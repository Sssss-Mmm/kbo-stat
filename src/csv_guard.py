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

from pathlib import Path

import pandas as pd


class EmptyDatasetError(RuntimeError):
    """행 수 0 이라 기존 CSV 덮어쓰기를 거부했을 때."""


class IntegrityError(RuntimeError):
    """행은 있으나 값이 정합성 규칙을 어겨 저장을 거부했을 때."""


KBO_TEAMS = {"KIA", "KT", "LG", "NC", "SSG", "두산", "롯데", "삼성", "키움", "한화"}

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


def _check_team_rank(df: pd.DataFrame) -> None:
    """순위표 — 10팀, 순위 유일, 승패무 합, 승률 범위(V-01~05)."""
    if len(df) != 10:
        _fail("V-01", f"팀 수가 10이 아니다 (={len(df)})")
    ranks = sorted(_num(df, "순위").dropna().astype(int).tolist())
    if ranks != list(range(1, 11)):
        _fail("V-02", f"순위가 1~10 유일하지 않다 ({ranks})")
    bad = df[_num(df, "승") + _num(df, "패") + _num(df, "무") != _num(df, "경기")]
    if len(bad):
        _fail("V-03", f"승+패+무 != 경기: {bad['팀명'].tolist()}")
    if not _num(df, "승률").between(0, 1).all():
        _fail("V-04", "승률이 0~1 범위 밖")
    _check_teams(df, "팀명")


def _check_teams(df: pd.DataFrame, col: str) -> None:
    """팀명이 알려진 10구단인지(V-05)."""
    unknown = set(df[col].dropna().unique()) - KBO_TEAMS
    if unknown:
        _fail("V-05", f"모르는 팀명 {sorted(unknown)}")


def _check_schedule(df: pd.DataFrame) -> None:
    """일정 — 날짜 파싱과 팀명(V-06, V-05)."""
    if pd.to_datetime(df["Date"], errors="coerce").isna().any():
        _fail("V-06", "파싱 불가한 Date 가 있다")
    for col in ("home_team", "away_team"):
        if col in df.columns:
            _check_teams(df, col)


def _check_hitters(df: pd.DataFrame) -> None:
    """타자 — 비율 지표 범위(V-07). 결측은 허용, 음수·이상치만 거부."""
    for col in ("AVG", "OBP", "SLG", "OPS"):
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) and not vals.between(0, 5).all():
                _fail("V-07", f"{col} 가 0~5 범위 밖")


def _check_team_rank_history(df: pd.DataFrame) -> None:
    """순위 스냅샷 이력 — 날짜별 누적이라 10행 제약은 없다. 팀명과 승패무만 본다."""
    _check_teams(df, "팀명")
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
            CHECKS[prefix](df)
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

    print("csv_guard selfcheck OK")


if __name__ == "__main__":
    _selfcheck()
