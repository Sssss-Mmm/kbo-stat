"""일일 파이프라인 — 수집 차단 + 새해(입력 CSV 없음) + Docker 미실행 회귀 테스트. 네트워크 요청 없음.

update_daily 단위: 입력 없으면 [skip:input] 로 건너뛰고(만들지 않음), 진짜 오류는 [error] + 예외로 남긴다.
update_kbo_daily.sh 전체: PATH 에 가짜 date(2099년)·docker 를 넣어 실제 스크립트를 돌린다. 로그·잠금·마커는 임시 폴더.

실행: python -m unittest discover -s src -p "test_update_daily.py" -v
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_hitter_metrics
import build_team_game_results
import update_daily

ROOT = Path(__file__).resolve().parent.parent
APPROVALS = ("KBO_AUTOMATED_FETCH_APPROVED", "NAVER_AUTOMATED_FETCH_APPROVED")
NO_APPROVAL = {k: v for k, v in os.environ.items() if k not in APPROVALS}


def args(year, players=True):
    return Namespace(year=year, players=players, registered_players=False, pitch_zones=False, pitch_date=None, db=False)


class UpdateDailyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raw, processed = Path(self.tmp.name) / "raw", Path(self.tmp.name) / "processed"
        raw.mkdir()
        processed.mkdir()
        self.raw, self.processed = raw, processed
        self.patches = [mock.patch.dict(os.environ, NO_APPROVAL, clear=True)]
        for module in (build_team_game_results, build_hitter_metrics):
            self.patches += [mock.patch.object(module, "RAW_DIR", raw), mock.patch.object(module, "PROCESSED_DIR", processed)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def run_daily(self, year, players=True):
        out = io.StringIO()
        with redirect_stdout(out):
            update_daily.run(args(year, players))
        return out.getvalue()

    def test_new_year_without_csv_skips_and_writes_nothing(self):
        log = self.run_daily(2099)
        self.assertIn("[skip:collect] KBO standings/schedule", log)
        self.assertIn("[skip:collect] KBO hitter/pitcher leaderboards", log)
        self.assertIn("[skip:input] team game results 2099", log)
        self.assertIn("[skip:input] hitter metrics 2099", log)
        self.assertNotIn("[error]", log)
        self.assertEqual(list(self.processed.iterdir()), [])  # 없는 자료를 만들지 않는다

    def test_existing_input_is_still_built(self):
        (self.raw / "kbo_schedule_2099.csv").write_text("x", encoding="utf-8")
        with mock.patch.object(build_team_game_results, "build") as built:
            log = self.run_daily(2099, players=False)
        built.assert_called_once_with(2099)
        self.assertNotIn("[skip:input] team game results", log)

    def test_real_error_is_not_swallowed(self):
        # 입력은 있는데 내용이 깨졌다 → 건너뜀이 아니라 실패
        (self.raw / "kbo_schedule_2099.csv").write_text("broken\n1\n", encoding="utf-8")
        err = io.StringIO()
        with mock.patch.object(sys, "argv", ["update_daily.py", "--year", "2099"]), redirect_stdout(io.StringIO()), \
                redirect_stderr(err), self.assertRaises(KeyError):
            update_daily.main()
        self.assertIn("[error] daily update failed: KeyError", err.getvalue())

    def test_missing_file_inside_a_builder_is_not_reported_as_skip(self):
        # 입력 확인을 통과한 뒤 빌더 안에서 난 FileNotFoundError 는 [skip:input] 로 바뀌지 않는다
        (self.raw / "kbo_schedule_2099.csv").write_text("x", encoding="utf-8")
        with mock.patch.object(build_team_game_results, "build", side_effect=FileNotFoundError("other")), \
                redirect_stdout(io.StringIO()), self.assertRaises(FileNotFoundError):
            update_daily.run(args(2099, players=False))


FAKE_DATE = """#!/bin/bash
for a in "$@"; do
  case "$a" in +%Y) echo 2099; exit 0;; +%F) echo 2099-01-02; exit 0;; esac
