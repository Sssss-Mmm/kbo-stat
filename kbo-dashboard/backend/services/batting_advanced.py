"""P3-A 타자 고급 지표 — ISO · BABIP · BB% · K% 계산, PA 출처 선택, KBO 기록실 ↔ 선수 ID 연결.

설계: docs/P3A_DESIGN.md. 이 모듈은 순수 계산과 판정만 한다(API·DB 쓰기 없음). 실데이터 검증용 CSV 읽기(load_season)는 읽기 전용.

원칙
- 계산은 개수에서 Fraction 으로 정확히 한다. 반올림은 표시용 `display` 에서만(ROUND_HALF_UP, 순위표와 같은 규칙).
- 계산할 수 없으면 0 이 아니라 value=None + 상태 + 사유. 출처가 준 값은 status=source 로 따로 — 계산값처럼 보이지 않게.
- 상태: calculated(직접 계산) · source(외부 자료 값) · unavailable(필요한 자료 없음·불가능한 조합) · zero_denominator(분모 0).

자료(설계 1장)
- naver: 네이버 시즌 기록(선수 ID, AB·H·2B·3B·HR·BB·HBP·SO, 출처 BABIP) — PA·SF·SH 없음
- kbo:   KBO 기록실 시즌 기록(규정 이상, PA 있음, 선수 ID 없음 → 연결 필요)
- calc:  투구 데이터 계산 경기 기록의 시즌 합(SF·SH 있음, 경기별 완결 여부) — 현재 2025 만
"""
import math
from fractions import Fraction
from pathlib import Path

from services.season_service import round_half_up

CALCULATED, SOURCE, UNAVAILABLE, ZERO_DENOMINATOR = "calculated", "source", "unavailable", "zero_denominator"

# 지표 정의: 표시 자릿수 · 배율(%). 계산식은 아래 함수.
METRICS = {"iso": {"digits": 3, "scale": 1}, "babip": {"digits": 3, "scale": 1},
           "bb_pct": {"digits": 1, "scale": 100}, "k_pct": {"digits": 1, "scale": 100}}

PA_KBO, PA_ASSEMBLED = "kbo_record_pa", "assembled_pa"  # PA 출처(설계 2.3)
COUNT_KEYS = ("PA", "AB", "H", "2B", "3B", "HR", "BB", "HBP", "SO", "SF", "SH")  # 모순 검사 대상(이름 등 다른 열은 보지 않음)


def _count(v):
    """개수 하나: None·NaN·빈 값 → None. 숫자가 아니거나 정수가 아니면 ValueError(불가능한 값)."""
    if v is None or v == "" or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"숫자가 아닌 개수 {v!r}") from None
    if math.isinf(f) or not f.is_integer():
        raise ValueError(f"정수가 아닌 개수 {v}")
    return int(f)


def _safe_count(v):
    """연결 키·비교용: 잘못된 값이면 None(그 행은 연결하지 않는다) — 예외로 응답 전체를 실패시키지 않는다."""
    try:
        return _count(v)
    except ValueError:
        return None


def counts_problem(c: dict, needed: tuple[str, ...]) -> str | None:
    """필요한 개수가 다 있고 서로 모순이 없으면 None, 아니면 사유. 있는 값끼리만 모순을 본다."""
    try:
        vals = {k: _count(c.get(k)) for k in set(needed) | (set(COUNT_KEYS) & set(c))}
    except ValueError as exc:
        return f"불가능한 값: {exc}"
    missing = [k for k in needed if vals.get(k) is None]
    if missing:
        return "입력 없음: " + ", ".join(missing)
    neg = [k for k, v in vals.items() if v is not None and v < 0]
    if neg:
        return "불가능한 값: 음수 " + ", ".join(sorted(neg))
    g = vals.get
    rules = [  # (조건이 참이면 모순, 설명) — 해당 값이 모두 있을 때만 본다
        (("H", "AB"), lambda: g("H") > g("AB"), "H > AB"),
        (("HR", "H"), lambda: g("HR") > g("H"), "HR > H"),
        (("2B", "3B", "HR", "H"), lambda: g("2B") + g("3B") + g("HR") > g("H"), "2B+3B+HR > H"),
        (("H", "SO", "AB"), lambda: g("H") + g("SO") > g("AB"), "H+SO > AB"),  # 안타와 삼진은 서로 다른 타수
        (("PA", "AB", "BB", "HBP"), lambda: g("AB") + g("BB") + g("HBP") > g("PA"), "AB+BB+HBP > PA"),
    ]
    for keys, broken, text in rules:
        if all(g(k) is not None for k in keys) and broken():
            return f"불가능한 조합: {text}"
    return None


