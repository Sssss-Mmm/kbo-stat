"""CSV 저장 전 검사를 모아둔 공용 가드.

두 가지를 막는다.
  1) 0행 저장 — 파서가 깨져도 exit 0 으로 끝나 CSV 가 헤더만 남는 사고
  2) 정합성 위반 — 행 수는 맞는데 값이 깨진 데이터 (DR-07 V-01~08)

외부 사이트 구조가 바뀌면 파서는 예외 대신 빈 DataFrame 을 뱉는다. 그대로
to_csv 하면 멀쩡하던 CSV 가 헤더만 남고, 파이프라인은 exit 0 으로 끝나
아무도 모른다. 저장 직전에 여기서 막고 에러로 알린다.

경기가 없어 0행이 정상인 데이터(비시즌, 우천취소일 투구 존)는 애초에
저장하지 않고 건너뛰거나 allow_empty=True 로 명시한다.
"""

import re
from pathlib import Path

import pandas as pd


class EmptyDatasetError(RuntimeError):
    """행 수 0 이라 기존 CSV 덮어쓰기를 거부했을 때."""


class IntegrityError(RuntimeError):
    """행은 있으나 값이 정합성 규칙을 어겨 저장을 거부했을 때."""


KBO_TEAMS = {"KIA", "KT", "LG", "NC", "SSG", "두산", "롯데", "삼성", "키움", "한화"}

# 오늘의 10구단 이름이 그 시즌에도 그대로 맞는 최초 시즌. SK→SSG(2021),
# 넥센→키움(2019) 개명 이후만 KBO_TEAMS 로 이름을 검사할 수 있다. 그 이전
# 시즌에는 SK·넥센·해태·현대·쌍방울처럼 사라진 구단명이 정상이라 whitelist 로
# 잡으면 멀쩡한 과거 데이터를 거부한다 — 팀 수와 승패 합으로 대신 검증한다.
CURRENT_NAMES_SINCE = 2021


def expected_team_count(season: int | None) -> int | None:
    """그 시즌의 1군 구단 수. 모르는 시즌(None)은 검사하지 않는다.

    1982년 6팀에서 KT 창단(2015)으로 10팀이 됐다. 10팀 고정으로 두면 2012년
    8팀 순위표가 V-01 로 거부돼 과거 시즌 백필이 아예 불가능하다.
    """
    if season is None:
        return None
    if season >= 2015:
        return 10
    if season >= 2013:  # NC 창단
        return 9
    if season >= 1991:  # 쌍방울 창단
        return 8
    if season >= 1986:  # 빙그레 창단
        return 7
    return 6


def _season_from_path(path: Path) -> int | None:
    """파일명 끝의 4자리 연도. 없으면 None(시즌 무관 파일)."""
    match = re.search(r"(\d{4})(?!.*\d{4})", path.stem)
    if not match:
        return None
    season = int(match.group(1))
    return season if 1982 <= season <= 2100 else None


# 전일 대비 행 수가 이 비율 아래로 줄면 수집 사고로 본다(V-08).
ROW_DROP_LIMIT = 0.5


def _fail(rule: str, msg: str) -> None:
    raise IntegrityError(f"{rule}: {msg}")


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    """검사용 숫자 변환.

    크롤러는 HTML 표를 그대로 DataFrame 으로 만들기 때문에 모든 칸이 문자열이다
    (crawl_kbo_team_rank._parse_table). 반면 CSV 를 다시 읽으면 pandas 가 int/float
    로 추론한다. 그래서 저장된 파일로만 검사하면 통과하고 실제 크롤 결과에서는
    터진다 — 2026-09-01 일일 갱신이 V-02 로 죽은 원인이 이것이었다
    (sorted(['1','10','2',...]) != [1,...,10]).
    """
    return pd.to_numeric(df[col], errors="coerce")


def _check_team_rank(df: pd.DataFrame, season: int | None = None) -> None:
    """순위표 — 그 시즌 팀 수, 순위 유일, 승패무 합, 승률 범위(V-01~05)."""
    teams = expected_team_count(season)
    if teams is not None and len(df) != teams:
        _fail("V-01", f"{season} 시즌 팀 수가 {teams}가 아니다 (={len(df)})")
    count = teams if teams is not None else len(df)
    _check_ranks(_num(df, "순위").dropna().astype(int).tolist(), count)
    bad = df[_num(df, "승") + _num(df, "패") + _num(df, "무") != _num(df, "경기")]
    if len(bad):
        _fail("V-03", f"승+패+무 != 경기: {bad['팀명'].tolist()}")
    if not _num(df, "승률").between(0, 1).all():
        _fail("V-04", "승률이 0~1 범위 밖")
    _check_teams(df, "팀명", season)


