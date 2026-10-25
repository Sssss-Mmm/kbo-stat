"""KBO 공식 사이트가 이 환경에서 받아지는지 확인하는 프로브.

용도: 일일 순위 스냅샷을 GitHub Actions 로 옮길 수 있는지 판단한다.
순위 스냅샷은 하루 거르면 영영 복구할 수 없는 유일한 데이터라(KBO 순위
페이지는 현재 순위만 보여준다) PC 가 꺼져 있어도 돌 곳이 필요한데,
국내 사이트가 해외 클라우드 IP 를 막는 경우가 있어 먼저 확인해야 한다.

로컬과 러너에서 같은 스크립트를 돌려 비교한다.
  둘 다 성공        → Actions 로 옮겨도 된다
  로컬만 성공       → 러너 IP/지역 차단. 다른 방법을 써야 한다
  둘 다 실패        → 사이트나 파서 쪽 변경. 차단 문제가 아니다

데이터를 저장하지 않는다. 읽기만 한다.
2026-10-24 부터 KBO 요청은 src/kbo_access.py 스위치(KBO_AUTOMATED_FETCH_APPROVED=1, 승인 후)로만 나간다.
실행: python scripts/probe_kbo_reachable.py
"""

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import crawl_kbo_team_rank as tr  # noqa: E402
import csv_guard  # noqa: E402
import kbo_access  # noqa: E402 — KBO 요청은 승인 전 차단
from fetch_guard import Guard  # noqa: E402

# ipify(제3자)는 KBO 승인과 따로 승인한다 — KBO 승인만으로 다른 외부 사이트에 요청하지 않는다(Codex 교차검증).
ipify = Guard("PROBE_EGRESS_IP_APPROVED", "ipify(나가는 IP 확인)")


def egress_ip() -> str:
    """나가는 IP. 차단 여부를 나중에 대조하려면 어디서 나갔는지 알아야 한다."""
    if not ipify.allowed():
        return f"(생략 — {ipify.env}=1 일 때만 확인)"
    try:
        return ipify.requests.get("https://api.ipify.org", timeout=10).text.strip()
    except requests.RequestException as exc:
        return f"(확인 실패: {type(exc).__name__})"


def main() -> int:
    if not kbo_access.allowed():  # 승인 전에는 아무 외부 요청 없이 끝낸다
        print(f"판정: 중단 — KBO 자동 요청 비활성화(승인 전) — 허용하려면 {kbo_access.ENV}=1")
        return 2
    print(f"egress IP : {egress_ip()}")
    print(f"target    : {tr.TEAM_RANK_URL}")

    started = time.monotonic()
    try:
        response = kbo_access.requests.get(tr.TEAM_RANK_URL, headers=tr.HEADERS, timeout=20)
    except kbo_access.KboFetchDisabled as exc:
        print(f"\n판정: 중단 — {exc}")
        return 2
    except requests.RequestException as exc:
        print(f"\n판정: 실패 — 요청 자체가 안 됐다 ({type(exc).__name__}: {exc})")
        return 1
    elapsed = time.monotonic() - started

    print(f"HTTP      : {response.status_code} ({elapsed:.2f}s, {len(response.content):,} bytes)")
    if response.status_code != 200:
        print(f"\n판정: 실패 — HTTP {response.status_code}. 차단이거나 페이지가 바뀌었다.")
        return 1

    df = tr._parse_table(response.text)
    print(f"파싱      : {len(df)}행 {len(df.columns)}열")
    if df.empty:
        # 200 인데 표가 없으면 차단 페이지(캡차·안내)를 받았을 가능성이 높다.
        print(f"본문 앞부분: {response.text[:200]!r}")
        print("\n판정: 실패 — 200 이지만 순위 표가 없다. 차단 페이지이거나 파서가 깨졌다.")
        return 1

    print(f"팀        : {df['팀명'].tolist()}")
    try:
        csv_guard._validate(df, Path("kbo_team_rank_probe.csv"))
    except csv_guard.IntegrityError as exc:
        print(f"\n판정: 실패 — 표는 받았지만 정합성 검사가 거부했다 ({exc})")
        return 1

    print("\n판정: 성공 — 이 환경에서 KBO 순위 표를 정상적으로 받고 검증까지 통과했다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
