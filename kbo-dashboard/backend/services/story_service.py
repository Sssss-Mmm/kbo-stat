"""AI 데일리 경기 스토리(프리뷰/리뷰) 생성 서비스.

today.py 의 경기 카드(로컬 일정 CSV) + 순위/최근 흐름/선발 시즌 성적을 조립해
OpenAI API 단일 호출로 경기별 내러티브를 만든다. RAG/에이전트가 아니라
"데이터를 골라 글로 쓰는" 단순 텍스트 생성 작업이라 단일 호출이면 충분하다.

외부 LLM 호출은 llm_access 승인 스위치(기본 꺼짐)가 켜져야만 나간다 — 꺼져 있으면 로컬 기록만으로 만든
한 줄 요약(_mock)을 쓴다. 키만 있어서는 호출하지 않는다.
"""
from __future__ import annotations

import logging
import os
import time
from threading import Lock
from pathlib import Path
from typing import Any

import pandas as pd

from services.csv_cache import file_versions
from services.ai_budget import ai_budget
from services import llm_access

logger = logging.getLogger(__name__)

from routers.today import _fetch  # 경기 카드(로컬 일정 CSV — 외부 요청 없음) 재사용

BUDGET_MESSAGE = "오늘의 AI 생성 한도에 도달했습니다. 경기 기록을 확인해 주세요."
# 승인 후 호출이 실패했을 때의 기록 요약 꼬리 문구 — 승인 전 차단 문구와 구분하고, 이 결과는 짧게만 캐시해 다시 시도한다.
FAILED_NOTE = "(AI 리뷰를 만들지 못해 기록 요약을 표시합니다.)"


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "kbo_official"
PROCESSED_DIR = ROOT / "data" / "processed"

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

# 승부예측(경기 전): log5(홈/원정 분리 승률) + 홈 어드밴티지 + 선발 ERA 보정.
HOME_EDGE = 0.04      # KBO 홈 승률 ≈ 0.54
STARTER_W = 0.03      # 선발 ERA 1.00 차이 ≈ 승률 3%p
STARTER_CAP = 1.5     # ERA 편차는 ±1.5까지만 반영(소표본 방어)
PROB_MIN, PROB_MAX = 0.15, 0.85

# 팀 코드 -> CSV(팀명/Team) 표기. today.py TEAM_CODE 의 역방향.
CODE_TO_TEAM = {
    "LG": "LG", "OB": "두산", "WO": "키움", "KT": "KT",
    "SK": "SSG", "SSG": "SSG", "NC": "NC", "LT": "롯데",
    "SS": "삼성", "HT": "KIA", "KIA": "KIA", "HH": "한화",
}

SYSTEM_PROMPT = (
    "당신은 KBO 리그를 오래 취재한 한국어 야구 칼럼니스트다. "
    "주어진 데이터(순위, 최근 10경기 흐름, 득실차, 선발투수 시즌 성적, 경기 결과)만 "
    "근거로 삼아 한 경기에 대한 짧은 글을 쓴다. 데이터에 없는 사실(부상, 라인업, 과거 "
    "맞대결 등)을 지어내지 않는다. 숫자는 자연스럽게 문장에 녹인다. "
    "runs_scored 는 그 팀이 '낸' 점수다(실점이 아니다). "
    "선발투수의 이 경기 투구 내용(이닝, 실점, 탈삼진, 승패)은 데이터에 없으니 절대 쓰지 마라. "
    "ERA·W·L·WHIP·K9 는 이 경기를 포함하지 않을 수 있는 시즌 누적이므로 "
    "'이 경기로 몇 승째' 같은 표현도 쓰지 마라. "
    "경기 전이면 매치업 프리뷰(선발 대결과 두 팀의 분위기), 경기 종료면 결과 리뷰를 쓴다. "
    "3~4문장, 과장 없이 담백하게."
)