def _check_ranks(values: list[int], count: int) -> None:
    """순위가 정상적인 등수 매기기인지(V-02).

    동순위를 허용해야 한다 — 과거 시즌에는 공동 순위가 실제로 나온다
    (1991년 [1,2,3,4,5,6,6,8]). 그래서 "1~N 중복 없이" 로는 멀쩡한 데이터를
    거부한다. 대신 등수 매기기의 형태를 본다: 오름차순으로 정렬했을 때 각 값은
    직전 값과 같거나(공동 순위) 제 자리 번호와 같아야 한다(공동 순위 다음은
    건너뛴 번호로 이어진다).

    행 순서는 믿지 않는다 — 순위 컬럼이 승률순이 아닌 시즌이 있다(1992년은
    포스트시즌 결과가 반영돼 승률 1위가 2위로 적혀 있다).

    서로 다른 값이 하나뿐이면 파서가 같은 값을 모든 행에 넣은 것으로 본다.
    10팀 전체가 공동 1위인 시즌은 없다.
    """
    if len(values) != count:
        _fail("V-02", f"순위 값이 {count}개가 아니다 (={len(values)})")
    ranks = sorted(values)
    if ranks[0] != 1:
        _fail("V-02", f"1위가 없다 ({ranks})")
    if ranks[-1] > count:
        _fail("V-02", f"순위가 팀 수({count})를 넘는다 ({ranks})")
    for i in range(1, len(ranks)):
        if ranks[i] not in (ranks[i - 1], i + 1):
            _fail("V-02", f"순위가 등수 형태가 아니다 ({ranks})")
    if count >= 2 and len(set(ranks)) < 2:
        _fail("V-02", f"순위가 모두 같다 — 파싱이 깨졌다 ({ranks})")


def _check_teams(df: pd.DataFrame, col: str, season: int | None = None) -> None:
    """팀명이 알려진 10구단인지(V-05).

    개명 이전 시즌은 건너뛴다(CURRENT_NAMES_SINCE). 대신 빈 이름은 어느
    시즌이든 파싱이 깨진 신호라 항상 거부한다.
    """
    names = set(df[col].dropna().astype(str).str.strip().unique())
    if "" in names:
        _fail("V-05", f"{col} 에 빈 팀명이 있다")
    if season is not None and season < CURRENT_NAMES_SINCE:
        return
    unknown = names - KBO_TEAMS
    if unknown:
        _fail("V-05", f"모르는 팀명 {sorted(unknown)}")


def _check_schedule(df: pd.DataFrame, season: int | None = None) -> None:
    """일정 — 날짜 파싱과 팀명(V-06, V-05)."""
    if pd.to_datetime(df["Date"], errors="coerce").isna().any():
        _fail("V-06", "파싱 불가한 Date 가 있다")
    for col in ("home_team", "away_team"):
        if col in df.columns:
            _check_teams(df, col, season)


def _check_hitters(df: pd.DataFrame, season: int | None = None) -> None:
    """타자 — 비율 지표 범위(V-07). 결측은 허용, 음수·이상치만 거부."""
    for col in ("AVG", "OBP", "SLG", "OPS"):
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) and not vals.between(0, 5).all():
                _fail("V-07", f"{col} 가 0~5 범위 밖")


def _check_team_rank_history(df: pd.DataFrame, season: int | None = None) -> None:
    """순위 스냅샷 이력 — 날짜별 누적이라 행 수 제약은 없다. 팀명과 승패무만 본다."""
    _check_teams(df, "팀명", season)
    bad = df[_num(df, "승") + _num(df, "패") + _num(df, "무") != _num(df, "경기")]
    if len(bad):
        _fail("V-03", f"승+패+무 != 경기 {len(bad)}행")


# 파일명 접두사 → 검사 함수. 가장 긴 접두사가 이긴다(history 가 team_rank 보다 우선).
CHECKS = {
    "kbo_team_rank_history_": _check_team_rank_history,
    "kbo_team_rank_": _check_team_rank,
    "kbo_schedule_": _check_schedule,
    "kbo_naver_hitters_": _check_hitters,
    "kbo_hitter_metrics_": _check_hitters,
}


def _validate(df: pd.DataFrame, path: Path) -> None:
    """파일명에 맞는 정합성 검사를 고른다. 규칙 없는 파일은 통과."""
    for prefix in sorted(CHECKS, key=len, reverse=True):
        if path.name.startswith(prefix):
            CHECKS[prefix](df, _season_from_path(path))
            return


