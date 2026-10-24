"""
공식·외부 기록과 자체 계산 기록을 영역(스키마)별로 나눈 테이블 (P1-A).

  ref       경기·선수 기준 정보(ID 기반)
  ingest    원본 응답(JSON 그대로)과 수집 시도 이력
  official  외부 기록(현재 출처: naver_boxscore). 원본 파일 1개 = 행 묶음, 불변
  derived   투구 데이터로 자체 계산한 선수-경기 기록(빌드별 불변, derived.build)
  verify    derived vs official 대조 결과(naver_* 상태. KBO 공식 사이트 대조는 kbo_* 로 따로)

기존 public 테이블과 메타데이터를 공유하지 않는다(RecordsBase) — database.init_db() 의
create_all 이 이 스키마들을 건드리지 않게, 적재는 migrate_records.py 가 따로 한다.

시점 보존(예측용): 외부 기록은 원본별로 행이 남고(fetched_at), 계산·대조 결과도 판본·시각을 단다.
'그 시점에 알 수 있던 값'은 fetched_at/loaded_at <= 기준시각 으로 거른다.
"""
from sqlalchemy import JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, declared_attr
from sqlalchemy.sql import func

RecordsBase = declarative_base()
SCHEMAS = ("ref", "ingest", "official", "derived", "verify")
Payload = JSON().with_variant(JSONB(), "postgresql")


def _now():
    return Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Game(RecordsBase):
    __tablename__ = "game"
    __table_args__ = {"schema": "ref"}
    game_id = Column(String(13), primary_key=True)  # KBO GameId (예: 20250719HHKT0). 네이버는 뒤에 시즌을 붙인다
    season = Column(Integer, nullable=False, index=True)
    game_date = Column(Date, nullable=False)
    dh = Column(Integer, nullable=False)  # 0=단일, 1·2=더블헤더 차전
    away_team = Column(String(20))
    home_team = Column(String(20))
    status = Column(String(20))
    away_score = Column(Integer)
    home_score = Column(Integer)
    ballpark = Column(String(20))
    source = Column(String(30), nullable=False)
    updated_at = _now()


class Player(RecordsBase):
    __tablename__ = "player"
    __table_args__ = {"schema": "ref"}
    player_id = Column(Integer, primary_key=True)  # KBO playerId = 네이버 pcode = 투구 데이터 PitcherId/BatterId
    name = Column(String(50))
    updated_at = _now()


class PlayerName(RecordsBase):
    """선수 이름 이력(출처별). 이름이 바뀌어도 옛 이름이 남는다."""
    __tablename__ = "player_name"
    __table_args__ = {"schema": "ref"}
    player_id = Column(Integer, primary_key=True)
    name = Column(String(50), primary_key=True)
    source = Column(String(30), primary_key=True)
    first_seen_at = _now()


class RawRecord(RecordsBase):
    __tablename__ = "raw_record"
    __table_args__ = {"schema": "ingest"}
    raw_file = Column(String(80), primary_key=True)  # record/ 아래 상대 경로 = 수집 1회
    source = Column(String(30), nullable=False)
    season = Column(Integer, nullable=False)
    game_id = Column(String(13), nullable=False, index=True)
    url = Column(Text)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    sha256 = Column(String(64), nullable=False)
    payload = Column(Payload, nullable=False)
    loaded_at = _now()


class FetchLog(RecordsBase):
    __tablename__ = "fetch_log"
    __table_args__ = {"schema": "ingest"}
    run_id = Column(String(20), primary_key=True)
    fetched_at = Column(DateTime(timezone=True), primary_key=True)
    game_id = Column(String(13), primary_key=True)
    status = Column(String(20), primary_key=True)  # saved | unchanged | skipped_existing | error
    season = Column(Integer)
    path = Column(String(80))
    sha256 = Column(String(64))
    error = Column(Text)


class _GameLine:
    """경기별 외부 기록 한 줄의 공통 열. 키 = (원본 파일, 선수) — 다시 받으면 새 원본의 행이 추가된다."""
    @declared_attr
    def raw_file(cls):
        return Column(String(80), ForeignKey("ingest.raw_record.raw_file"), primary_key=True)

    player_id = Column(Integer, primary_key=True)
    source = Column(String(30), nullable=False)
    season = Column(Integer, nullable=False)
    game_id = Column(String(13), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False)
    sha256 = Column(String(64), nullable=False)
    game_status_code = Column(String(5))
    side = Column(String(4))
    team = Column(String(20))
    player = Column(String(50))
    team_sum_mismatch = Column(String(60), nullable=False, default="")


