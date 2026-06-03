"""
스탯티즈(statiz.co.kr) 타자 시즌 스탯 크롤러.

사용법:
    # .env 파일에 계정 정보 입력 후:
    python crawl_statiz.py                    # 2010-2025
    python crawl_statiz.py --start 2015 --end 2023
    python crawl_statiz.py --probe            # 로그인 테스트 + 페이지 구조 확인
"""

import os
import re
import time
import random
import argparse
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "statiz"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://www.statiz.co.kr"
LOGIN_URL = f"{BASE}/member/handle.php"
STAT_URL  = f"{BASE}/stats/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE,
}


# ── 로그인 ────────────────────────────────────────────────────────────────────

def login(user_id: str, user_pw: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)

    payload = {
        "act":          "loginJWT",
        "retPage":      "",
        "location":     "",
        "userID":       user_id,
        "userPassword": user_pw,
        "autoLogin":    "Y",
    }
    resp = s.post(LOGIN_URL, data=payload, timeout=15)
    resp.raise_for_status()

    # 로그인 성공 여부: 쿠키에 인증 토큰이 있어야 함
    if not any(k for k in s.cookies.keys() if k not in ("PHPSESSID",)):
        # 일부 사이트는 PHPSESSID만 있어도 로그인됨 — 실제 페이지로 확인
        test = s.get(f"{STAT_URL}?m=main&opt=0&year=2024", timeout=15)
        if len(test.text) < 400:
            raise RuntimeError("로그인 실패 — 아이디/비밀번호를 확인하세요.")

    print(f"  로그인 성공  cookies={list(s.cookies.keys())}")
    return s


# ── 페이지 파싱 ───────────────────────────────────────────────────────────────

def _parse_table(html: str) -> pd.DataFrame | None:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    # 선수 데이터가 있는 테이블: 행이 가장 많은 것
    best = max(tables, key=lambda t: len(t.find_all("tr")), default=None)
    if best is None or len(best.find_all("tr")) < 3:
        return None

    rows = best.find_all("tr")
    cols = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    data = [
        [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
        for row in rows[1:]
        if row.find_all(["th", "td"])
    ]
    if not data:
        return None
    return pd.DataFrame(data, columns=cols if cols else None)


def _total_pages(html: str) -> int:
    """페이지네이션에서 총 페이지 수 파악."""
    soup = BeautifulSoup(html, "lxml")
    pager = soup.find(class_=re.compile(r"pager|pagination|page_nav", re.I))
    if not pager:
        return 1
    nums = re.findall(r"\d+", pager.get_text())
    return max((int(n) for n in nums), default=1)


# ── 시즌 수집 ─────────────────────────────────────────────────────────────────

def fetch_season(session: requests.Session, year: int,
                 opt: int = 0, pp: int = 100) -> pd.DataFrame:
    """
    opt=0: 타자, opt=1: 투수
    pp: 페이지당 행 수 (100이 최대인 경우 많음)
    """
    frames = []
    page = 1
    while True:
        params = {
            "m":    "main",
            "opt":  opt,
            "year": year,
            "sopt": 0,
            "pp":   pp,
            "page": page,
        }
        resp = session.get(STAT_URL, params=params, timeout=20)
        resp.raise_for_status()

        if len(resp.text) < 400:
            # 로그인 만료
            raise RuntimeError("세션 만료 — 재로그인 필요")

        df = _parse_table(resp.text)
        if df is None or df.empty:
            break

        df.insert(0, "season", year)
        frames.append(df)

        total = _total_pages(resp.text)
        if page >= total:
            break
        page += 1
        time.sleep(random.uniform(1.0, 2.0))

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ── 메인 ─────────────────────────────────────────────────────────────────────

def probe(session: requests.Session):
    """로그인 후 페이지 구조 출력 (개발용)."""
    resp = session.get(f"{STAT_URL}?m=main&opt=0&year=2023&pp=100", timeout=20)
    soup = BeautifulSoup(resp.text, "lxml")
    tables = soup.find_all("table")
    print(f"  status={resp.status_code}  len={len(resp.text)}  tables={len(tables)}")
    for i, t in enumerate(tables):
        rows = t.find_all("tr")
        if len(rows) > 2:
            cols = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
            print(f"  table[{i}] rows={len(rows)-1}  cols={cols[:8]}")

    # 페이지네이션 확인
    pager = soup.find(class_=re.compile(r"pager|pagination|page_nav", re.I))
    if pager:
        print("  pager:", pager.get_text()[:100])


def crawl(session: requests.Session, start: int, end: int, delay: float = 2.0):
    for year in range(start, end + 1):
        out = RAW_DIR / f"statiz_{year}.csv"
        if out.exists():
            print(f"  skip  {out.name}")
            continue
        try:
            df = fetch_season(session, year)
            if df.empty:
                print(f"  empty {year}")
            else:
                df.to_csv(out, index=False)
                print(f"  saved {out.name}  ({len(df)} rows, {len(df.columns)} cols)")
        except Exception as e:
            print(f"  ERROR {year}: {e}")
        time.sleep(delay + random.uniform(0, 1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2010)
    parser.add_argument("--end",   type=int, default=2025)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--probe", action="store_true",
                        help="로그인 후 페이지 구조만 출력하고 종료")
    args = parser.parse_args()

    user_id = os.getenv("STATIZ_ID")
    user_pw = os.getenv("STATIZ_PW")
    if not user_id or not user_pw:
        raise SystemExit("ERROR: .env 파일에 STATIZ_ID, STATIZ_PW를 입력하세요.")

    print("스탯티즈 로그인 중 …")
    session = login(user_id, user_pw)

    if args.probe:
        probe(session)
    else:
        print(f"수집 범위: {args.start}–{args.end}")
        crawl(session, args.start, args.end, args.delay)
        print("Done.")