done
exec /bin/date "$@"
"""
FAKE_DOCKER = """#!/bin/bash
echo "docker $*" >> "$DOCKER_CALLS"
case "${FAKE_DOCKER_MODE}" in
  daemon_down) [[ "$1" == "info" ]] && exit 1; [[ "$*" == "compose version" ]] && { echo "Docker Compose version v2.40.0"; exit 0; } ;;
  ok)
    [[ "$1" == "info" ]] && { echo "${FAKE_DOCKER_OS:-Docker Desktop}|fake|ID"; exit 0; }
    [[ "$*" == "compose version" ]] && { echo "Docker Compose version v2.40.0"; exit 0; }
    [[ "$*" == *" ps -q backend" ]] && { echo abc123; exit 0; }
    [[ "$*" == *"exec -T backend python migrate.py" ]] && exit 0 ;;
esac
exit 1
"""


class DailyScriptTest(unittest.TestCase):
    """실제 scripts/update_kbo_daily.sh 를 2099년(입력 없음)·수집 차단으로 끝까지 돌린다."""

    def run_script(self, docker_mode, docker_os="Docker Desktop"):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        bin_dir, logs = tmp / "bin", tmp / "logs"
        bin_dir.mkdir()
        (bin_dir / "date").write_text(FAKE_DATE)
        if docker_mode != "missing":
            (bin_dir / "docker").write_text(FAKE_DOCKER)
        for f in bin_dir.iterdir():
            f.chmod(0o755)
        # PATH 는 이 폴더 하나 — 스크립트가 쓰는 도구만 링크한다(진짜 docker 가 끼어들지 않게)
        for tool in ("dirname", "flock", "grep", "mkdir", "sleep"):
            (bin_dir / tool).symlink_to(next(Path(d, tool) for d in ("/usr/bin", "/bin") if Path(d, tool).exists()))
        env = {**NO_APPROVAL, "PATH": str(bin_dir), "LOG_DIR": str(logs), "DOCKER_CALLS": str(tmp / "calls"),
               "FAKE_DOCKER_MODE": docker_mode, "FAKE_DOCKER_OS": docker_os, "PYTHON_BIN": sys.executable, "PYTHONDONTWRITEBYTECODE": "1"}
        before = sorted(p.name for p in (ROOT / "data").rglob("*2099*"))
        r = subprocess.run(["/bin/bash", str(ROOT / "scripts" / "update_kbo_daily.sh")], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(sorted(p.name for p in (ROOT / "data").rglob("*2099*")), before)  # data/ 에 2099 산출물 없음
        calls = (tmp / "calls").read_text() if (tmp / "calls").exists() else ""
        return r, r.stdout + r.stderr, calls, logs

    def test_new_year_docker_ok_finishes_with_skips_only(self):
        r, log, calls, logs = self.run_script("ok")
        self.assertEqual(r.returncode, 0, log[-2000:])
        self.assertIn("season=2099", log)
        for tag in ("[skip:collect] KBO", "[skip:collect] naver", "[skip:input] team game results 2099",
                    "[skip:input] hitter metrics 2099", "[skip:input] zones", "[skip:input] arsenal", "[skip:input] count"):
            self.assertIn(tag, log)
        self.assertNotIn("[error]", log)
        self.assertNotIn("Traceback", log)
        self.assertIn("exec -T backend python migrate.py", calls)
        self.assertNotIn(" up ", calls)  # 실행 중이면 컨테이너를 건드리지 않는다
        self.assertEqual((logs / ".last_update_date").read_text().strip(), "2099-01-02")

    def test_docker_daemon_down_is_an_error(self):
        r, log, calls, logs = self.run_script("daemon_down")
        self.assertEqual(r.returncode, 5, log[-2000:])
        self.assertIn("[error] db: docker compose 플러그인 또는 Docker 데몬을 쓸 수 없다", log)
        self.assertNotIn("migrate.py", calls)
        self.assertFalse((logs / ".last_update_date").exists())  # 성공 마커를 남기지 않는다

    def test_wrong_docker_engine_is_an_error(self):
        # Docker Desktop 이 꺼져 WSL 기본 엔진이 소켓을 잡은 상태 — 낡은 컨테이너에 적재하지 않는다
        r, log, calls, logs = self.run_script("ok", docker_os="Ubuntu 24.04.3 LTS")
        self.assertEqual(r.returncode, 5, log[-2000:])
        self.assertIn("[error] engine: 연결된 엔진이 'Docker Desktop' 가 아니다", log)
        self.assertNotIn("migrate.py", calls)
        self.assertNotIn(" up ", calls)
        self.assertFalse((logs / ".last_update_date").exists())

    def test_docker_missing_is_an_error(self):
        r, log, _, logs = self.run_script("missing")
        self.assertEqual(r.returncode, 3, log[-2000:])
        self.assertIn("[error] db: docker not found", log)
        self.assertFalse((logs / ".last_update_date").exists())


FAKE_DOCKER_START = """#!/bin/bash
echo "docker $*" >> "$DOCKER_CALLS"
[[ "$1" == "info" ]] && { echo "${FAKE_DOCKER_OS}|fake|ID"; exit 0; }
[[ "$1 $2" == "ps -a" ]] && exit 0
[[ "$*" == *" ps -aq" ]] && { echo c1; echo c2; exit 0; }
[[ "$1" == "inspect" ]] && { echo "/kbo_backend 127.0.0.1:8001 "; echo "/kbo_frontend ${FAKE_FRONT_BIND}:3000 "; exit 0; }
[[ "$*" == *" up -d --no-recreate" ]] && exit 0
exit 1
"""


class StartScriptTest(unittest.TestCase):
    """scripts/start_kbo.sh: 엔진 확인(A)과 외부 바인딩 확인 — 둘 다 compose up 전에 멈춘다."""

    def run_script(self, docker_os="Docker Desktop", front_bind="127.0.0.1"):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        bin_dir, logs = tmp / "bin", tmp / "logs"
        bin_dir.mkdir()
        logs.mkdir()
        (logs / ".last_update_date").write_text("2099-01-02")  # 오늘(가짜 날짜) 갱신됨 → 캐치업을 띄우지 않는다
        (bin_dir / "date").write_text(FAKE_DATE)
        (bin_dir / "docker").write_text(FAKE_DOCKER_START)
        for f in bin_dir.iterdir():
            f.chmod(0o755)
        for tool in ("dirname", "mkdir", "grep", "cat"):
            (bin_dir / tool).symlink_to(next(Path(d, tool) for d in ("/usr/bin", "/bin") if Path(d, tool).exists()))
        env = {"PATH": str(bin_dir), "LOG_DIR": str(logs), "DOCKER_CALLS": str(tmp / "calls"),
               "FAKE_DOCKER_OS": docker_os, "FAKE_FRONT_BIND": front_bind}
        r = subprocess.run(["/bin/bash", str(ROOT / "scripts" / "start_kbo.sh")], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=60)
        calls = (tmp / "calls").read_text() if (tmp / "calls").exists() else ""
        return r, r.stdout + r.stderr, calls

    def test_desktop_engine_and_local_bindings_start(self):
        r, log, calls = self.run_script()
        self.assertEqual(r.returncode, 0, log)
        self.assertIn("[engine] Docker Desktop", log)
        self.assertIn(" up -d --no-recreate", calls)

    def test_wrong_engine_stops_before_anything(self):
        r, log, calls = self.run_script(docker_os="Ubuntu 24.04.3 LTS")
        self.assertEqual(r.returncode, 5, log)
        self.assertIn("[error] engine:", log)
        self.assertNotIn(" up ", calls)
        self.assertNotIn("inspect", calls)

    def test_exposed_binding_stops_before_up(self):
        for bind in ("", "0.0.0.0", "::"):
            r, log, calls = self.run_script(front_bind=bind)
            self.assertEqual(r.returncode, 4, (bind, log))
            self.assertIn("/kbo_frontend", log)
            self.assertNotIn(" up ", calls)


if __name__ == "__main__":
    unittest.main()