def _ints(c: dict, keys) -> dict:
    return {k: _count(c.get(k)) for k in keys}


def metric(name: str, value: Fraction | None, status: str, provenance: dict, reason: str | None = None,
           fraction: tuple[int, int] | None = None) -> dict:
    """지표 하나(JSON 직렬화 가능). value = 정밀값(float), display = 표시용 반올림값(% 지표는 ×100),
    fraction = 직접 계산일 때 정확한 분자·분모(value = 분자/분모 × 배율). Fraction 객체는 내보내지 않는다."""
    spec = METRICS[name]
    scaled = None if value is None else value * spec["scale"]
    return {"metric": name, "value": None if scaled is None else float(scaled),
            "display": round_half_up(scaled, spec["digits"]), "status": status, "reason": reason,
            "fraction": None if fraction is None else {"numerator": fraction[0], "denominator": fraction[1],
                                                         "scale": spec["scale"]},
            "provenance": provenance}


def _ratio(name: str, num: int, den: int, provenance: dict) -> dict:
    if den == 0:
        return metric(name, None, ZERO_DENOMINATOR, provenance, "분모 0", fraction=(num, den))
    return metric(name, Fraction(num, den), CALCULATED, provenance, fraction=(num, den))


def iso(c: dict, provenance: dict) -> dict:
    """ISO = SLG − AVG = (2B + 2·3B + 3·HR) / AB."""
    need = ("AB", "H", "2B", "3B", "HR")
    problem = counts_problem(c, need)
    if problem:
        return metric("iso", None, UNAVAILABLE, provenance, problem)
    v = _ints(c, need)
    return _ratio("iso", v["2B"] + 2 * v["3B"] + 3 * v["HR"], v["AB"], provenance)


def babip(c: dict, provenance: dict) -> dict:
    """BABIP = (H − HR) / (AB − SO − HR + SF). SF 가 없으면 계산하지 않는다(SF=0 가정 금지)."""
    need = ("AB", "H", "HR", "SO", "SF")
    problem = counts_problem(c, need)
    if problem:
        return metric("babip", None, UNAVAILABLE, provenance, problem)
    v = _ints(c, need)
    return _ratio("babip", v["H"] - v["HR"], v["AB"] - v["SO"] - v["HR"] + v["SF"], provenance)


def rate_per_pa(name: str, numerator_key: str, c: dict, pa: dict, provenance: dict) -> dict:
    """BB% · K% = 분자 / PA × 100. pa = select_pa() 결과."""
    if pa["value"] is None:
        return metric(name, None, UNAVAILABLE, provenance | {"pa_basis": None}, pa["reason"])
    merged = dict(c) | {"PA": pa["value"]}
    problem = counts_problem(merged, (numerator_key, "PA"))
    if problem is None and _count(merged[numerator_key]) > pa["value"]:
        problem = f"불가능한 조합: {numerator_key} > PA"
    if problem:
        return metric(name, None, UNAVAILABLE, provenance | {"pa_basis": pa["basis"]}, problem)
    return _ratio(name, _count(merged[numerator_key]), pa["value"], provenance | {"pa_basis": pa["basis"]})


def source_value(name: str, value, provenance: dict) -> dict:
    """출처가 준 값(예 네이버 BABIP). 계산값과 섞지 않도록 status=source. 숫자가 아니면 unavailable."""
    try:
        f = None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        f = None
    if f is None or math.isnan(f) or math.isinf(f):
        return metric(name, None, UNAVAILABLE, provenance, "출처 값 없음")
    return metric(name, Fraction(str(f)), SOURCE, provenance)