class GamePitcherLine(_GameLine, RecordsBase):
    __tablename__ = "game_pitcher_line"
    __table_args__ = {"schema": "official"}
    ord = Column(Integer)
    ip = Column(String(10))  # 원본 표기 그대로("5 ⅔")
    outs = Column(Integer)
    bf = Column(Integer)
    ab = Column(Integer)
    h = Column(Integer)
    hr = Column(Integer)
    bb = Column(Integer)
    bbhp = Column(Integer)
    so = Column(Integer)
    r = Column(Integer)
    er = Column(Integer)
    np = Column(Integer)
    decision = Column(String(5))


class GameBatterLine(_GameLine, RecordsBase):
    __tablename__ = "game_batter_line"
    __table_args__ = {"schema": "official"}
    bat_order = Column(Integer)
    pos = Column(String(10))
    ab = Column(Integer)
    h = Column(Integer)
    hr = Column(Integer)
    bb = Column(Integer)
    so = Column(Integer)
    r = Column(Integer)
    rbi = Column(Integer)
    sb = Column(Integer)
    ibb = Column(Integer)  # 이닝별 결과 칸의 '고4' 수(자동 고의4구 포함)


class Build(RecordsBase):
    """계산·대조 산출물 한 벌(= 입력 CSV 내용 해시). 행은 빌드별로 불변 — 입력이 바뀌면 새 빌드가 쌓이고
    옛 빌드는 그대로 남는다. 현재 값은 *_current 뷰(시즌·종류별 가장 최근 적재 빌드)로 본다."""
    __tablename__ = "build"
    __table_args__ = {"schema": "derived"}
    build_id = Column(String(16), primary_key=True)
    kind = Column(String(20), nullable=False)  # player_game | player_game_check | outs_uncertain
    season = Column(Integer, nullable=False)
    calc_rule = Column(String(12), nullable=False)
    source_file = Column(String(80), nullable=False)
    row_count = Column(Integer, nullable=False)
    loaded_at = _now()  # 이 빌드를 처음 적재한 시각 — 시점 조회(loaded_at <= 기준시각)의 기준
    # 대조·예외 빌드가 기준으로 삼은 player_game 빌드(같은 적재에서 함께 올라간 것). 계산 빌드 자신은 NULL.
    # API 는 보여 주는 계산 빌드와 연결된 대조 결과만 쓴다(Codex P2-A 3차).
    basis_build_id = Column(String(16))


class PlayerGame(RecordsBase):
    """build_player_games 산출물. 빌드별 불변."""
    __tablename__ = "player_game"
    __table_args__ = {"schema": "derived"}
    build_id = Column(String(16), ForeignKey("derived.build.build_id"), primary_key=True)
    calc_rule = Column(String(12), nullable=False)
    role = Column(String(7), primary_key=True)
    player_id = Column(Integer, primary_key=True)
    game_id = Column(String(13), primary_key=True)
    season = Column(Integer, nullable=False, index=True)
    game_date = Column(Date)
    dh = Column(Integer)
    player = Column(String(50))
    team = Column(String(20))
    opponent = Column(String(20))
    home_away = Column(String(4))
    pa = Column(Integer)
    ab = Column(Integer)
    h = Column(Integer)
    b2 = Column(Integer)
    b3 = Column(Integer)
    hr = Column(Integer)
    bb = Column(Integer)
    hbp = Column(Integer)
    sf = Column(Integer)
    sh = Column(Integer)
    so = Column(Integer)
    bf = Column(Integer)
    result_unknown = Column(Integer)
    pa_uncertain = Column(Integer)
    attribution_uncertain = Column(Integer)
    pa_complete = Column(Boolean)
    stats_complete = Column(Boolean)
    outs = Column(Integer)  # OutsComplete 일 때만 값이 있다 — 외부 기록으로 채우지 않는다
    outs_complete = Column(Boolean)


class PlayerGameCheck(RecordsBase):
    __tablename__ = "player_game_check"
    __table_args__ = {"schema": "verify"}
    build_id = Column(String(16), ForeignKey("derived.build.build_id"), primary_key=True)
    calc_rule = Column(String(12), nullable=False)
    external_raw_file = Column(String(80), ForeignKey("ingest.raw_record.raw_file"), primary_key=True)
    role = Column(String(7), primary_key=True)
    player_id = Column(Integer, primary_key=True)
    metric = Column(String(10), primary_key=True)
    season = Column(Integer, nullable=False)
    game_id = Column(String(13), nullable=False, index=True)
    player = Column(String(50))
    calc_value = Column(Integer)
    calc_proven = Column(Boolean, nullable=False)
    external_value = Column(Integer)
    external_source = Column(String(30), nullable=False)
    external_fetched_at = Column(DateTime(timezone=True))
    status = Column(String(30), nullable=False, index=True)
    checked_at = Column(DateTime(timezone=True), nullable=False)


