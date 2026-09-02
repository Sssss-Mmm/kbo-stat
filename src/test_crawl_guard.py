"""크롤러가 파서 사고를 조용히 넘기지 않는지 확인한다.

막으려는 사고: 외부 사이트 구조가 바뀌어 파서가 0행을 뱉었는데, 크롤러가
그걸 print 하고 넘어가 CSV 는 낡은 채 남고 크론은 exit 0 으로 성공을 기록하는 것.
일일 갱신은 overwrite=True 로 도는 경로라 여기서 걸리지 않으면 아무도 모른다.

실행: python test_crawl_guard.py
"""
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import csv_guard
import crawl_kbo_hitter
import crawl_kbo_pitcher

GOOD = pd.DataFrame({"선수명": ["김도영", "노시환"], "팀명": ["KIA", "한화"], "AVG": [0.347, 0.301]})


def _setup(mod, tmp, filename, fetch):
    """모듈의 RAW_DIR 과 fetch_year 를 임시본으로 바꾸고 원복 함수를 준다."""
    old_dir, old_fetch = mod.RAW_DIR, mod.fetch_year
    mod.RAW_DIR, mod.fetch_year = tmp, fetch
    path = tmp / filename
    GOOD.to_csv(path, index=False, encoding="utf-8-sig")
    return path, lambda: (setattr(mod, "RAW_DIR", old_dir), setattr(mod, "fetch_year", old_fetch))


def check_empty_parse_is_refused(mod, filename):
    """파서가 0행을 뱉으면 기존 CSV 를 덮지 않고 예외로 알린다."""
    with tempfile.TemporaryDirectory() as d:
        path, restore = _setup(mod, Path(d), filename, lambda s, y: pd.DataFrame())
        try:
            try:
                mod.crawl(start=2026, end=2026, overwrite=True)
            except csv_guard.EmptyDatasetError:
                pass
            else:
                raise AssertionError(f"{mod.__name__}: 0행 저장이 그냥 통과했다")
            after = pd.read_csv(path, encoding="utf-8-sig")
            assert len(after) == 2, f"{mod.__name__}: 기존 CSV 가 훼손됐다 ({len(after)}행)"
        finally:
            restore()


def check_fetch_error_is_loud(mod, filename):
    """네트워크 실패는 연도별로 모았다가 끝에서 크게 실패한다(조용한 exit 0 금지)."""
    def boom(session, year):
        raise RuntimeError("연결 실패")

    with tempfile.TemporaryDirectory() as d:
        _, restore = _setup(mod, Path(d), filename, boom)
        try:
            try:
                mod.crawl(start=2026, end=2026, overwrite=True)
            except RuntimeError as exc:
                assert "2026" in str(exc), f"{mod.__name__}: 실패 연도가 메시지에 없다 — {exc}"
            else:
                raise AssertionError(f"{mod.__name__}: 수집 실패인데 정상 종료했다")
        finally:
            restore()


def check_good_data_still_saves(mod, filename):
    """정상 데이터는 그대로 저장된다(가드가 과하게 막지 않는다)."""
    fresh = pd.concat([GOOD, GOOD.assign(선수명=["박민우", "손아섭"])], ignore_index=True)
    with tempfile.TemporaryDirectory() as d:
        path, restore = _setup(mod, Path(d), filename, lambda s, y: fresh)
        try:
            mod.crawl(start=2026, end=2026, overwrite=True)
            assert len(pd.read_csv(path, encoding="utf-8-sig")) == 4, f"{mod.__name__}: 저장 안 됨"
        finally:
            restore()


if __name__ == "__main__":
    targets = [(crawl_kbo_hitter, "kbo_2026.csv"), (crawl_kbo_pitcher, "kbo_pitcher_2026.csv")]
    for mod, name in targets:
        check_empty_parse_is_refused(mod, name)
        check_fetch_error_is_loud(mod, name)
        check_good_data_still_saves(mod, name)
    print(f"ok: 크롤러 가드 자체 점검 통과 (모듈 {len(targets)}개 × 3항목)")