class StoryService:
    """경기별 AI 스토리 생성 + 상태 기반 캐싱."""

    def __init__(self) -> None:
        self._csv_cache: dict[int, dict[str, pd.DataFrame]] = {}
        self._csv_versions = {}
        # story 캐시: cache_key -> (저장시각, story dict). 종료 경기는 TTL 무한.
        self._story_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._preview_ttl = 600.0  # 프리뷰/진행중 경기는 10분만 캐싱
        self._retry_keys: set[str] = set()  # AI 호출 실패로 기록 요약을 준 종료 경기 — 영구 캐시하지 않는다
        self._lock = Lock()

    # ── 공개 API ──────────────────────────────────────────────────────────
    def stories_for_date(self, date: str, season: int) -> dict[str, Any]:
        with self._lock:
            return self._stories_for_date(date, season)

    def _stories_for_date(self, date: str, season: int) -> dict[str, Any]:
        games = _fetch(date)  # 로컬 일정 CSV. 시즌 파일이 없으면 503(HTTPException)
        csv = self._load_csv(season)
        stories = [self._story_for_game(g, csv) for g in games]
        return {
            "status": "success",
            "date": date,
            "season": season,
            "model": MODEL,
            "ai_enabled": llm_access.allowed(),
            "count": len(stories),
            "data": stories,
        }

    # ── 경기 1건 처리 ────────────────────────────────────────────────────
    def _story_for_game(self, game: dict, csv: dict[str, pd.DataFrame]) -> dict[str, Any]:
        key = self._cache_key(game)
        cached = self._story_cache.get(key)
        if cached:
            saved_at, story = cached
            done = game.get("statusCode") == "RESULT"
            if (done and key not in self._retry_keys) or time.time() - saved_at < self._preview_ttl:
                return {**story, "cached": True}

        context = self._build_context(game, csv)
        kind = "review" if game.get("statusCode") == "RESULT" else "preview"
        # 경기 전은 AI 텍스트 대신 승부예측. 종료 경기만 LLM 리뷰를 쓴다.
        story = {
            "gameId": game.get("gameId"),
            "kind": kind,
            "matchup": context["matchup"],
            "story": self._generate(context, kind) if kind == "review" else None,
            "winProb": None if kind == "review" else win_prob(context, self._league_era(csv)),
            "cached": False,
        }
        if story["story"] == BUDGET_MESSAGE:
            return story  # 한도가 풀리면 다시 생성해야 하므로 캐싱하지 않는다.
        if len(self._story_cache) >= 2048:
            self._retry_keys.discard(next(iter(self._story_cache)))
            self._story_cache.pop(next(iter(self._story_cache)))
        self._story_cache[key] = (time.time(), story)
        if (story["story"] or "").endswith(FAILED_NOTE):
            self._retry_keys.add(key)  # 일시 장애가 영구 대체 결과가 되지 않게 10분 뒤 다시 시도
        else:
            self._retry_keys.discard(key)
        return story

    @staticmethod
    def _cache_key(game: dict) -> str:
        # 상태/스코어가 바뀌면 새 스토리. (경기전→진행중→종료 전환마다 갱신)
        home = game.get("home", {})
        away = game.get("away", {})
        return "|".join(
            str(x)
            for x in (
                game.get("gameId"),
                game.get("statusCode"),
                home.get("score"),
                away.get("score"),
                home.get("starter"),
                away.get("starter"),
            )
        )

    # ── 컨텍스트 조립 ────────────────────────────────────────────────────
    def _build_context(self, game: dict, csv: dict[str, pd.DataFrame]) -> dict[str, Any]:
        home = game.get("home", {})
        away = game.get("away", {})
        home_team = CODE_TO_TEAM.get(home.get("code", ""), home.get("name") or "")
        away_team = CODE_TO_TEAM.get(away.get("code", ""), away.get("name") or "")
        return {
            "matchup": f"{away.get('name')} @ {home.get('name')}",
            "stadium": game.get("stadium"),
            "time": game.get("time"),
            "status": game.get("status"),
            "status_code": game.get("statusCode"),
            "winner": game.get("winner"),
            "home": {
                "name": home.get("name"),
                "runs_scored": home.get("score"),
                "team": self._team_context(home_team, csv),
                "starter": self._starter_context(home.get("starter"), home_team, csv),
            },
            "away": {
                "name": away.get("name"),
                "runs_scored": away.get("score"),
                "team": self._team_context(away_team, csv),
                "starter": self._starter_context(away.get("starter"), away_team, csv),
            },
        }

    def _team_context(self, team: str, csv: dict[str, pd.DataFrame]) -> dict[str, Any]:
        out: dict[str, Any] = {"team": team}
        standings = csv["standings"]
        if not standings.empty:
            row = standings[standings["팀명"].astype(str) == team]
            if not row.empty:
                r = row.iloc[0]
                out.update(
                    rank=self._num(r.get("순위")),
                    wins=self._num(r.get("승")),
                    losses=self._num(r.get("패")),
                    draws=self._num(r.get("무")),
                    win_rate=r.get("승률"),
                    recent10=r.get("최근10경기"),
                    streak=r.get("연속"),
                    home_record=r.get("홈"),
                    away_record=r.get("방문"),
                )
        games = csv["team_games"]
        if not games.empty:
            tg = games[games["Team"].astype(str) == team]
            if not tg.empty:
                out["runs_for"] = int(tg["RunsFor"].sum())
                out["runs_against"] = int(tg["RunsAgainst"].sum())
                out["run_diff"] = out["runs_for"] - out["runs_against"]
        return out

    def _starter_context(
        self, name: str | None, team: str, csv: dict[str, pd.DataFrame]
    ) -> dict[str, Any] | None:
        if not name:
            return None
        pitchers = csv["pitchers"]
        if pitchers.empty:
            return {"name": name}
        row = pitchers[pitchers["선수명"].astype(str) == name]
        if row.empty:
            return {"name": name}
        r = row.iloc[0]
        return {
            "name": name,
            "team": team,
            "W": self._num(r.get("W")),
            "L": self._num(r.get("L")),
            "ERA": self._round(r.get("ERA")),
            "WHIP": self._round(r.get("WHIP")),
            "K9": self._round(r.get("K/9")),
            "IP": r.get("IP"),
        }

    # ── OpenAI 호출(승인 시) 또는 로컬 기록 요약 ──────────────────────────
    def _generate(self, context: dict[str, Any], kind: str) -> str:
        if not llm_access.allowed():
            return self._mock(context, kind)

        if not ai_budget.take():
            return BUDGET_MESSAGE

        try:
            client = llm_access.client()
            resp = client.chat.completions.create(
                model=MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": self._render_prompt(context, kind)},
                ],
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001 — 한 경기 실패로 그날 카드 전체가 500 이 되지 않게(QA 와 같은 방식)
            # 예외 종류만 남긴다(메시지에 요청 내용이 섞일 수 있다). 예산은 이미 썼다 — 결과는 10분만 캐시돼 다시 시도한다.
            logger.warning("story model call failed: %s", type(exc).__name__)
            return self._mock(context, kind, failed=True)

    @staticmethod
    def _render_prompt(context: dict[str, Any], kind: str) -> str:
        import json

        instruction = (
            "다음은 오늘 종료된 경기 데이터다. 결과를 중심으로 리뷰를 써라."
            if kind == "review"
            else "다음은 곧 열릴(또는 진행 중인) 경기 데이터다. 매치업 프리뷰를 써라."
        )
        body = json.dumps(context, ensure_ascii=False, indent=2)
        return f"{instruction}\n\n```json\n{body}\n```"

    @staticmethod
    def _mock(context: dict[str, Any], kind: str, failed: bool = False) -> str:
        home = context["home"]
        away = context["away"]
        h_team = home["team"]
        a_team = away["team"]
        if kind == "review" and home.get("runs_scored") is not None:
            return (
                f"[기록 요약] {context['matchup']} 경기는 {home['name']} {home['runs_scored']} : "
                f"{away['runs_scored']} {away['name']}로 마무리됐다. "
                + (FAILED_NOTE if failed else "(외부 AI 리뷰는 데이터 이용 권한 확인 전까지 꺼져 있습니다.)")
            )
        return (
            f"[기록 요약] {context['stadium']} {context['time']}, "
            f"{away['name']}(현재 {a_team.get('rank', '?')}위) 와 "
            f"{home['name']}(현재 {h_team.get('rank', '?')}위) 의 맞대결. "
            f"선발은 {(away.get('starter') or {}).get('name', '미정')} 대 "
            f"{(home.get('starter') or {}).get('name', '미정')}. "
            + (FAILED_NOTE if failed else "(외부 AI 프리뷰는 데이터 이용 권한 확인 전까지 꺼져 있습니다.)")
        )

    @staticmethod
    def _league_era(csv: dict[str, pd.DataFrame]) -> float:
        # ponytail: 리그 평균 자책점을 팀 득점/경기 * 0.92 로 근사한다.
        # 정확히 하려면 투수 CSV의 ER/IP 합계가 필요한데, 보정항 하나에 그 정도는 과하다.
        games = csv["team_games"]
        if games.empty or "RunsFor" not in games:
            return 4.5
        return float(games["RunsFor"].mean()) * 0.92

    # ── CSV 로딩/유틸 ────────────────────────────────────────────────────
    def _load_csv(self, season: int) -> dict[str, pd.DataFrame]:
        paths = {
            "standings": RAW_DIR / f"kbo_team_rank_{season}.csv",
            "team_games": PROCESSED_DIR / f"kbo_team_games_{season}.csv",
            "pitchers": PROCESSED_DIR / f"kbo_naver_pitchers_{season}.csv",
        }
        version = file_versions(list(paths.values()))
        if season in self._csv_cache and self._csv_versions.get(season) == version:
            return self._csv_cache[season]
        data = {name: self._read(path) for name, path in paths.items()}
        changed = season in self._csv_versions
        self._csv_cache[season] = data
        self._csv_versions[season] = version
        if changed:
            self._story_cache.clear()
        return data

    @staticmethod
    def _read(path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path)

    @staticmethod
    def _num(value: Any) -> Any:
        try:
            f = float(value)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _round(value: Any) -> Any:
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return value


