"""
FanGraphs KBO leaderboard crawler.

Strategy:
  1. Fetch HTML page, extract full JSON from __NEXT_DATA__ script tag.
  2. If that fails with 403, fall back to Selenium (headless Chrome).

One HTML request per season returns all Standard + Advanced stats
combined (no separate tabs needed).

Usage:
    python crawl.py                          # 2002–2025, qualified batters
    python crawl.py --start 2015 --end 2023
    python crawl.py --qual 0                 # all players (no PA floor)
    python crawl.py --selenium               # force Selenium from the start
"""

import json
import time
import random
import argparse
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://www.fangraphs.com/leaders/international/kbo"
DROP_COLS = {"teamid", "playerids", "minormasterid"}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def _extract_from_html(html: str) -> list[dict]:
    """Next.js 의 __NEXT_DATA__ JSON 에서 kbo/data 쿼리 결과(레코드 배열)를 꺼낸다."""
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        raise ValueError("__NEXT_DATA__ script tag not found")
    data = json.loads(script.text)
    queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
    for q in queries:
        if "kbo/data" in str(q.get("queryKey", "")):
            return q["state"]["data"]
    raise ValueError("kbo/data query not found in __NEXT_DATA__")


def _build_session(ua: str) -> requests.Session:
    """주어진 User-Agent 로 브라우저처럼 보이는 requests 세션을 만든다."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def fetch_season_requests(season: int, qual: str = "y", max_retries: int = 3) -> pd.DataFrame:
    """requests 로 한 시즌을 받는다. 403 등 실패 시 UA/대기를 바꿔 재시도한다."""
    params = {"type": "0", "season": str(season), "qual": qual}
    for attempt in range(max_retries):
        ua = random.choice(USER_AGENTS)
        s = _build_session(ua)
        wait = 3 + attempt * 5 + random.uniform(0, 2)
        if attempt > 0:
            print(f"    retry {attempt} (waiting {wait:.0f}s) …")
            time.sleep(wait)
        try:
            resp = s.get(BASE_URL, params=params, timeout=30)
            if resp.status_code == 403:
                print(f"    403 on attempt {attempt+1}")
                continue
            resp.raise_for_status()
            records = _extract_from_html(resp.text)
            if not records:
                return pd.DataFrame()
            df = pd.DataFrame(records)
            df = df.drop(columns=[c for c in DROP_COLS if c in df.columns])
            return df
        except Exception as e:
            print(f"    attempt {attempt+1} error: {e}")
    raise RuntimeError(f"All {max_retries} attempts failed for season {season}")


def fetch_season_selenium(season: int, qual: str = "y") -> pd.DataFrame:
    """requests 가 막힐 때 헤드리스 크롬으로 페이지를 띄워 같은 JSON 을 긁어온다."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")

    url = f"{BASE_URL}?type=0&season={season}&qual={qual}"
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(url)
        # wait for the data table to appear
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table tr:nth-child(2)"))
        )
        html = driver.page_source
        records = _extract_from_html(html)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df = df.drop(columns=[c for c in DROP_COLS if c in df.columns])
        return df
    finally:
        driver.quit()


def fetch_season(season: int, qual: str = "y", use_selenium: bool = False) -> pd.DataFrame:
    """한 시즌 수집. 기본은 requests, 실패하면 Selenium 으로 자동 폴백한다."""
    if use_selenium:
        return fetch_season_selenium(season, qual)
    try:
        return fetch_season_requests(season, qual)
    except RuntimeError:
        print(f"  requests failed, switching to Selenium for season {season}")
        return fetch_season_selenium(season, qual)


def crawl(start: int = 2002, end: int = 2025, qual: str = "y",
          delay: float = 3.0, use_selenium: bool = False):
    """연도 범위를 돌며 시즌별 CSV 를 저장한다(이미 있으면 건너뜀)."""
    for season in range(start, end + 1):
        out_path = RAW_DIR / f"kbo_{season}.csv"
        if out_path.exists():
            print(f"  skip  {out_path.name}")
            continue
        try:
            df = fetch_season(season, qual, use_selenium)
            if df.empty:
                print(f"  empty {season} — no data returned")
            else:
                df.to_csv(out_path, index=False)
                print(f"  saved {out_path.name}  ({len(df)} players, {len(df.columns)} cols)")
        except Exception as e:
            print(f"  ERROR {season}: {e}")
        jitter = delay + random.uniform(0, delay * 0.3)
        time.sleep(jitter)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=2002)
    parser.add_argument("--end", type=int, default=2025)
    parser.add_argument("--qual", default="y",
                        help="'y'=qualified, '0'=all players (default: y)")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="base delay in seconds between requests (default: 3)")
    parser.add_argument("--selenium", action="store_true",
                        help="use Selenium (headless Chrome) instead of requests")
    args = parser.parse_args()

    print(f"Crawling KBO data {args.start}–{args.end}  qual={args.qual}  "
          f"{'[Selenium]' if args.selenium else '[requests]'}")
    crawl(args.start, args.end, args.qual, args.delay, args.selenium)
    print("Done.")
