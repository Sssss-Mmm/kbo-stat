"""
보존된 네이버 박스스코어 원본(crawl_naver_boxscore.py)을 경기별 투수·타자 기록으로 푼다.

    data/processed/naver_box_pitchers_{season}.csv
    data/processed/naver_box_batters_{season}.csv

경기마다 가장 최근 원본 파일 하나만 쓴다. 값은 원본 그대로 옮기고 고치지 않는다.
모든 행에 출처를 단다: Source(naver_boxscore) · FetchedAt · RawFile · Sha256.
이 값은 '네이버가 보여 주는 기록'이다 — KBO 공식 사이트로 교차검증한 값(kbo_*)과 섞지 않는다.

TeamSumMismatch: 그 경기·그 팀에서 선수 합계가 같은 원본의 팀 합계와 다른 항목(쉼표 구분, 맞으면 빈 값).
  투수: 아웃·타자수·피안타·피홈런·4사구·삼진·실점 vs teamPitchingBoxscore
  타자: 타수·안타·득점·타점·도루 vs battersBoxscore.{away,home}Total
자책점은 넣지 않는다 — 팀 자책은 규칙상(9.16(i)) 개인 자책 합보다 작을 수 있다(2025 2경기).
어긋난 항목은 원본 자체가 맞지 않는 것이라 그 항목의 비교 기준으로 쓰지 않는다(verify_player_games).

필드 대응·팀 합계 규칙은 naver_box_parse.py 에 있다(DB 적재 단계도 같은 파서로 다시 대조한다).

Usage:
    python src/build_naver_box_games.py --season 2025
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import csv_guard
from build_zone_metrics import PROCESSED_DIR
from crawl_naver_boxscore import RECORD_DIR
from naver_box_parse import BATTER_FIELDS, PITCHER_FIELDS, inning_outs, parse_envelope  # noqa: F401 (inning_outs 재노출)

PROVENANCE = ["Season", "GameId", "Source", "FetchedAt", "RawFile", "Sha256", "GameStatusCode"]


def latest_files(season: int, root: Path | None = None) -> list[Path]:
    base = (root or RECORD_DIR) / str(season)
    return [files[-1] for d in sorted(base.glob("*")) if d.is_dir() and (files := sorted(d.glob("*.json")))]


def parse_record(path: Path, root: Path | None = None) -> tuple[list[dict], list[dict]]:
    """원본 파일 하나 → (투수 행들, 타자 행들). 해석·무결성 검사는 naver_box_parse 한 곳에서."""
    rel = path.relative_to(root or RECORD_DIR).as_posix()
    return parse_envelope(json.loads(path.read_text(encoding="utf-8")), rel)


def build_frames(season: int, root: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    pitchers, batters = [], []
    for path in latest_files(season, root):
        p, b = parse_record(path, root)
        pitchers += p
        batters += b
    return pd.DataFrame(pitchers), pd.DataFrame(batters)


def build(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not latest_files(season):
        raise SystemExit(f"[naver-box] {season} 박스스코어 원본이 없습니다 — crawl_naver_boxscore.py 로 먼저 받으세요")
    pitchers, batters = build_frames(season)
    for name, frame in (("pitchers", pitchers), ("batters", batters)):
        frame = frame.astype({c: "Int64" for c in frame.columns if c in {"Outs", *PITCHER_FIELDS.values(),
                                                                          *BATTER_FIELDS.values()}})
        csv_guard.save_csv(frame, PROCESSED_DIR / f"naver_box_{name}_{season}.csv", prefix="[naver-box]", extra=(
            f"games={frame['GameId'].nunique() if len(frame) else 0} "
            f"team_sum_mismatch_games={frame.loc[frame['TeamSumMismatch'].ne(''), 'GameId'].nunique() if len(frame) else 0}"))
    return pitchers, batters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    build(parser.parse_args().season)


if __name__ == "__main__":
    main()