# ── 승부예측 (순수 함수) ──────────────────────────────────────────────────
def log5(a: float, b: float) -> float:
    """승률 a 팀이 승률 b 팀을 이길 확률."""
    d = a * (1 - b) + b * (1 - a)
    return (a * (1 - b)) / d if d else 0.5


def record_rate(record: Any) -> float | None:
    """'19-0-10'(승-무-패) -> 승률."""
    try:
        w, _, l = (int(x) for x in str(record).split("-"))
    except (ValueError, TypeError):
        return None
    return w / (w + l) if w + l else None


def era_edge(starter: dict[str, Any] | None, league_era: float) -> float:
    """선발이 리그 평균보다 얼마나 좋은가(자책점 기준, ±STARTER_CAP)."""
    try:
        era = float((starter or {}).get("ERA"))
    except (TypeError, ValueError):
        return 0.0
    return max(-STARTER_CAP, min(STARTER_CAP, league_era - era))


def win_prob(context: dict[str, Any], league_era: float) -> dict[str, Any] | None:
    """홈 관점 예상 승률. 순위 데이터가 없으면 None."""
    home, away = context["home"], context["away"]
    ph = record_rate(home["team"].get("home_record")) or _rate(home["team"].get("win_rate"))
    pa = record_rate(away["team"].get("away_record")) or _rate(away["team"].get("win_rate"))
    if ph is None or pa is None:
        return None
    edge = era_edge(home.get("starter"), league_era) - era_edge(away.get("starter"), league_era)
    p = log5(ph, pa) + HOME_EDGE + STARTER_W * edge
    p = max(PROB_MIN, min(PROB_MAX, p))
    return {
        "home": round(p, 3),
        "away": round(1 - p, 3),
        "starterEdge": round(edge, 2),
        "leagueEra": round(league_era, 2),
    }


