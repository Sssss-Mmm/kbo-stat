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

from services.csv_cache import file_versions


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

# 하락 서사에 쓸 월 표본 기준. 3월(3경기)이나 시즌 막바지 조각 달은 월 성적이 아니다.
MIN_MONTH_GAMES = 5
MIN_MONTHS = 4
# "왜 무너졌나" 류 시간축 질문 키워드.
DECLINE_WORDS = ("왜", "무너", "부진", "떨어", "언제부터")

# 검색된 근거가 0건일 때 쓰는 답변. 단정하지 않고, 이 답변기가 실제로 답할 수 있는 범위를 안내한다.
# (FR-09 AC2: 출처 없는 단정 금지)
NO_EVIDENCE_ANSWER: dict[str, Any] = {
    "title": "이 질문에 답할 근거를 찾지 못했습니다.",
    "summary": (
        "수집된 순위·경기·타자 지표 CSV에서 질문과 맞는 데이터를 찾지 못했습니다. "
        "이 답변기는 CSV에 있는 사실만 답할 수 있어, 근거 없이 단정하지 않습니다."
    ),
    "bullets": [
        "팀 순위·성적 - 예) 삼성 어때?",
        "WAR·OPS 상위 타자 - 예) MVP는 누구야?",
        "최근 상승세 팀 - 예) 최근 가장 뜨거운 팀은?",
    ],
}


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
        self._versions = {}

    def ask(self, question: str, season: int) -> dict[str, Any]:
        """질문 → 문서화 → 검색 → 답변 합성까지의 전체 파이프라인."""
        data = self._load(season)
        docs = self._build_documents(data)
        retrieved = self._retrieve(question, docs, limit=8)
        # 근거가 하나도 없으면 답변을 합성하지 않는다. 무관한 질문에 단정형 문장이 나가는 걸 여기 한 곳에서 막는다.
        answer = dict(self._synthesize(question, data, retrieved) if retrieved else NO_EVIDENCE_ANSWER)
        supporting = answer.pop("_evidence", [])
        return {
            "status": "success",
            "season": season,
            "question": question,
            "answer": answer,
            "evidence": [self._evidence_to_dict(item) for item in supporting],
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
        paths = {
            "standings": RAW_DIR / f"kbo_team_rank_{season}.csv",
            "team_games": PROCESSED_DIR / f"kbo_team_games_{season}.csv",
            "team_monthly": PROCESSED_DIR / f"kbo_team_monthly_{season}.csv",
            "hitters": PROCESSED_DIR / f"kbo_hitter_metrics_{season}.csv",
        }
        version = file_versions(list(paths.values()))
        if season in self._cache and self._versions.get(season) == version:
            return self._cache[season]
        data = {name: self._read_csv(path) for name, path in paths.items()}
        self._cache[season] = data
        self._versions[season] = version
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
                runs_for = int(team_games["RunsFor"].sum()) if not team_games.empty else None
                runs_against = int(team_games["RunsAgainst"].sum()) if not team_games.empty else None
                run_diff = runs_for - runs_against if runs_for is not None else None
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
        lowered = question.lower()
        team = self._find_team_in_question(question, data["standings"])
        if any(word in question for word in ("부상", "연봉", "트레이드", "라인업", "예측", "확률", "내년", "내일", "우승")):
            return NO_EVIDENCE_ANSWER
        if team and re.search(r"홈(?!런)|원정|방문", question):
            return self._answer_split(question, team, data)
        if any(word in lowered for word in ("mvp", "war", "ops", "홈런", "타율", "타점")):
            metric = "WARProxy"
            if "mvp" not in lowered and "war" not in lowered:
                metric = next((column for word, column in (("ops", "OPS"), ("홈런", "HR"), ("타율", "AVG"), ("타점", "RBI")) if word in lowered), "WARProxy")
            # 팀·선수를 명시한 질문에 리그 전체 1위를 답하지 않는다.
            hitters = data["hitters"]
            if not hitters.empty:
                players = [name for name in hitters["Player"].dropna().unique() if str(name) in question]
                players = [name for name in players if not any(name != other and name in other for other in players)]
                if players:
                    hitters = hitters[hitters["Player"].isin(players)]
                elif team:
                    hitters = hitters[hitters["Team"] == team]
                elif not any(word in lowered for word in ("mvp", "순위", "상위", "최고", "1위", "누구")):
                    return NO_EVIDENCE_ANSWER
            return self._answer_mvp({**data, "hitters": hitters}, metric)
        if team and any(word in question for word in DECLINE_WORDS):
            decline = self._answer_decline(question, data)
            if decline:
                return decline
        if not team and ("뜨거" in question or "최근" in question or "hot" in lowered):
            return self._answer_hot_team(data)
        if team and any(word in question for word in ("어때", "성적", "순위", "강", "왜", "최근", "승률", "득실", "몇 위", "몇위")):
            return self._answer_team(question, data, evidence)
        return NO_EVIDENCE_ANSWER

    def _support(self, data: dict, teams=(), players=()) -> list[Evidence]:
        return [doc for doc in self._build_documents(data)
                if (doc.payload.get("type") == "team" and doc.payload.get("team") in teams)
                or (doc.payload.get("type") == "hitter" and doc.payload.get("player") in players)]

    def _answer_split(self, question: str, team: str, data: dict) -> dict:
        if re.search(r"홈(?!런)", question) and re.search(r"원정|방문", question):
            home = self._answer_split("홈", team, data)
            away = self._answer_split("원정", team, data)
            if not home.get("_evidence") or not away.get("_evidence"):
                return NO_EVIDENCE_ANSWER
            return {"title": f"{team}의 홈·원정 성적입니다.",
                    "summary": f"홈: {home['summary']} 원정: {away['summary']}",
                    "bullets": home["bullets"] + away["bullets"],
                    "_evidence": home["_evidence"] + away["_evidence"]}
        games = data["team_games"]
        required = {"Team", "HomeAway", "Win", "Loss", "Draw", "Date"}
        if games.empty or not required.issubset(games.columns):
            return NO_EVIDENCE_ANSWER
        home = "홈" in question
        label = "홈" if home else "원정"
        aliases = ("home", "홈") if home else ("away", "원정", "방문")
        rows = games[(games["Team"] == team) & games["HomeAway"].str.lower().isin(aliases)]
        if rows.empty:
            return NO_EVIDENCE_ANSWER
        wins, losses, draws = (int(rows[col].sum()) for col in ("Win", "Loss", "Draw"))
        rate = wins / (wins + losses) if wins + losses else None
        summary = f"{len(rows)}경기 {wins}승 {draws}무 {losses}패, 승률 {rate:.3f}입니다." if rate is not None else f"{len(rows)}경기 {draws}무로 승률을 계산할 수 없습니다."
        through = str(rows["Date"].max())
        payload = {"type": "split", "team": team, "split": label, "games": len(rows),
                   "wins": wins, "losses": losses, "draws": draws, "win_rate": rate, "through": through}
        evidence = Evidence(f"{team} {label} 성적", summary, "kbo_team_games", 0, payload)
        return {"title": f"{team}의 {label} 성적입니다.", "summary": summary,
                "bullets": [f"{through} 경기까지 수집된 결과 기준 · 무승부는 승률 계산에서 제외"],
                "_evidence": [evidence]}

    def _answer_decline(
        self,
        question: str,
        data: dict[str, pd.DataFrame],
    ) -> dict[str, Any] | None:
        """'왜 무너졌나' 류 질문에 월별 성적으로 답한다: 최고였던 달 -> 무너진 달 -> 지금 흐름.

        인과를 세울 수 없으면 None을 반환해 기존 팀 답변기로 넘긴다.
        팀을 못 찾거나, 월 표본이 모자라거나, 최악의 달이 최고의 달보다 앞서거나,
        최악의 달 뒤에 회복한 달이 있는(= 지금까지 이어지는 하락이 아닌) 경우다.
        없는 서사를 지어내는 것보다 스냅샷이 낫다.
        """
        monthly = data["team_monthly"]
        team = self._find_team_in_question(question, data["standings"])
        if not team or monthly.empty:
            return None

        rows = monthly[(monthly["Team"] == team) & (monthly["Games"] >= MIN_MONTH_GAMES)]
        rows = rows.sort_values("Month")
        if len(rows) < MIN_MONTHS:
            return None

        best = rows.loc[rows["WinRate"].idxmax()]
        worst = rows.loc[rows["WinRate"].idxmin()]
        # "무너져서 지금 이 순위다"는 슬럼프가 마지막 달까지 이어질 때만 참이다.
        # 최악의 달이 정점보다 앞서거나, 그 뒤에 회복한 달이 있으면 지나간 슬럼프다.
        if int(worst["Month"]) <= int(best["Month"]) or int(worst["Month"]) != int(rows["Month"].max()):
            return None

        stand = data["standings"]
        stand_row = stand[stand[TEAM_COL] == team]
        now = stand_row.iloc[0] if not stand_row.empty else None

        title = (
            f"{team}는 {int(best['Month'])}월이 정점이었고, "
            f"{int(worst['Month'])}월에 무너졌습니다."
        )
        summary = (
            f"{int(best['Month'])}월에는 {int(best['Wins'])}승 {int(best['Losses'])}패"
            f"(승률 {float(best['WinRate']):.3f}, 득실 {int(best['RunDiff']):+d})로 가장 좋았습니다. "
            f"그러다 {int(worst['Month'])}월에 {int(worst['Wins'])}승 {int(worst['Losses'])}패"
            f"(승률 {float(worst['WinRate']):.3f}, 득실 {int(worst['RunDiff']):+d})로 낮아졌습니다. "
            f"이 수치만으로 부진의 원인을 단정할 수는 없습니다."
        )
        if now is not None:
            summary += (
                f" 별도로 최근 10경기는 {now[RECENT_COL]}, "
                f"현재 {now[STREAK_COL]}로 {int(now[RANK_COL])}위입니다."
            )

        bullets = [
            f"{int(row.Month)}월: {int(row.Wins)}승 {int(row.Losses)}패 "
            f"(승률 {float(row.WinRate):.3f}, 득실 {int(row.RunDiff):+d})"
            for row in rows.itertuples()
        ]
        if now is not None:
            bullets.append(
                f"현재: {int(now[RANK_COL])}위, {int(now[WINS_COL])}승 {int(now[LOSSES_COL])}패, "
                f"게임차 {now.get('게임차')}"
            )
        supporting = self._support(data, teams=[team])
        supporting += [Evidence(
            f"{team} {int(row.Month)}월 성적", bullet, "kbo_team_monthly", 0,
            {"type": "monthly", "team": team, "month": int(row.Month), "games": int(row.Games),
             "wins": int(row.Wins), "losses": int(row.Losses), "win_rate": float(row.WinRate), "run_diff": int(row.RunDiff)},
        ) for row, bullet in zip(rows.itertuples(), bullets)]
        return {"title": title, "summary": summary, "bullets": bullets, "_evidence": supporting}

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
        run_diff = payload['run_diff']
        run_summary = f"득실차는 {run_diff:+d}입니다." if run_diff is not None else "득실 기록은 수집되지 않았습니다."
        summary = (
            f"수집된 시즌 성적 기준으로 "
            f"{int(payload['wins'])}승 {int(payload['losses'])}패, 최근 흐름은 "
            f"{payload['recent']}, {run_summary}"
        )
        return {
            "title": title,
            "summary": summary,
            "_evidence": [team_doc],
            "bullets": [
                f"시즌 전적: {int(payload['wins'])}승 {int(payload['draws'])}무 {int(payload['losses'])}패",
                f"득실: {payload['runs_for']}득점 / {payload['runs_against']}실점" if run_diff is not None else "득실 기록 미수집",
                f"최근 흐름: {payload['recent']} ({payload['streak']})",
            ],
        }

    @staticmethod
    def _find_team_in_question(question: str, standings: pd.DataFrame) -> str | None:
        if standings.empty:
            return None
        for team in standings[TEAM_COL].dropna().astype(str).tolist():
            if team and team.lower() in question.lower():
                return team
        return None

    def _answer_mvp(self, data: dict[str, pd.DataFrame], metric: str = "WARProxy") -> dict[str, Any]:
        """WARProxy·OPS 상위 5명을 뽑아 MVP형 타자를 답한다."""
        hitters = data["hitters"]
        if hitters.empty:
            return {
                "title": "No hitter metric data is available.",
                "summary": "Build kbo_hitter_metrics first.",
                "bullets": [],
            }
        top = hitters.dropna(subset=[metric]).sort_values(list(dict.fromkeys([metric, "OPS"])), ascending=False).head(5)
        if top.empty:
            return NO_EVIDENCE_ANSWER
        leader = top.iloc[0]
        return {
            "title": f"{leader['Player']}의 {metric}가 조회 범위에서 가장 높습니다.",
            "_evidence": self._support(data, players=top["Player"].tolist()),
            "summary": (
                f"WARProxy(공식 WAR와 다른 근사 지표) {leader['WARProxy']}, OPS {leader['OPS']}, "
                f"홈런 {int(leader['HR'])}, 타점 {int(leader['RBI'])}을 근거로 봅니다."
            ),
            "bullets": [
                f"{row['Player']} ({row['Team']}) - {metric} {row[metric]}, OPS {row['OPS']}"
                for _, row in top.iterrows()
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
            "_evidence": self._support(data, teams=[item[1][TEAM_COL] for item in rows[:5]]),
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
        if payload_type == "hitter" and any(word in query.lower() for word in ["mvp", "ops", "war", "선수", "홈런", "타율", "타점"]):
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


if __name__ == "__main__":
    # 근거 0건 분기 자가검증: 무관한 질문은 단정하지 않고, 매칭되는 질문은 기존대로 답해야 한다.
    _svc = RagService()
    _svc._load = lambda season: _svc._cache[season]
    _svc._cache[1900] = {
        "standings": pd.DataFrame([{
            TEAM_COL: "삼성", RANK_COL: 1, WINS_COL: 60, LOSSES_COL: 40,
            DRAWS_COL: 2, WIN_RATE_COL: 0.6, RECENT_COL: "7승 3패", STREAK_COL: "3승",
        }]),
        "team_games": pd.DataFrame(),
        "team_monthly": pd.DataFrame(),
        "hitters": pd.DataFrame(),
    }

    _off = _svc.ask("김치찌개 맛집 알려줘", 1900)
    assert _off["evidence"] == [], _off["evidence"]
    assert _off["answer"] == NO_EVIDENCE_ANSWER, _off["answer"]
    assert "삼성" not in _off["answer"]["title"], "근거 없이 팀을 단정하면 안 된다"
    assert _off["status"] == "success" and set(_off) == {
        "status", "season", "question", "answer", "evidence", "data_sources"
    }, _off.keys()

    _on = _svc.ask("삼성 어때?", 1900)
    assert _on["evidence"], "팀명이 있으면 근거가 검색돼야 한다"
    assert "삼성" in _on["answer"]["title"], _on["answer"]

    # 공백만 있는 질문도 터지지 않고 근거 없음으로 떨어진다.
    assert _svc.ask("   ", 1900)["answer"] == NO_EVIDENCE_ANSWER

    # 하락 분기 자가검증. 5월 정점 -> 8월 붕괴 팀과, 계속 올라간 팀을 같이 넣는다.
    def _m(month, team, w, l, rd):
        return {
            "Season": 1901, "Month": month, "Team": team, "Games": w + l,
            "Wins": w, "Losses": l, "Draws": 0, "RunsFor": 0, "RunsAgainst": 0,
            "RunDiff": rd, "WinRate": w / (w + l),
        }

    _svc._cache[1901] = {
        "standings": pd.DataFrame([
            {TEAM_COL: "한화", RANK_COL: 8, WINS_COL: 49, LOSSES_COL: 63, DRAWS_COL: 3,
             WIN_RATE_COL: 0.438, RECENT_COL: "1승0무9패", STREAK_COL: "7패", "게임차": 19.5},
            {TEAM_COL: "삼성", RANK_COL: 1, WINS_COL: 69, LOSSES_COL: 44, DRAWS_COL: 3,
             WIN_RATE_COL: 0.611, RECENT_COL: "7승1무2패", STREAK_COL: "6승", "게임차": 0.0},
        ]),
        "team_games": pd.DataFrame(),
        "team_monthly": pd.DataFrame([
            _m(4, "한화", 9, 15, -23), _m(5, "한화", 16, 9, 61),
            _m(6, "한화", 10, 12, 15), _m(7, "한화", 9, 10, 11),
            _m(8, "한화", 3, 15, -65),
            _m(4, "삼성", 9, 15, -23), _m(5, "삼성", 10, 12, 5),
            _m(6, "삼성", 13, 9, 20), _m(7, "삼성", 16, 6, 40),
        ]),
        "hitters": pd.DataFrame(),
    }

    _why = _svc.ask("한화 초반 잘 치고 나가다가 왜 9등이랑 1게임차밖에 차이가 안나게 된걸까?", 1901)["answer"]
    assert "5월" in _why["summary"] and "8월" in _why["summary"], _why  # 시간축이 답에 있어야 한다
    assert "7패" in _why["summary"], _why  # 연패는 불릿이 아니라 원인 자리에
    assert _why["summary"].index("5월") < _why["summary"].index("8월"), _why  # 정점 -> 붕괴 순서

    # 하락이 아닌 팀(계속 상승)은 서사를 지어내지 않고 기존 팀 답변으로 떨어진다.
    _up = _svc.ask("삼성 왜 이래?", 1901)["answer"]
    assert "무너" not in _up["title"], _up
    assert "현재" in _up["title"], _up

    # 회귀(LG 케이스): 최악의 달(7월) 뒤에 회복한 달(8월)이 있으면 지나간 슬럼프이므로 서사를 세우지 않는다.
    _svc._cache[1902] = {
        "standings": pd.DataFrame([
            {TEAM_COL: "LG", RANK_COL: 3, WINS_COL: 62, LOSSES_COL: 50, DRAWS_COL: 3,
             WIN_RATE_COL: 0.554, RECENT_COL: "6승0무4패", STREAK_COL: "2승", "게임차": 7.0},
        ]),
        "team_games": pd.DataFrame(),
        "team_monthly": pd.DataFrame([
            _m(4, "LG", 16, 7, 30), _m(5, "LG", 13, 11, 5),
            _m(6, "LG", 12, 11, 3), _m(7, "LG", 7, 15, -20),
            _m(8, "LG", 13, 8, 18),
        ]),
        "hitters": pd.DataFrame(),
    }
    _recovered = _svc.ask("왜 LG가 강하지?", 1902)["answer"]
    assert "무너" not in _recovered["title"], _recovered
    assert "현재" in _recovered["title"], _recovered

    # 회귀: 월 데이터가 없는 시즌에서 "왜"가 섞여도 기존 팀 답변 그대로.
    assert "무너" not in _svc.ask("삼성 왜 강해?", 1900)["answer"]["title"]

    print("rag_service selfcheck ok")