class OutsUncertain(RecordsBase):
    __tablename__ = "outs_uncertain"
    __table_args__ = {"schema": "verify"}
    build_id = Column(String(16), ForeignKey("derived.build.build_id"), primary_key=True)
    calc_rule = Column(String(12), nullable=False)
    game_id = Column(String(13), primary_key=True)
    player_id = Column(Integer, primary_key=True)
    season = Column(Integer, nullable=False)
    game_date = Column(Date)
    player = Column(String(50))
    team = Column(String(20))
    halves = Column(String(60))
    reasons = Column(String(120))
    last_results = Column(Text)
    last_outs = Column(String(30))
    outs_raw = Column(Integer)  # 근거 없이 채운 원값 — 확정값 아님
    naver_outs = Column(Integer)
    naver_status = Column(String(30), nullable=False)
    external_fetched_at = Column(DateTime(timezone=True))
    external_raw_file = Column(String(80), ForeignKey("ingest.raw_record.raw_file"))  # 미수집 경기는 NULL
    checked_at = Column(DateTime(timezone=True), nullable=False)


class VerifyException(RecordsBase):
    """대조 예외 사례(자동 고의4구·콜드·무승부·대주자·원본 누락 등). 값이 아니라 사유 목록이다."""
    __tablename__ = "exception"
    __table_args__ = {"schema": "verify"}
    build_id = Column(String(16), ForeignKey("derived.build.build_id"), primary_key=True)
    row_no = Column(Integer, primary_key=True)  # 빌드 안 순번(자연 키가 없다 — 한 경기에 같은 종류가 여럿)
    calc_rule = Column(String(12), nullable=False)
    season = Column(Integer, nullable=False)
    game_id = Column(String(13), nullable=False, index=True)
    kind = Column(String(40), nullable=False, index=True)
    role = Column(String(7))
    player_id = Column(Integer)
    player = Column(String(50))
    count = Column(Integer, nullable=False)
    detail = Column(Text)
    checked_at = Column(DateTime(timezone=True), nullable=False)


class ScheduleGame(RecordsBase):
    """정규시즌 일정·결과 한 경기(취소 포함). 출처 CSV 한 벌 = 빌드, 빌드별 불변.
    status 는 원본(status_raw, Note)에서 파생: final / tie(무승부) / canceled(사유) / scheduled."""
    __tablename__ = "schedule_game"
    __table_args__ = {"schema": "official"}
    build_id = Column(String(16), ForeignKey("derived.build.build_id"), primary_key=True)
    row_no = Column(Integer, primary_key=True)
    season = Column(Integer, nullable=False, index=True)
    game_date = Column(Date, nullable=False, index=True)
    game_time = Column(String(8))
    weekday = Column(String(4))
    away_team = Column(String(20), nullable=False)
    home_team = Column(String(20), nullable=False)
    away_score = Column(Integer)
    home_score = Column(Integer)
    status = Column(String(10), nullable=False)
    status_raw = Column(String(20), nullable=False)
    cancel_reason = Column(String(30))
    ballpark = Column(String(20))
    game_id = Column(String(13))  # 취소 경기는 원본에 없다
    dh = Column(Integer)          # GameId 13번째 자리(0 단일, 1·2 더블헤더) — GameId 없으면 NULL
    source = Column(String(30), nullable=False)
    collected_at = Column(DateTime(timezone=True), nullable=False)


class SeasonStanding(RecordsBase):
    """원본 시즌 최종 순위표(팀 1행). 값은 원본 그대로 — 계산 순위와 대조는 API 가 따로 한다."""
    __tablename__ = "season_standing"
    __table_args__ = {"schema": "official"}
    build_id = Column(String(16), ForeignKey("derived.build.build_id"), primary_key=True)
    team = Column(String(20), primary_key=True)
    season = Column(Integer, nullable=False, index=True)
    rank = Column(Integer)
    games = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    draws = Column(Integer)
    pct = Column(Numeric(6, 3))
    games_behind = Column(Numeric(5, 1))
    last10 = Column(String(20))
    streak = Column(String(10))
    home_record = Column(String(20))
    away_record = Column(String(20))
    source = Column(String(30), nullable=False)
    collected_at = Column(DateTime(timezone=True), nullable=False)
