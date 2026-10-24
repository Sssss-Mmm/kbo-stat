"""P2-D 팀 상세 · 선수 검색 · 선수 시즌 기록(team_player_service + /api/v2 라우트). 임시 CSV + SQLite."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from database import Base
from models import Hitter, Pitcher, Team
from services import team_player_service as tp
from tests.test_season_api import seed
from tests.test_v2_api import make_engine

HIT = "Season,PlayerId,선수명,팀명,포지션,등번호,G,AVG,AB,H,2B,3B,HR,RBI,R,SB,BB,HBP,SO,OBP,SLG,OPS,ISO,BABIP,wOBA,wRC+,WPA,WAR,규정충족\n"
PIT = "Season,PlayerId,선수명,팀명,포지션,등번호,G,W,L,SV,HLD,IP,ERA,SO,H,HR,R,ER,BB,HBP,WHIP,QS,K/9,BB/9,K/BB,WPA,WAR,규정충족\n"
REG = "RosterDate,TeamCode,Team,BackNo,PlayerId,PlayerName,Position,PitchBat,BirthDate,HeightCm,WeightKg,Body,DetailUrl,RecordType\n"


def hitter(pid, name, team, pos, war, ab=100, g=40, bb=8, hbp=1):
    return f"2025,{pid},{name},{team},{pos},7,{g},0.3,{ab},30,5,0,3,10,9,1,{bb},{hbp},20,0.36,0.45,0.81,0.15,0.33,0.35,120.0,0.5,{war},True\n"


def pitcher(pid, name, team, war, era="3.5", g=20, pos="투수"):
    return f"2025,{pid},{name},{team},{pos},40,{g},5,4,0,0,60 1/3,{era},50,55,4,25,23,18,2,1.21,3,7.5,2.7,2.78,0.3,{war},False\n"


class ServiceTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (tmp / "processed").mkdir()
        raw = tmp / "raw" / "kbo_official"
        raw.mkdir(parents=True)
        (tmp / "processed" / "kbo_naver_hitters_2025.csv").write_text(
            HIT + hitter(1, "김민수", "LG", "내야수", "2.5") + hitter(2, "김민수", "두산", "외야수", "")  # WAR 미확정
            + hitter(3, "홍 길동", "LG", "내야수", "4.1") + hitter(4, "박투수", "LG", "", "0.0", ab=0, g=3, bb=0, hbp=0)
            + hitter(8, "야수등판", "LG", "", "2.0", ab=300, g=120)  # 포지션 빈칸 야수가 1경기 등판
            + hitter(9, "코치투수", "LG", "2군 투수코치", "0.0", ab=0, g=2, bb=0, hbp=0), encoding="utf-8-sig")
        (tmp / "processed" / "kbo_naver_pitchers_2025.csv").write_text(
            PIT + pitcher(4, "박투수", "LG", "1.2") + pitcher(5, "최투수", "LG", "3.3", era="")
            + pitcher(8, "야수등판", "LG", "0.0", g=1, pos="") + pitcher(9, "코치투수", "LG", "0.5", g=30, pos="2군 투수코치"),
            encoding="utf-8-sig")
        (raw / "kbo_registered_players_2026-06-11.csv").write_text(
            REG + "2026-06-11,LG,LG,7,1,김민수,내야수,우투우타,1999-01-01,180,80,,u,hitter\n", encoding="utf-8-sig")
        self.enterContext(patch.object(tp, "PROCESSED_DIR", tmp / "processed"))
        self.enterContext(patch.object(tp, "RAW_DIR", raw))

    def test_same_name_players_stay_apart(self):
        found = tp.search("김민수", None, None, None)["data"]
        self.assertEqual([p["player_id"] for p in found], [1, 2])
        self.assertEqual([p["same_name"] for p in found], [1, 1])
        self.assertEqual((found[0]["birth_date"], found[0]["pitch_bat"]), ("1999-01-01", "우투우타"))
        self.assertIsNone(found[1]["birth_date"])  # 명단에 없으면 추측하지 않는다
        self.assertEqual([s["team"] for p in found for s in p["seasons"]], ["LG", "두산"])

    def test_search_ignores_spaces_and_filters(self):
        self.assertEqual([p["player_id"] for p in tp.search("홍길동", None, None, None)["data"]], [3])
        self.assertEqual({p["player_id"] for p in tp.search(None, "LG", 2025, None)["data"]}, {1, 3, 4, 5, 8, 9})
        self.assertEqual({p["player_id"] for p in tp.search(None, "LG", None, "pitcher")["data"]}, {4, 5, 8, 9})
        self.assertEqual(tp.search("김민수", None, 2024, None)["data"], [])

    def test_position_player_who_pitched_keeps_batting_line(self):
        # 포지션 빈칸이어도 타격 경기 > 투구 경기면 야수 — 타격 기록을 지우지 않는다(규정 타석 타자가 빠진 실제 사례가 있었다)
        roles = sorted(s["role"] for s in tp.search("야수등판", None, None, None)["data"][0]["seasons"])
        self.assertEqual(roles, ["batter", "pitcher"])
        # 야수가 아닌 다른 포지션 값(코치 등)은 경기 수로 — 타격 2 ≤ 투구 30 이면 투수의 타석
        roles = [s["role"] for s in tp.search("코치투수", None, None, None)["data"][0]["seasons"]]
        self.assertEqual(roles, ["pitcher"])

    def test_ambiguous_line_with_real_plate_appearances_is_kept(self):
        # Codex 재현: 포지션 빈칸·타격 1경기·4타수·투구 2경기 — 경기 수만으로는 투수로 단정하지 않는다(실제 타석 기록은 남긴다)
        line = {"position": None, "stats": {"G": 1, "AB": 4, "BB": 0, "HBP": 0}}
        self.assertFalse(tp._is_pitcher_batting(line, 2))
        self.assertFalse(tp._is_pitcher_batting({"position": "", "stats": {"G": 1, "AB": 0, "BB": 1, "HBP": 0}}, 5))
        self.assertTrue(tp._is_pitcher_batting({"position": None, "stats": {"G": 2, "AB": 0, "BB": 0, "HBP": 0}}, 30))
        self.assertTrue(tp._is_pitcher_batting({"position": "투수", "stats": {"G": 2, "AB": 3, "BB": 0, "HBP": 0}}, 30))
        self.assertFalse(tp._is_pitcher_batting({"position": "내야수", "stats": {"G": 1, "AB": 0, "BB": 0, "HBP": 0}}, 30))

    def test_pitcher_batting_line_is_dropped(self):
        roles = [s["role"] for s in tp.search("박투수", None, None, None)["data"][0]["seasons"]]
        self.assertEqual(roles, ["pitcher"])

    def test_profile_keeps_missing_values_as_none(self):
        self.assertIsNone(tp.profile(999))
        self.assertIsNone(tp.profile(2)["data"]["seasons"][0]["stats"]["WAR"])
        self.assertIsNone(tp.profile(5)["data"]["seasons"][0]["stats"]["ERA"])
        self.assertEqual(tp.profile(1)["data"]["seasons"][0]["stats"]["WAR"], 2.5)
        self.assertEqual(tp.profile(1)["meta"]["sources"][0]["source"], "naver_season_stats")

    def test_team_detail(self):
        engine = make_engine()
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            seed(conn)
            d = tp.team_detail(conn, "LG", 2025)["data"]
            self.assertEqual((d["record"]["wins"], d["record"]["losses"], d["record"]["draws"]), (1, 2, 1))
            # 최근 경기: 끝난 경기만(취소 제외), 최근 것부터, 더블헤더 2차전이 먼저
            self.assertEqual([(g["date"], g["doubleheader"], g["result"], g["side"]) for g in d["recent_games"]],
                             [("2025-03-26", 2, "L", "home"), ("2025-03-26", 1, "L", "home"), ("2025-03-23", None, "T", "away"),
                              ("2025-03-22", None, "W", "away")])
            p = d["players"]
            self.assertEqual(p["basis"], "naver_season_stats")
            self.assertEqual([x["player_id"] for x in p["key_batters"]], [3, 1, 8])  # WAR 순, 투수 타석 줄 없음
            self.assertEqual([x["player_id"] for x in p["key_pitchers"]], [5, 4, 9])
            # 원본이 같은 시각 더블헤더를 2차전부터 적어도 1차전 → 2차전 순서로 본다
            conn.execute(text("UPDATE official.schedule_game SET row_no = 10 - row_no, game_time = '14:00' "
                              "WHERE game_date = '2025-03-26'"))
            d = tp.team_detail(conn, "LG", 2025)["data"]
            self.assertEqual([g["doubleheader"] for g in d["recent_games"][:2]], [2, 1])
            self.assertIsNone(tp.team_detail(conn, "KT", 2025))
            self.assertIsNone(tp.team_detail(conn, "LG", 2024))

    def test_team_without_player_ids_uses_v1_qualified(self):
        engine = make_engine()
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            seed(conn)
            conn.execute(Team.__table__.insert(), [{"id": 1, "name": "LG"}])
            conn.execute(Hitter.__table__.insert(), [dict(season=2025, rank=3, player_name="옛타자", team_id=1, avg=0.31)])
            conn.execute(Pitcher.__table__.insert(), [dict(season=2025, rank=1, player_name="옛투수", team_id=1, era=2.5)])
            with patch.object(tp, "naver_seasons", return_value=[]):
                p = tp.team_detail(conn, "LG", 2025)["data"]["players"]
        self.assertEqual(p["basis"], "v1_qualified")
        self.assertEqual((p["batters"][0]["name"], p["batters"][0]["avg"], p["batters"][0]["home_runs"]), ("옛타자", 0.31, None))
        self.assertEqual(p["pitchers"][0]["era"], 2.5)


class PitcherBattingBoundaryTest(unittest.TestCase):
    """'투수의 타석' 판정은 선수 ID 마다 한다 — 같은 이름·포지션 빈칸인 투수와 '투수로 1경기 나온 야수'가 섞이지 않는다.
    이적해도(시즌 기록은 한 팀) 같은 규칙."""

    def test_same_name_pitcher_and_fielder_are_judged_per_id(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (tmp / "processed").mkdir()
        (tmp / "raw" / "kbo_official").mkdir(parents=True)
        (tmp / "processed" / "kbo_naver_hitters_2025.csv").write_text(
            HIT + hitter(10, "동명선수", "LG", "", "0.0", ab=0, g=2, bb=0, hbp=0) + hitter(11, "동명선수", "두산", "", "1.5", ab=300, g=100),
            encoding="utf-8-sig")
        (tmp / "processed" / "kbo_naver_pitchers_2025.csv").write_text(
            PIT + pitcher(10, "동명선수", "LG", "1.0", g=30, pos="") + pitcher(11, "동명선수", "두산", "0.0", g=1, pos=""),
            encoding="utf-8-sig")
        with patch.object(tp, "PROCESSED_DIR", tmp / "processed"), patch.object(tp, "RAW_DIR", tmp / "raw" / "kbo_official"):
            found = {p["player_id"]: sorted(x["role"] for x in p["seasons"]) for p in tp.search("동명선수", None, None, None)["data"]}
            self.assertEqual(found, {10: ["pitcher"], 11: ["batter", "pitcher"]})
            self.assertEqual([p["same_name"] for p in tp.search("동명선수", None, None, None)["data"]], [1, 1])
            self.assertEqual({x["player_id"] for x in tp.naver_lines(2025, "batter")}, {11})


class RouteTest(unittest.TestCase):
    def test_routes(self):
        import main
        import routers.v2 as router
        engine = make_engine()
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            seed(conn)
        client = TestClient(main.app)
        with patch.object(router, "engine", engine), patch.object(tp, "naver_seasons", return_value=[]):
            self.assertEqual(client.get("/api/v2/players/search").status_code, 422)
            self.assertEqual(client.get("/api/v2/players/search?q=%20").status_code, 422)
            self.assertEqual(client.get("/api/v2/players/search?q=x").json()["data"], [])
            self.assertEqual(client.get("/api/v2/players/1/profile").status_code, 404)
            self.assertEqual(client.get("/api/v2/teams/LG?season=2025").status_code, 200)
            self.assertEqual(client.get("/api/v2/teams/LG?season=2024").status_code, 404)
            self.assertEqual(client.get("/api/v2/teams/LG").status_code, 422)  # 시즌 필수


if __name__ == "__main__":
    unittest.main()