def source_babip(id_row: dict, provenance: dict) -> dict:
    """출처(네이버) BABIP. 출처는 분모가 0 일 수 있는 행(타수 0 등)에도 0.000 을 적는다(2007–2026 확인) — 정의되지 않는 값을
    0 으로 쓴 것이므로 그대로 쓰지 않는다. AB−SO−HR ≤ 0 이고 출처 값이 0 이면 unavailable. 그 밖에는 status=source."""
    m = source_value("babip", id_row.get("BABIP"), provenance)
    if m["status"] == SOURCE and not 0 <= m["value"] <= 1:  # BABIP 는 0–1 — 범위 밖 출처 값은 쓰지 않는다
        return metric("babip", None, UNAVAILABLE, provenance, f"출처 값이 범위(0–1) 밖: {m['value']}")
    if m["status"] == SOURCE and m["value"] == 0:
        try:
            ab, so, hr = (_count(id_row.get(k)) for k in ("AB", "SO", "HR"))
        except ValueError:
            ab = None
        if ab is None or so is None or hr is None or ab - so - hr <= 0:
            return metric("babip", None, UNAVAILABLE, provenance, "출처가 분모 0 가능 상황을 0 으로 표기 — 값으로 쓰지 않음")
    return m


# ---------------------------------------------------------------- 선수 연결(KBO 기록실 ↔ 선수 ID)

LINKED, AMBIGUOUS, UNMATCHED, TEAM_MISSING, RECORD_MISMATCH = (
    "linked", "ambiguous", "unmatched", "team_missing", "record_mismatch")


def _norm(s) -> str | None:
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return None
    t = "".join(str(s).split())
    return t or None


def link_kbo_records(kbo_rows: list[dict], id_rows: list[dict], season: int) -> list[dict]:
    """KBO 기록실 행마다 선수 ID 를 찾는다. 키 = (시즌, 이름, 팀, AB, H) — 이름·팀만으로는 같은 팀 동명이인이 섞인다.
    연결은 후보가 정확히 1명이고 그 ID 를 다른 기록실 행이 노리지 않을 때만. 연결 뒤 BB·SO 가 다르면 record_mismatch
    (그 PA 는 쓰지 않는다). 팀명이 없으면 연결하지 않는다. 이적 등으로 팀이 다르면 후보가 없어 unmatched.
    행 키: 기록실 {Season, 선수명, 팀명, AB, H, BB, SO, PA, HBP} · ID 자료 {Season, PlayerId, 선수명, 팀명, AB, H, BB, SO}."""
    def key(r):
        return (_safe_count(r.get("Season")), _norm(r.get("선수명")), _norm(r.get("팀명")), _safe_count(r.get("AB")),
                _safe_count(r.get("H")))

    candidates: dict[tuple, list[dict]] = {}
    for r in id_rows:
        k = key(r)
        if k[0] == season and None not in k and r.get("PlayerId") is not None:
            candidates.setdefault(k, []).append(r)
    out = []
    for i, r in enumerate(kbo_rows):
        k = key(r)
        if k[0] != season:
            out.append({"index": i, "player_id": None, "status": UNMATCHED, "reason": "시즌 불일치"})
        elif k[2] is None:
            out.append({"index": i, "player_id": None, "status": TEAM_MISSING, "reason": "기록실 행에 팀명 없음"})
        elif None in k:
            out.append({"index": i, "player_id": None, "status": UNMATCHED, "reason": "이름·AB·H 중 빈 값 또는 잘못된 값"})
        else:
            found = {int(c["PlayerId"]) for c in candidates.get(k, [])}
            if not found:
                out.append({"index": i, "player_id": None, "status": UNMATCHED,
                            "reason": "같은 시즌·이름·팀·AB·H 후보 없음(팀명 누락·이적·기록 차이 가능)"})
            elif len(found) > 1:
                out.append({"index": i, "player_id": None, "status": AMBIGUOUS, "reason": f"후보 {len(found)}명"})
            else:
                out.append({"index": i, "player_id": found.pop(), "status": LINKED, "reason": None})
    claimed: dict[int, int] = {}
    for link in out:
        if link["status"] == LINKED:
            claimed[link["player_id"]] = claimed.get(link["player_id"], 0) + 1
    by_id = {}
    for r in id_rows:
        if _safe_count(r.get("Season")) == season and r.get("PlayerId") is not None:
            by_id.setdefault(int(r["PlayerId"]), []).append(r)
    for link in out:
        if link["status"] != LINKED:
            continue
        pid = link["player_id"]
        if claimed[pid] > 1 or len(by_id.get(pid, [])) != 1:
            link.update(player_id=None, status=AMBIGUOUS, reason="같은 선수 ID 에 기록실 행이 여럿")
            continue
        r, idr = kbo_rows[link["index"]], by_id[pid][0]
        diff = [c for c in ("BB", "SO") if _safe_count(r.get(c)) is None or _safe_count(r.get(c)) != _safe_count(idr.get(c))]
        if diff:
            link.update(status=RECORD_MISMATCH, reason="연결 후 기록 불일치: " + ", ".join(diff))
    return out


