"""필수 데이터 준비 상태 — entrypoint(기동 전)와 /ready 가 같이 쓴다.

2026-10-24 장애: Docker Desktop 이 WSL 경로가 연결되기 약 0.8초 전에 컨테이너를 띄워 /app/data 가 빈 tmpfs 로
붙었다. v1 은 CSV 가 없으면 직전 시즌으로 조용히 폴백하고 /health 는 200 이라, 빈 화면으로 서비스됐다.

구분: 마운트(tmpfs 자리표시 / 마운트됨 / 마운트 없음=이미지 스냅샷) · 필수 파일(없음 / 비어 있음 / 읽기 실패 / 정상) ·
선택 파일(없어도 준비 완료 — 그 화면만 '자료 없음'). 필수 = 활성 시즌의 핵심 4개(순위·일정·팀경기·타자지표).

    python data_check.py   # 0 = 준비 완료, 1 = 아님. 사유를 한 줄씩 출력
"""
import os
import sys
from pathlib import Path

from utils import PROCESSED_DIR, current_season

DATA_DIR = PROCESSED_DIR.parent
REQUIRED = ("raw/kbo_official/kbo_team_rank_{s}.csv", "raw/kbo_official/kbo_schedule_{s}.csv",
            "processed/kbo_team_games_{s}.csv", "processed/kbo_hitter_metrics_{s}.csv")
OPTIONAL = ("processed/kbo_naver_hitters_{s}.csv", "processed/kbo_naver_pitchers_{s}.csv",
            "processed/kbo_batter_zones_{s}.csv", "processed/kbo_pitcher_zones_{s}.csv",
            "processed/kbo_pitcher_arsenal_{s}.csv", "processed/kbo_count_baseball_{s}.csv")


def mount_state(path: Path = DATA_DIR, mountinfo: str = "/proc/self/mountinfo") -> str:
    """tmpfs(바인드 소스가 아직 없어 자리표시가 붙음) / mounted / image(마운트 없음 — 이미지에 구운 스냅샷)."""
    state = "image"
    try:
        lines = Path(mountinfo).read_text().splitlines()
    except OSError:
        return state
    for line in lines:  # 같은 자리에 여러 번 붙으면 마지막이 보인다
        f = line.split()
        if len(f) > 4 and f[4] == str(path):
            state = "tmpfs" if f[f.index("-") + 1] == "tmpfs" else "mounted"
    return state


def file_state(path: Path) -> str:
    """missing / empty(0바이트·헤더만) / unreadable / ok. 앞 두 줄만 읽는다(/ready 가 10초마다 부른다)."""
    if not path.exists():
        return "missing"
    try:
        with path.open(encoding="utf-8-sig") as f:
            head = [line for _, line in zip(range(2), f) if line.strip()]
    except (OSError, UnicodeDecodeError):
        return "unreadable"
    return "ok" if len(head) == 2 else "empty"


def check(require_mount: bool | None = None) -> dict:
    if require_mount is None:
        require_mount = os.getenv("KBO_DATA_MOUNT_REQUIRED") == "1"
    mount = mount_state()
    season = current_season()
    required = {p.format(s=season): file_state(DATA_DIR / p.format(s=season)) for p in REQUIRED}
    problems = ["mount: /app/data 가 tmpfs 자리표시 — 바인드 소스 미준비" if mount == "tmpfs" else None,
                "mount: 마운트가 필요한데 없다(이미지 스냅샷)" if require_mount and mount == "image" else None]
    problems = [p for p in problems if p] + [f"required {name}: {state}" for name, state in required.items() if state != "ok"]
    optional_missing = [p.format(s=season) for p in OPTIONAL if file_state(DATA_DIR / p.format(s=season)) != "ok"]
    return {"ready": not problems, "mount": mount, "season": season, "required": required,
            "optional_missing": optional_missing, "problems": problems}


if __name__ == "__main__":
    result = check()
    for p in result["problems"]:
        print(f"[error] data: {p}")
    if result["ready"]:  # 준비 실패일 때 선택 자료 경고는 잡음이라 뺀다
        for name in result["optional_missing"]:
            print(f"[warn] data: 선택 자료 없음 {name} — 해당 화면만 '자료 없음'")
        print(f"[data] ready — season={result['season']} mount={result['mount']}")
    sys.exit(0 if result["ready"] else 1)
