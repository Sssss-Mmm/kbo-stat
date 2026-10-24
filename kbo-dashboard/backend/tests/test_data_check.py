"""필수 데이터 준비 판정(data_check)과 /ready — 2026-10-24 빈 마운트 장애 재발 방지."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import data_check as dc

TMPFS = "36 30 0:5 / /app/data ro,relatime - tmpfs none ro\n"
EXT4 = "36 30 8:48 /home/u/data /app/data ro,relatime - ext4 /dev/sdd ro\n"
OTHER = "22 1 8:1 / / rw - overlay overlay rw\n"


class DataCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def mountinfo(self, text):
        p = self.tmp / "mountinfo"
        p.write_text(OTHER + text)
        return dc.mount_state(Path("/app/data"), str(p))

    def test_mount_states(self):
        self.assertEqual(self.mountinfo(TMPFS), "tmpfs")
        self.assertEqual(self.mountinfo(EXT4), "mounted")
        self.assertEqual(self.mountinfo(""), "image")
        self.assertEqual(self.mountinfo(TMPFS + EXT4), "mounted")  # 나중에 붙은 것이 보인다

    def test_file_states(self):
        f = self.tmp / "a.csv"
        self.assertEqual(dc.file_state(f), "missing")
        f.write_text("")
        self.assertEqual(dc.file_state(f), "empty")
        f.write_text("Season,Team\n")
        self.assertEqual(dc.file_state(f), "empty")  # 헤더만
        f.write_text("Season,Team\n2026,LG\n")
        self.assertEqual(dc.file_state(f), "ok")
        f.write_bytes(b"\xff\xfe\x00bad")
        self.assertEqual(dc.file_state(f), "unreadable")

    def run_check(self, files, mount="mounted", require_mount=True):
        for name in files:
            (self.tmp / name).parent.mkdir(parents=True, exist_ok=True)
            (self.tmp / name).write_text("h\n1\n")
        with patch.object(dc, "DATA_DIR", self.tmp), patch.object(dc, "current_season", return_value=2026), \
                patch.object(dc, "mount_state", return_value=mount):
            return dc.check(require_mount)

    def test_required_present_optional_missing_is_ready(self):
        r = self.run_check([p.format(s=2026) for p in dc.REQUIRED])
        self.assertTrue(r["ready"], r)
        self.assertEqual(len(r["optional_missing"]), len(dc.OPTIONAL))  # 선택 자료는 경고만

    def test_missing_required_is_not_ready(self):
        r = self.run_check([p.format(s=2026) for p in dc.REQUIRED[1:]])
        self.assertFalse(r["ready"])
        self.assertEqual(r["problems"], [f"required {dc.REQUIRED[0].format(s=2026)}: missing"])

    def test_tmpfs_mount_is_not_ready_even_with_files(self):
        r = self.run_check([p.format(s=2026) for p in dc.REQUIRED], mount="tmpfs")
        self.assertFalse(r["ready"])
        self.assertIn("tmpfs", r["problems"][0])

    def test_missing_mount_only_fails_when_required(self):
        files = [p.format(s=2026) for p in dc.REQUIRED]
        self.assertFalse(self.run_check(files, mount="image", require_mount=True)["ready"])
        self.assertTrue(self.run_check(files, mount="image", require_mount=False)["ready"])


class ReadyEndpointTest(unittest.TestCase):
    def test_db_ok_but_data_missing_is_503(self):
        with patch("database.init_db"):
            import main
        bad = {"ready": False, "mount": "tmpfs", "season": 2025, "problems": ["mount: tmpfs"], "optional_missing": [],
               "required": {}}
        with patch.object(main.data_check, "check", return_value=bad), patch.object(main.engine, "connect"):
            r = main.readiness_check()
        self.assertEqual(r.status_code, 503)
        self.assertIn(b'"database":"available"', r.body)
        self.assertIn(b"tmpfs", r.body)


if __name__ == "__main__":
    unittest.main()