# ---------------------------------------------------------------- PA 선택

def kbo_pa(kbo_row: dict | None, link: dict | None) -> dict | None:
    """검증된 KBO 기록실 PA: 연결 linked + PA 가 AB+BB+HBP 이상. 아니면 None."""
    if not kbo_row or not link or link["status"] != LINKED:
        return None
    if counts_problem(kbo_row, ("PA", "AB", "BB", "HBP")):
        return None
    return {"value": _count(kbo_row["PA"]), "basis": PA_KBO, "reason": None}


def calc_problem(id_row: dict, calc: dict | None) -> str | None:
    """투구 계산 시즌 합(SF·SH 의 유일한 출처)을 쓸 수 있으면 None, 아니면 사유.
    조건: 시즌 경기가 모두 완결(complete_games == games > 0) · 계산 AB·HBP 가 시즌 기록과 같다(같은 타석을 셌다).
    calc = {games, complete_games, AB, HBP, SF, SH}."""
    if not calc:
        return "SF·SH 자료 없음(투구 계산 없음)"
    try:
        games, done = _count(calc.get("games")), _count(calc.get("complete_games"))
    except ValueError as exc:
        return f"불가능한 값: {exc}"
    if not games:
        return "투구 계산 경기 없음"
    if done != games:
        return f"투구 계산 미완결 경기 {games - (done or 0)}개"
    problem = counts_problem(calc, ("AB", "HBP", "SF", "SH")) or counts_problem(id_row, ("AB", "HBP"))
    if problem:
        return problem
    if _count(calc["AB"]) != _count(id_row["AB"]) or _count(calc["HBP"]) != _count(id_row["HBP"]):
        return "투구 계산 AB·HBP 가 시즌 기록과 다름"
    return None


def assembled_pa(id_row: dict, calc: dict | None) -> tuple[dict | None, str | None]:
    """조립 PA = (시즌 기록) AB + BB + HBP + (투구 계산) SF + SH — 설계 보고서에서 KBO PA 와 완결 선수 100% 일치를 확인한 구성.
    반환 (PA 또는 None, 사유)."""
    problem = calc_problem(id_row, calc) or counts_problem(id_row, ("AB", "BB", "HBP"))
    if problem:
        return None, problem
    pa = sum(_count(id_row[k]) for k in ("AB", "BB", "HBP")) + _count(calc["SF"]) + _count(calc["SH"])
    return {"value": pa, "basis": PA_ASSEMBLED, "reason": None}, None


def select_pa(kbo_row: dict | None, link: dict | None, id_row: dict, calc: dict | None) -> dict:
    """PA 우선순위: ① 검증된 KBO 기록실 PA ② 완결 선수의 조립 PA ③ 없음(사유)."""
    pa = kbo_pa(kbo_row, link)
    if pa:
        return pa
    pa, why = assembled_pa(id_row, calc)
    if pa:
        return pa
    kbo_why = "KBO 기록실 PA 없음(규정 미달)" if not link else f"KBO 기록실 연결 {link['status']}"
    return {"value": None, "basis": None, "reason": f"PA 자료 없음 — {kbo_why}; {why}"}