def _check_row_drop(df: pd.DataFrame, path: Path) -> None:
    """전일 대비 행 수 급감 방어(V-08)."""
    if not path.exists():
        return
    try:
        before = len(pd.read_csv(path, encoding="utf-8-sig"))
    except Exception:
        return  # 기존 파일을 못 읽으면 비교를 포기하고 저장은 허용한다.
    if before and len(df) < before * ROW_DROP_LIMIT:
        _fail("V-08", f"행 수가 {before} → {len(df)} 로 급감 ({path.name})")


def save_csv(
    df: pd.DataFrame,
    path: Path,
    *,
    prefix: str = "",
    allow_empty: bool = False,
    extra: str = "",
    check: bool = True,
) -> pd.DataFrame:
    """검사를 통과할 때만 CSV 로 저장한다.

    0행이거나 정합성 규칙을 어기면 덮어쓰지 않고 예외를 던진다.
    백필처럼 행 수 급감이 정상인 경우에만 check=False 로 끈다.
    """
    tag = f"{prefix} " if prefix else ""
    if len(df) == 0 and not allow_empty:
        existing = "existing file kept" if path.exists() else "no existing file"
        raise EmptyDatasetError(
            f"{tag}refusing to write {path.name} with 0 rows — "
            f"upstream parse likely broke ({existing})"
        )

    if len(df) and check:
        _check_row_drop(df, path)
        _validate(df, path)

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    suffix = f" {extra}" if extra else ""
    print(f"{tag}saved {path.name} rows={len(df)}{suffix}")
    return df


def _selfcheck() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "kbo_naver_hitters_2026.csv"

        # 정상 저장
        good = pd.DataFrame({"선수명": ["김하성"], "G": [100]})
        save_csv(good, path, prefix="[test]")
        assert path.exists() and len(pd.read_csv(path)) == 1

        # 0행이면 예외 + 기존 파일 보존
        empty = pd.DataFrame(columns=["선수명", "G"])
        try:
            save_csv(empty, path, prefix="[test]")
        except EmptyDatasetError as exc:
            assert "0 rows" in str(exc) and "existing file kept" in str(exc), exc
        else:
            raise AssertionError("0행 저장이 막히지 않았다")
        assert len(pd.read_csv(path)) == 1, "기존 CSV 가 빈 데이터로 덮어써졌다"

        # 정상 0행은 통과(비시즌/경기 없는 날)
        off_season = Path(tmp) / "off_season.csv"
        save_csv(empty, off_season, allow_empty=True)
        assert off_season.exists() and len(pd.read_csv(off_season)) == 0

        # 정합성: 깨진 순위표는 거부된다(V-01~05)
        rank_path = Path(tmp) / "kbo_team_rank_2026.csv"
        teams = sorted(KBO_TEAMS)
        ok_rank = pd.DataFrame({
            "순위": range(1, 11), "팀명": teams,
            "경기": [100] * 10, "승": [50] * 10, "패": [45] * 10, "무": [5] * 10,
            "승률": [0.526] * 10,
        })
        save_csv(ok_rank, rank_path)

        for rule, broken in [
            ("V-01", ok_rank.head(9)),
            ("V-02", ok_rank.assign(순위=[1] * 10)),
            ("V-03", ok_rank.assign(승=[99] * 10)),
            ("V-04", ok_rank.assign(승률=[1.5] * 10)),
            ("V-05", ok_rank.assign(팀명=["없는팀"] + teams[1:])),
        ]:
            try:
                save_csv(broken, rank_path)
            except (IntegrityError, EmptyDatasetError) as exc:
                assert rule in str(exc) or "V-08" in str(exc), f"{rule} 대신 {exc}"
            else:
                raise AssertionError(f"{rule} 위반이 통과됐다")
        assert len(pd.read_csv(rank_path)) == 10, "깨진 데이터가 저장됐다"

        # 크롤러는 HTML 을 그대로 담아 전 컬럼이 문자열이다. 위 ok_rank 는 숫자라
        # 이 경로를 못 덮었고, 그래서 V-02 가 실제 크롤에서만 터졌다.
        str_rank = ok_rank.astype(str)
        assert str_rank["순위"].tolist() == [str(i) for i in range(1, 11)]
        save_csv(str_rank, rank_path)
        try:
            save_csv(str_rank.assign(순위=["1"] * 10), rank_path)
        except IntegrityError as exc:
            assert "V-02" in str(exc), exc
        else:
            raise AssertionError("문자열 순위의 V-02 위반이 통과됐다")

        # V-08: 행 수 급감 거부
        try:
            save_csv(ok_rank.head(4).assign(순위=range(1, 5)), rank_path)
        except IntegrityError as exc:
            assert "V-08" in str(exc), exc
        else:
            raise AssertionError("행 수 급감이 통과됐다")

        # 규칙 없는 파일은 그대로 통과
        save_csv(pd.DataFrame({"a": [1]}), Path(tmp) / "unknown_2026.csv")

        _selfcheck_seasons(Path(tmp))

    print("csv_guard selfcheck OK")


