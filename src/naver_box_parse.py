"""
네이버 박스스코어 원본 봉투(envelope) → 경기별 투수·타자 행. 표준 라이브러리만 쓴다.

수집(crawl_naver_boxscore)·CSV 가공(build_naver_box_games)·DB 적재(backend/migrate_records)가 같은
해시·무결성 규칙과 같은 파서를 쓰도록 한 곳에 둔다 — 적재 단계가 원본을 다시 풀어 가공 CSV 와 대조한다.

필드 대응(2025 원본에서 확인): pa=상대 타자수, bf=투구수, inn="5 ⅔" 꼴 이닝,
bbhp=4사구(볼넷+사구), bb=볼넷.
"""
import hashlib
import json

SOURCE = "naver_boxscore"
PITCHER_FIELDS = {"pa": "BF", "ab": "AB", "hit": "H", "hr": "HR", "bb": "BB", "bbhp": "BBHP", "kk": "SO",
                  "r": "R", "er": "ER", "bf": "NP"}
BATTER_FIELDS = {"ab": "AB", "hit": "H", "hr": "HR", "bb": "BB", "kk": "SO", "run": "R", "rbi": "RBI", "sb": "SB"}
# 자책점은 넣지 않는다 — 팀 자책은 규칙상(9.16(i)) 개인 자책 합보다 작을 수 있다(2025 2경기).
PITCHER_TEAM_SUM = {"Outs": "inn", "BF": "pa", "H": "hit", "HR": "hr", "BBHP": "bbhp", "SO": "kk", "R": "r"}
BATTER_TEAM_SUM = {"AB": "ab", "H": "hit", "R": "run", "RBI": "rbi", "SB": "sb"}


def payload_hash(payload) -> str:
    """정렬 JSON 의 sha256 — 봉투의 sha256 이 이 값이어야 한다."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def inning_outs(text) -> int | None:
    """'5 ⅔' → 17, '0 ⅓' → 1, '3' → 9. 모르는 형태는 None(짐작하지 않는다)."""
    parts = str(text).replace("⅓", " ⅓").replace("⅔", " ⅔").split()
    if not parts or len(parts) > 2:
        return None
    frac = {"⅓": 1, "⅔": 2}
    if len(parts) == 2 and parts[1] not in frac:
        return None
    if not parts[0].isdigit():
        return None if len(parts) == 2 or parts[0] not in frac else frac[parts[0]]
    return int(parts[0]) * 3 + (frac[parts[1]] if len(parts) == 2 else 0)


def check_envelope(envelope: dict, rel: str) -> None:
    """저장 뒤 손상·변조되거나 다른 경기·시즌 폴더에 놓인 원본은 출처가 맞는 값처럼 쓰지 않는다.
    rel: record/ 아래 상대 경로('2025/20250719HHKT0/....json')."""
    parts = rel.replace("\\", "/").split("/")
    if (payload_hash(envelope.get("payload")) != envelope.get("sha256") or envelope.get("source") != SOURCE
            or parts[:2] != [str(envelope.get("season")), envelope.get("game_id")]):
        raise ValueError(f"[naver-box] 원본 무결성 불일치 — {rel} (해시·출처·경기/시즌 경로 확인)")


def parse_envelope(envelope: dict, rel: str) -> tuple[list[dict], list[dict]]:
    """원본 봉투 하나 → (투수 행들, 타자 행들). 무결성 검사 후 값을 그대로 옮기고 TeamSumMismatch 를 붙인다."""
    check_envelope(envelope, rel)
    record = envelope["payload"]["recordData"]
    info = record.get("gameInfo") or {}
    meta = {"Season": envelope["season"], "GameId": envelope["game_id"], "Source": envelope["source"],
            "FetchedAt": envelope["fetched_at"], "RawFile": rel,
            "Sha256": envelope["sha256"], "GameStatusCode": info.get("statusCode")}
    pitchers, batters = [], []
    for side in ("away", "home"):
        team = info.get("aName" if side == "away" else "hName")
        side_p = [{**meta, "Side": side, "Team": team, "Order": i + 1, "PlayerId": int(p["pcode"]),
                   "Player": p.get("name"), "IP": p.get("inn"), "Outs": inning_outs(p.get("inn")),
                   "Decision": p.get("wls") or "", **{v: p.get(k) for k, v in PITCHER_FIELDS.items()}}
                  for i, p in enumerate((record.get("pitchersBoxscore") or {}).get(side) or [])]
        team_p = (record.get("teamPitchingBoxscore") or {}).get(side) or {}
        _mark(side_p, {col: inning_outs(team_p.get(key)) if col == "Outs" else team_p.get(key)
                       for col, key in PITCHER_TEAM_SUM.items()})
        side_b = [{**meta, "Side": side, "Team": team, "BatOrder": b.get("batOrder"), "Pos": b.get("pos"),
                   "PlayerId": int(b["playerCode"]), "Player": b.get("name"),
                   **{v: b.get(k) for k, v in BATTER_FIELDS.items()},
                   # 이닝별 결과 칸(inn1~)의 '고4' = 고의4구. 자동 고의4구는 공이 없어 투구 데이터에 안 나온다.
                   "IBB": sum(1 for k, v in b.items() if k.startswith("inn") and v == "고4")}
                  for b in (record.get("battersBoxscore") or {}).get(side) or []]
        team_b = (record.get("battersBoxscore") or {}).get(f"{side}Total") or {}
        _mark(side_b, {col: team_b.get(key) for col, key in BATTER_TEAM_SUM.items()})
        pitchers += side_p
        batters += side_b
    return pitchers, batters


def _mark(rows: list[dict], team: dict) -> None:
    """선수 합계 != 팀 합계 인 항목을 rows 에 TeamSumMismatch 로 붙인다. 팀 값·선수 값이 비면 불일치로 본다."""
    bad = [col for col in team
           if team[col] is None or any(r.get(col) is None for r in rows) or sum(r[col] for r in rows) != team[col]]
    for r in rows:
        r["TeamSumMismatch"] = ",".join(bad)
