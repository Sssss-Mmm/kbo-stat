"""CSV 기반 경량 RAG 서비스.

외부 벡터 DB나 임베딩 없이, data/processed CSV를 문서(Evidence)로 펼친 뒤
토큰 겹침 기반 점수로 검색하고, 질문 의도(MVP/최근뜨거운팀/특정팀)에 따라
규칙 기반으로 답변을 합성한다. 데모/오프라인에서도 동작하는 게 목적.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = ROOT / "data" / "raw" / "kbo_official"
PROCESSED_DIR = ROOT / "data" / "processed"

TEAM_COL = "팀명"
RANK_COL = "순위"
WINS_COL = "승"
LOSSES_COL = "패"
DRAWS_COL = "무"
WIN_RATE_COL = "승률"
RECENT_COL = "최근10경기"
STREAK_COL = "연속"


@dataclass
class Evidence:
    """검색 단위 문서. body는 사람이 읽는 근거 문장, payload는 구조화 값."""
    title: str
    body: str
    source: str  # 출처 CSV 이름
    score: float  # 검색 점수 (retrieve 시 계산)
    payload: dict[str, Any]


class RagService:
    """CSV-backed retrieval and answer synthesis for the KBO demo."""

    def __init__(self) -> None:
        self._cache: dict[int, dict[str, pd.DataFrame]] = {}  # 시즌별 CSV 캐시

    def ask(self, question: str, season: int) -> dict[str, Any]:
        """질문 → 문서화 → 검색 → 답변 합성까지의 전체 파이프라인."""
        data = self._load(season)
        docs = self._build_documents(data)
        retrieved = self._retrieve(question, docs, limit=8)
        answer = self._synthesize(question, data, retrieved)
        return {
            "status": "success",
            "season": season,
            "question": question,
            "answer": answer,
            "evidence": [self._evidence_to_dict(item) for item in retrieved],
            "data_sources": self._data_sources(data),
        }

    def search(self, query: str, season: int, limit: int = 8) -> dict[str, Any]:
        """답변 합성 없이 상위 근거 문서만 반환한다."""
        data = self._load(season)
        docs = self._build_documents(data)
        retrieved = self._retrieve(query, docs, limit=limit)
        return {
            "status": "success",
            "season": season,
            "query": query,
            "results": [self._evidence_to_dict(item) for item in retrieved],
        }

    def _load(self, season: int) -> dict[str, pd.DataFrame]:
        """시즌별 소스 CSV 4종을 읽어 캐시한다(순위/경기/월간/타자지표)."""
        if season in self._cache:
            return self._cache[season]

        data = {
            "standings": self._read_csv(RAW_DIR / f"kbo_team_rank_{season}.csv"),
            "team_games": self._read_csv(PROCESSED_DIR / f"kbo_team_games_{season}.csv"),
            "team_monthly": self._read_csv(PROCESSED_DIR / f"kbo_team_monthly_{season}.csv"),
            "hitters": self._read_csv(PROCESSED_DIR / f"kbo_hitter_metrics_{season}.csv"),
        }
        self._cache[season] = data
        return data

    @staticmethod
    def _read_csv(path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path)

    def _build_documents(self, data: dict[str, pd.DataFrame]) -> list[Evidence]:
        """CSV 행들을 검색 가능한 Evidence 문서(팀 순위 + 타자 지표)로 펼친다."""
        docs: list[Evidence] = []

        standings = data["standings"]
        games = data["team_games"]
        hitters = data["hitters"]

        if not standings.empty:
            for _, row in standings.iterrows():
                team = row.get(TEAM_COL, "")
                team_games = games[games["Team"] == team] if not games.empty else pd.DataFrame()
                runs_for = int(team_games["RunsFor"].sum()) if not team_games.empty else 0
                runs_against = int(team_games["RunsAgainst"].sum()) if not team_games.empty else 0
                run_diff = runs_for - runs_against
                docs.append(
                    Evidence(
                        title=f"{team} team standing",
                        body=(
                            f"{team} rank {row.get(RANK_COL)} with "
                            f"{row.get(WINS_COL)} wins, {row.get(LOSSES_COL)} losses, "
                            f"win rate {row.get(WIN_RATE_COL)}, recent {row.get(RECENT_COL)}, "
                            f"streak {row.get(STREAK_COL)}, run differential {run_diff}."
                        ),
                        source="kbo_team_rank + kbo_team_games",
                        score=0,
                        payload={
                            "type": "team",
                            "team": team,
                            "rank": self._safe_number(row.get(RANK_COL)),
                            "wins": self._safe_number(row.get(WINS_COL)),
                            "losses": self._safe_number(row.get(LOSSES_COL)),
                            "draws": self._safe_number(row.get(DRAWS_COL)),
                            "win_rate": self._safe_number(row.get(WIN_RATE_COL)),
                            "recent": row.get(RECENT_COL),
                            "streak": row.get(STREAK_COL),
                            "runs_for": runs_for,
                            "runs_against": runs_against,
                            "run_diff": run_diff,
                        },
                    )
                )

        if not hitters.empty:
            for _, row in hitters.iterrows():
                player = row.get("Player", "")
                team = row.get("Team", "")
                docs.append(
                    Evidence(
                        title=f"{player} hitter metrics",
                        body=(
                            f"{player} of {team}: WARProxy {row.get('WARProxy')}, "
                            f"OPS {row.get('OPS')}, AVG {row.get('AVG')}, "
                            f"HR {row.get('HR')}, RBI {row.get('RBI')}."
                        ),
                        source="kbo_hitter_metrics",
                        score=0,
                        payload={
                            "type": "hitter",
                            "player": player,
                            "team": team,
                            "war_proxy": self._safe_number(row.get("WARProxy")),
                            "ops": self._safe_number(row.get("OPS")),
                            "avg": self._safe_number(row.get("AVG")),
                            "hr": self._safe_number(row.get("HR")),
                            "rbi": self._safe_number(row.get("RBI")),
                        },
                    )
                )

        return docs

    def _retrieve(self, query: str, docs: list[Evidence], limit: int) -> list[Evidence]:
        """토큰 겹침 + 정확매칭 보너스 + 의도 보너스로 점수화해 상위 N개를 고른다."""
        query_terms = self._terms(query)
        scored = []
        for doc in docs:
            text = f"{doc.title} {doc.body} {' '.join(map(str, doc.payload.values()))}"
            terms = self._terms(text)
            overlap = len(query_terms & terms)  # 공통 토큰 수
            exact_bonus = sum(2 for term in query_terms if term and term in text.lower())  # 부분문자열 매칭 가산
            type_bonus = self._intent_bonus(query, doc)  # 질문 의도와 문서 유형 일치 가산
            score = overlap + exact_bonus + type_bonus
            if score > 0:
                scored.append(Evidence(doc.title, doc.body, doc.source, score, doc.payload))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    def _synthesize(
        self,
        question: str,
        data: dict[str, pd.DataFrame],
        evidence: list[Evidence],
    ) -> dict[str, Any]:
        # 질문 키워드로 의도를 분기해 알맞은 규칙 기반 답변기를 고른다.
        lowered = question.lower()
        if "mvp" in lowered or "war" in lowered or "ops" in lowered:
            return self._answer_mvp(data)  # 최고 타자
        if "뜨거" in question or "최근" in question or "hot" in lowered:
            return self._answer_hot_team(data)  # 최근 가장 잘하는 팀
        return self._answer_team(question, data, evidence)  # 기본: 특정 팀 분석

    def _answer_team(
        self,
        question: str,
        data: dict[str, pd.DataFrame],
        evidence: list[Evidence],
    ) -> dict[str, Any]:
        """질문에 팀명이 있으면 그 팀, 없으면 검색 1순위(없으면 1위 팀) 분석."""
        requested_team = self._find_team_in_question(question, data["standings"])
        docs = self._build_documents(data)
        team_doc = None
        if requested_team:
            team_doc = next(
                (
                    item
                    for item in docs
                    if item.payload.get("type") == "team"
                    and item.payload.get("team") == requested_team
                ),
                None,
            )
        if not team_doc:
            team_doc = next((item for item in evidence if item.payload.get("type") == "team"), None)
        if not team_doc and not data["standings"].empty:
            team_doc = docs[0]
        if not team_doc:
            return {
                "title": "No team data is available.",
                "summary": "Run the daily update job first, then ask again.",
                "bullets": [],
            }

        payload = team_doc.payload
        title = f"{payload['team']}는 현재 {int(payload['rank'])}위, 승률 {payload['win_rate']:.3f}입니다."
        summary = (
            f"핵심 근거는 승패 품질과 득실차입니다. "
            f"{int(payload['wins'])}승 {int(payload['losses'])}패, 최근 흐름은 "
            f"{payload['recent']}, 득실차는 {int(payload['run_diff']):+d}입니다."
        )
        return {
            "title": title,
            "summary": summary,
            "bullets": [
                f"시즌 전적: {int(payload['wins'])}승 {int(payload['draws'])}무 {int(payload['losses'])}패",
                f"득실: {payload['runs_for']}득점 / {payload['runs_against']}실점",
                f"최근 흐름: {payload['recent']} ({payload['streak']})",
            ],
        }

    @staticmethod
    def _find_team_in_question(question: str, standings: pd.DataFrame) -> str | None:
        if standings.empty:
            return None
        for team in standings[TEAM_COL].dropna().astype(str).tolist():
            if team and team in question:
                return team
        return None

    def _answer_mvp(self, data: dict[str, pd.DataFrame]) -> dict[str, Any]:
        """WARProxy·OPS 상위 5명을 뽑아 MVP형 타자를 답한다."""
        hitters = data["hitters"]
        if hitters.empty:
            return {
                "title": "No hitter metric data is available.",
                "summary": "Build kbo_hitter_metrics first.",
                "bullets": [],
            }
        top = hitters.sort_values(["WARProxy", "OPS"], ascending=False).head(5)
        leader = top.iloc[0]
        return {
            "title": f"{leader['Player']}이 현재 데이터 기준 가장 강한 MVP형 타자입니다.",
            "summary": (
                f"WARProxy {leader['WARProxy']}, OPS {leader['OPS']}, "
                f"홈런 {int(leader['HR'])}, 타점 {int(leader['RBI'])}을 근거로 봅니다."
            ),
            "bullets": [
                f"{row.Player} ({row.Team}) - WARProxy {row.WARProxy}, OPS {row.OPS}"
                for row in top.itertuples()
            ],
        }

    def _answer_hot_team(self, data: dict[str, pd.DataFrame]) -> dict[str, Any]:
        """'최근10경기' 문자열에서 승률을 계산해 가장 뜨거운 팀을 답한다."""
        standings = data["standings"]
        if standings.empty:
            return {
                "title": "No standings data is available.",
                "summary": "Run the daily update job first.",
                "bullets": [],
            }
        rows = []
        for _, row in standings.iterrows():
            rate = self._recent_win_rate(str(row.get(RECENT_COL, "")))
            rows.append((rate, row))
        rows.sort(key=lambda item: item[0], reverse=True)
        rate, row = rows[0]
        return {
            "title": f"{row[TEAM_COL]}가 최근 10경기 기준 가장 뜨겁습니다.",
            "summary": f"최근 흐름은 {row[RECENT_COL]}, 최근 승률은 {rate:.3f}입니다.",
            "bullets": [
                f"{item[1][TEAM_COL]} - {item[1][RECENT_COL]} ({item[0]:.3f})"
                for item in rows[:5]
            ],
        }

    @staticmethod
    def _terms(text: str) -> set[str]:
        """영문/숫자/한글 토큰화 (2글자 이상만 사용)."""
        return {term for term in re.split(r"[^0-9A-Za-z가-힣]+", text.lower()) if len(term) >= 2}

    @staticmethod
    def _intent_bonus(query: str, doc: Evidence) -> int:
        """질문 키워드가 문서 유형(team/hitter)과 맞으면 가산점."""
        payload_type = doc.payload.get("type")
        if payload_type == "team" and any(word in query for word in ["팀", "순위", "강", "왜"]):
            return 3
        if payload_type == "hitter" and any(word in query.lower() for word in ["mvp", "ops", "war", "선수", "홈런"]):
            return 3
        return 0

    @staticmethod
    def _recent_win_rate(text: str) -> float:
        """'7승 3패' 같은 최근10경기 문자열 -> 승률(0~1)."""
        wins = re.search(r"(\d+)승", text)
        losses = re.search(r"(\d+)패", text)
        w = int(wins.group(1)) if wins else 0
        l = int(losses.group(1)) if losses else 0
        return w / (w + l) if w + l else 0.0

    @staticmethod
    def _safe_number(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            if isinstance(value, float) and math.isnan(value):
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _evidence_to_dict(item: Evidence) -> dict[str, Any]:
        return {
            "title": item.title,
            "body": item.body,
            "source": item.source,
            "score": item.score,
            "payload": item.payload,
        }

    @staticmethod
    def _data_sources(data: dict[str, pd.DataFrame]) -> dict[str, int]:
        return {name: len(df) for name, df in data.items()}