def _rate(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":  # python -m services.story_service
    assert abs(log5(0.5, 0.5) - 0.5) < 1e-9
    assert log5(0.7, 0.3) > 0.8 and log5(0.3, 0.7) < 0.2
    assert record_rate("19-0-10") == 19 / 29
    assert record_rate("") is None and record_rate(None) is None
    assert record_rate("0-0-0") is None
    assert era_edge({"ERA": 2.5}, 4.5) == 1.5          # 캡 적용
    assert era_edge({"ERA": 3.5}, 4.5) == 1.0
    assert era_edge(None, 4.5) == 0.0 and era_edge({"name": "x"}, 4.5) == 0.0

    even = {
        "home": {"team": {"home_record": "10-0-10"}, "starter": None},
        "away": {"team": {"away_record": "10-0-10"}, "starter": None},
    }
    assert win_prob(even, 4.5)["home"] == 0.54, win_prob(even, 4.5)   # 홈 어드밴티지만
    assert win_prob(even, 4.5)["home"] + win_prob(even, 4.5)["away"] == 1.0
    ace = {
        "home": {"team": {"home_record": "10-0-10"}, "starter": {"ERA": 2.0}},
        "away": {"team": {"away_record": "10-0-10"}, "starter": {"ERA": 6.0}},
    }
    assert win_prob(ace, 4.5)["home"] == 0.63, win_prob(ace, 4.5)     # 0.54 + 0.03*3.0
    assert win_prob({"home": {"team": {}, "starter": None},
                     "away": {"team": {}, "starter": None}}, 4.5) is None
    print("ok")