# ---------------------------------------------------------------- 선수 시즌 · 리그

def player_season(id_row: dict, season: int, kbo_row: dict | None = None, link: dict | None = None,
                  calc: dict | None = None) -> dict:
    """한 선수의 시즌 지표 4개 + 출처 BABIP + 선택된 PA. id_row 는 네이버 시즌 기록 한 줄(선수 ID 자료)."""
    base = {"season": season, "scope": "player_season", "player_id": _count(id_row.get("PlayerId"))}
    naver = base | {"source": "naver_season_stats"}
    pa = select_pa(kbo_row, link, id_row, calc)
    out = {"pa": pa, "iso": iso(id_row, naver)}
    # BABIP: SF 는 투구 계산에만 있다 — 그 자료를 쓸 수 있을 때만 시즌 기록 개수 + 계산 SF
    why = calc_problem(id_row, calc)
    if why is None:
        out["babip"] = babip(dict(id_row) | {"SF": calc["SF"]}, base | {"source": "naver_season_stats+pitch_calc_sf"})
    else:
        out["babip"] = metric("babip", None, UNAVAILABLE, base | {"source": None}, why)
    out["babip_source"] = source_babip(id_row, naver | {"note": "네이버가 준 값 — 직접 계산 아님"})
    out["bb_pct"] = rate_per_pa("bb_pct", "BB", id_row, pa, naver)
    out["k_pct"] = rate_per_pa("k_pct", "SO", id_row, pa, naver)
    return out


def league_rate(name: str, numerator_key: str, players: list[dict]) -> dict:
    """리그 BB%·K% = 분자 합 / PA 합 — 선수별 비율의 평균이 아니다. 모집단 전원의 PA 가 확인될 때만 계산하고,
    일부만 확인되면 그 일부로 리그 값을 만들지 않는다(unavailable). players = [{counts..., 'pa': select_pa 결과}]."""
    prov = {"scope": "league_season", "population": len(players)}
    if not players:
        return metric(name, None, UNAVAILABLE, prov, "모집단 없음")
    missing = sum(1 for p in players if p["pa"]["value"] is None)
    if missing:
        return metric(name, None, UNAVAILABLE, prov, f"PA 미확인 선수 {missing}명 — 일부만으로 리그 지표를 만들지 않음")
    num = den = 0
    for p in players:
        problem = counts_problem(dict(p) | {"PA": p["pa"]["value"]}, (numerator_key, "PA"))
        if problem:
            return metric(name, None, UNAVAILABLE, prov, problem)
        num += _count(p[numerator_key])
        den += p["pa"]["value"]
    return _ratio(name, num, den, prov | {"basis": "sum_numerator/sum_pa"})


# ---------------------------------------------------------------- 실데이터 읽기(검증용, 읽기 전용)

def load_season(data_dir: Path, season: int) -> dict:
    """로컬 수집 자료에서 한 시즌 입력을 읽는다(쓰기 없음). 없는 파일은 빈 목록."""
    import pandas as pd

    def rows(path, **kw):
        return pd.read_csv(path, encoding="utf-8-sig", **kw).to_dict("records") if path.exists() else []

    naver = rows(data_dir / "processed" / f"kbo_naver_hitters_{season}.csv")
    kbo = rows(data_dir / "raw" / "kbo_official" / f"kbo_{season}.csv")
    calc = {}
    games = data_dir / "processed" / f"kbo_player_games_{season}.csv"
    if games.exists():
        df = pd.read_csv(games, encoding="utf-8-sig")
        b = df[df["Role"] == "batter"]
        g = b.groupby("PlayerId").agg(games=("GameId", "count"), complete_games=("StatsComplete", "sum"),
                                      AB=("AB", "sum"), HBP=("HBP", "sum"), SF=("SF", "sum"), SH=("SH", "sum"))
        calc = {int(pid): {k: int(v) for k, v in r.items()} for pid, r in g.iterrows()}
    return {"naver": naver, "kbo": kbo, "calc": calc}
