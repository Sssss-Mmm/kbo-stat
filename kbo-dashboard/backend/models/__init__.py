from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Team(Base):
    """팀 정보"""
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True)  # 팀명 (시즌 무관 고유)

    # 관계설정
    standings = relationship("Standing", back_populates="team")
    schedules = relationship("Schedule", back_populates="home_team", foreign_keys="[Schedule.home_team_id]")

    def __repr__(self):
        return f"<Team {self.name}>"


class Standing(Base):
    """팀 순위"""
    __tablename__ = "standings"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    rank = Column(Integer)  # 순위
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    games = Column(Integer)  # 경기
    wins = Column(Integer)  # 승
    losses = Column(Integer)  # 패
    draws = Column(Integer)  # 무
    win_rate = Column(Numeric(5, 3))  # 승률
    games_behind = Column(Numeric(5, 1))  # 게임차
    last_10_games = Column(String(100))  # 최근10경기
    streak = Column(String(50))  # 연속
    home_record = Column(String(50))  # 홈
    away_record = Column(String(50))  # 방문
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계설정
    team = relationship("Team", back_populates="standings")

    def __repr__(self):
        return f"<Standing {self.season} {self.rank}위>"


class Schedule(Base):
    """경기 일정"""
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    game_date = Column(Date, index=True)  # 경기일
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    home_score = Column(Integer)  # 홈팀 점수
    away_score = Column(Integer)  # 원정팀 점수
    status = Column(String(20))  # 진행상태 (예정, 진행중, 완료)
    stadium = Column(String(100))  # 경기장
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계설정
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])

    def __repr__(self):
        return f"<Schedule {self.game_date}>"


class Hitter(Base):
    """타자 통계"""
    __tablename__ = "hitters"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    rank = Column(Integer)  # 순위
    player_name = Column(String(100), index=True)  # 선수명
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    avg = Column(Numeric(5, 3))  # 타율
    games = Column(Integer)  # 경기
    pa = Column(Integer)  # 타석
    ab = Column(Integer)  # 타수
    hits = Column(Integer)  # 안타
    doubles = Column(Integer)  # 2루타
    triples = Column(Integer)  # 3루타
    home_runs = Column(Integer)  # 홈런
    rbi = Column(Integer)  # 타점
    sb = Column(Integer)  # 도루
    cs = Column(Integer)  # 도루실
    bb = Column(Integer)  # 볼넷
    hbp = Column(Integer)  # 사구
    so = Column(Integer)  # 삼진
    gdp = Column(Integer)  # 병살
    errors = Column(Integer)  # 오류
    xbh = Column(Integer)  # 장타
    go = Column(Integer)
    ao = Column(Integer)
    go_ao = Column(Numeric(5, 2))  # GO/AO
    gw_rbi = Column(Integer)  # GW RBI
    bb_k = Column(Numeric(5, 2))  # BB/K
    p_pa = Column(Numeric(5, 2))  # P/PA
    isop = Column(Numeric(5, 3))  # ISOP
    xr = Column(Numeric(5, 1))  # XR
    gpa = Column(Numeric(5, 3))  # GPA
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계설정
    team = relationship("Team")

    def __repr__(self):
        return f"<Hitter {self.player_name} {self.avg}>"


class Pitcher(Base):
    """투수 통계"""
    __tablename__ = "pitchers"

    id = Column(Integer, primary_key=True, index=True)
    season = Column(Integer, index=True)
    rank = Column(Integer)  # 순위
    player_name = Column(String(100), index=True)  # 선수명
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    # 기본 통계
    games = Column(Integer)  # 경기
    games_started = Column(Integer)  # 선발
    wins = Column(Integer)  # 승
    losses = Column(Integer)  # 패
    saves = Column(Integer)  # 세이브
    era = Column(Numeric(5, 2))  # 평균자책점
    innings_pitched = Column(Numeric(5, 1))  # 이닝
    hits_allowed = Column(Integer)  # 피안타
    runs_allowed = Column(Integer)  # 피득점
    earned_runs = Column(Integer)  # 자책점
    walks = Column(Integer)  # 볼넷
    strikeouts = Column(Integer)  # 삼진
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 관계설정
    team = relationship("Team")

    def __repr__(self):
        return f"<Pitcher {self.player_name} {self.era}>"