def _selfcheck_seasons(tmp: Path) -> None:
    """시즌별 팀 수·팀명 검사 불변식.

    핵심은 두 방향이다: 과거 시즌 백필이 통과해야 하고, **현재 시즌 보호가
    그대로여야** 한다(과거를 열어주려다 일일 갱신 방어가 풀리면 본전도 못 찾는다).
    """
    def rank_df(teams: list[str], games: int = 144) -> pd.DataFrame:
        n = len(teams)
        return pd.DataFrame({
            "순위": range(1, n + 1), "팀명": teams,
            "경기": [games] * n, "승": [70] * n, "패": [70] * n, "무": [games - 140] * n,
            "승률": [0.500] * n,
        })

    현재10 = sorted(KBO_TEAMS)
    과거8 = ["KIA", "LG", "SK", "넥센", "두산", "롯데", "삼성", "한화"]
    과거6 = ["삼성", "롯데", "OB", "해태", "MBC", "삼미"]

    # 동순위(V-02): 과거 시즌에 실제로 나온다
    _check_ranks([1, 2, 3, 4, 5, 6, 6, 8], 8)
    _check_ranks([1, 1, 3, 4], 4)
    _check_ranks([1, 2, 2, 2, 5], 5)
    for bad in ([1] * 8, [1, 2, 3, 4, 5, 6, 7, 9], [2, 3, 4, 5, 6, 7, 8, 9],
                [1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 5, 6, 6, 7]):
        try:
            _check_ranks(bad, 8)
        except IntegrityError:
            pass
        else:
            raise AssertionError(f"잘못된 순위 {bad} 가 통과했다")

    # 시즌 팀 수 표
    assert expected_team_count(2026) == 10 and expected_team_count(2015) == 10
    assert expected_team_count(2014) == 9 and expected_team_count(2013) == 9
    assert expected_team_count(2012) == 8 and expected_team_count(1991) == 8
    assert expected_team_count(1990) == 7 and expected_team_count(1986) == 7
    assert expected_team_count(1985) == 6 and expected_team_count(1982) == 6
    assert expected_team_count(None) is None

    # 파일명에서 시즌 추출
    assert _season_from_path(Path("kbo_team_rank_2012.csv")) == 2012
    assert _season_from_path(Path("kbo_team_rank_history_2026.csv")) == 2026
    assert _season_from_path(Path("kbo_team_rank_probe.csv")) is None

    # 과거 시즌: 8팀·사라진 구단명이 통과한다
    save_csv(rank_df(과거8), tmp / "kbo_team_rank_2012.csv")
    save_csv(rank_df(과거6, games=80), tmp / "kbo_team_rank_1982.csv")
    save_csv(
        pd.DataFrame({"Date": ["2012-04-07"], "home_team": ["SK"], "away_team": ["넥센"]}),
        tmp / "kbo_schedule_2012.csv",
    )

    # 과거 시즌이라도 팀 수가 어긋나면 거부한다(백필을 열어도 검사는 남는다)
    for season, teams, bad in [(2012, 과거8, 7), (1982, 과거6, 5)]:
        try:
            save_csv(rank_df(teams[:bad]), tmp / f"kbo_team_rank_{season}.csv")
        except IntegrityError as exc:
            assert "V-01" in str(exc), exc
        else:
            raise AssertionError(f"{season} 팀 수 부족이 통과했다")

    # 어느 시즌이든 빈 팀명은 거부한다
    try:
        save_csv(rank_df(["", *과거8[1:]]), tmp / "kbo_team_rank_2012.csv")
    except IntegrityError as exc:
        assert "V-05" in str(exc), exc
    else:
        raise AssertionError("빈 팀명이 통과했다")

    # 현재 시즌 보호는 그대로다: 9팀도, 모르는 팀명도 거부
    cur = tmp / "kbo_team_rank_2026.csv"
    save_csv(rank_df(현재10), cur)
    for label, broken in [
        ("V-01", rank_df(현재10[:9])),
        ("V-05", rank_df(["없는팀", *현재10[1:]])),
    ]:
        try:
            save_csv(broken, cur)
        except IntegrityError as exc:
            assert label in str(exc), f"{label} 대신 {exc}"
        else:
            raise AssertionError(f"현재 시즌 {label} 위반이 통과했다")
    assert len(pd.read_csv(cur)) == 10, "현재 시즌 CSV 가 깨진 데이터로 덮어써졌다"


if __name__ == "__main__":
    _selfcheck()
