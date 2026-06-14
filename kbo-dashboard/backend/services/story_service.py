"""AI 데일리 경기 스토리(프리뷰/리뷰) 생성 서비스.

today.py 의 라이브 경기 카드 + 순위/최근 흐름/선발 시즌 성적을 조립해
Claude Opus 4.8 단일 호출로 경기별 내러티브를 만든다. RAG/에이전트가 아니라
"데이터를 골라 글로 쓰는" 단순 텍스트 생성 작업이라 단일 호출이면 충분하다.

ANTHROPIC_API_KEY 가 없으면 mock 폴백으로 동작해 프런트 흐름을 확인할 수 있다.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from routers.today import _fetch  # 라이브 경기 카드(네이버 프록시) 재사용


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "kbo_official"
PROCESSED_DIR = ROOT / "data" / "processed"

MODEL = "claude-opus-4-8"

# 네이버 홈/원정 팀 코드 -> CSV(팀명/Team) 표기. today.py HOME_STADIUM 과 동일 코드 체계.
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
    "경기 전이면 매치업 프리뷰(선발 대결과 두 팀의 분위기), 경기 종료면 결과 리뷰를 쓴다. "
    "3~4문장, 과장 없이 담백하게."
)


class StoryService:
    """경기별 AI 스토리 생성 + 상태 기반 캐싱."""

    def __init__(self) -> None:
        self._csv_cache: dict[int, dict[str, pd.DataFrame]] = {}
        # story 캐시: cache_key -> (저장시각, story dict). 종료 경기는 TTL 무한.
        self._story_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._preview_ttl = 600.0  # 프리뷰/진행중 경기는 10분만 캐싱

    # ── 공개 API ──────────────────────────────────────────────────────────
    def stories_for_date(self, date: str, season: int) -> dict[str, Any]:
        games = _fetch(date)  # today.py 가 60초 캐싱 + 네이버 호출 처리
        csv = self._load_csv(season)
        stories = [self._story_for_game(g, csv) for g in games]
        return {
            "status": "success",
            "date": date,
            "season": season,
            "model": MODEL,
            "ai_enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
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
            if done or time.time() - saved_at < self._preview_ttl:
                return {**story, "cached": True}

        context = self._build_context(game, csv)
        kind = "review" if game.get("statusCode") == "RESULT" else "preview"
        text = self._generate(context, kind)
        story = {
            "gameId": game.get("gameId"),
            "kind": kind,
            "matchup": context["matchup"],
            "story": text,
            "cached": False,
        }
        self._story_cache[key] = (time.time(), story)
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
                "score": home.get("score"),
                "team": self._team_context(home_team, csv),
                "starter": self._starter_context(home.get("starter"), home_team, csv),
            },
            "away": {
                "name": away.get("name"),
                "score": away.get("score"),
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

    # ── Claude 호출 (or mock) ─────────────────────────────────────────────
    def _generate(self, context: dict[str, Any], kind: str) -> str:
        if not os.getenv("ANTHROPIC_API_KEY"):
            return self._mock(context, kind)

        import anthropic  # 키가 있을 때만 import (의존성 선택적)

        client = anthropic.Anthropic()
        user_prompt = self._render_prompt(context, kind)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return next((b.text for b in resp.content if b.type == "text"), "").strip()

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
    def _mock(context: dict[str, Any], kind: str) -> str:
        home = context["home"]
        away = context["away"]
        h_team = home["team"]
        a_team = away["team"]
        if kind == "review" and home.get("score") is not None:
            return (
                f"[mock] {context['matchup']} 경기는 {home['name']} {home['score']} : "
                f"{away['score']} {away['name']}로 마무리됐다. "
                f"(ANTHROPIC_API_KEY를 설정하면 실제 AI 리뷰가 생성됩니다.)"
            )
        return (
            f"[mock] {context['stadium']} {context['time']}, "
            f"{away['name']}(현재 {a_team.get('rank', '?')}위) 와 "
            f"{home['name']}(현재 {h_team.get('rank', '?')}위) 의 맞대결. "
            f"선발은 {(away.get('starter') or {}).get('name', '미정')} 대 "
            f"{(home.get('starter') or {}).get('name', '미정')}. "
            f"(ANTHROPIC_API_KEY를 설정하면 실제 AI 프리뷰가 생성됩니다.)"
        )

    # ── CSV 로딩/유틸 ────────────────────────────────────────────────────
    def _load_csv(self, season: int) -> dict[str, pd.DataFrame]:
        if season in self._csv_cache:
            return self._csv_cache[season]
        data = {
            "standings": self._read(RAW_DIR / f"kbo_team_rank_{season}.csv"),
            "team_games": self._read(PROCESSED_DIR / f"kbo_team_games_{season}.csv"),
            "pitchers": self._read(PROCESSED_DIR / f"kbo_naver_pitchers_{season}.csv"),
        }
        self._csv_cache[season] = data
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
