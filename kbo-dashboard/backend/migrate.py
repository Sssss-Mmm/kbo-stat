"""
CSV 데이터를 PostgreSQL 데이터베이스로 마이그레이션하는 스크립트
"""
import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session
from datetime import datetime
import sys
import os

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, init_db
from models import Team, Standing, Schedule, Hitter, Pitcher


def migrate_standings(db: Session, data_path: Path, season: int):
    """팀 순위 데이터 마이그레이션"""
    print(f"마이그레이션: {season}년 순위표...")
    
    file_path = data_path / f"kbo_team_rank_{season}.csv"
    if not file_path.exists():
        print(f"⚠️  파일 없음: {file_path}")
        return

    df = pd.read_csv(file_path)
    
    for _, row in df.iterrows():
        team_name = row['팀명']
        
        # 팀 객체 찾기 또는 생성
        team = db.query(Team).filter(Team.name == team_name).first()
        if not team:
            team = Team(name=team_name, season=season)
            db.add(team)
            db.flush()
        
        # 순위 데이터 추가
        standing = Standing(
            season=season,
            rank=row['순위'],
            team_id=team.id,
            games=row['경기'],
            wins=row['승'],
            losses=row['패'],
            draws=row.get('무', 0),
            win_rate=float(row['승률']),
            games_behind=float(row['게임차']),
            last_10_games=row.get('최근10경기', ''),
            streak=row.get('연속', ''),
            home_record=row.get('홈', ''),
            away_record=row.get('방문', '')
        )
        db.add(standing)
    
    db.commit()
    print(f"✅ {season}년 순위표 마이그레이션 완료")


def migrate_hitters(db: Session, data_path: Path, season: int):
    """타자 통계 마이그레이션"""
    print(f"마이그레이션: {season}년 타자 통계...")
    
    file_path = data_path / f"kbo_{season}.csv"
    if not file_path.exists():
        print(f"⚠️  파일 없음: {file_path}")
        return

    df = pd.read_csv(file_path)
    
    for _, row in df.iterrows():
        team_name = row['팀명']
        
        # 팀 객체 찾기 또는 생성
        team = db.query(Team).filter(Team.name == team_name).first()
        if not team:
            team = Team(name=team_name, season=season)
            db.add(team)
            db.flush()
        
        # 타자 데이터 추가
        hitter = Hitter(
            season=season,
            rank=row.get('순위', 0),
            player_name=row['선수명'],
            team_id=team.id,
            avg=float(row.get('AVG', 0)) if pd.notna(row.get('AVG')) else 0,
            games=int(row.get('G', 0)) if pd.notna(row.get('G')) else 0,
            pa=int(row.get('PA', 0)) if pd.notna(row.get('PA')) else 0,
            ab=int(row.get('AB', 0)) if pd.notna(row.get('AB')) else 0,
            hits=int(row.get('H', 0)) if pd.notna(row.get('H')) else 0,
            doubles=int(row.get('2B', 0)) if pd.notna(row.get('2B')) else 0,
            triples=int(row.get('3B', 0)) if pd.notna(row.get('3B')) else 0,
            home_runs=int(row.get('HR', 0)) if pd.notna(row.get('HR')) else 0,
            rbi=int(row.get('RBI', 0)) if pd.notna(row.get('RBI')) else 0,
            sb=int(row.get('SB', 0)) if pd.notna(row.get('SB')) else 0,
            cs=int(row.get('CS', 0)) if pd.notna(row.get('CS')) else 0,
            bb=int(row.get('BB', 0)) if pd.notna(row.get('BB')) else 0,
            hbp=int(row.get('HBP', 0)) if pd.notna(row.get('HBP')) else 0,
            so=int(row.get('SO', 0)) if pd.notna(row.get('SO')) else 0,
            gdp=int(row.get('GDP', 0)) if pd.notna(row.get('GDP')) else 0,
            errors=int(row.get('E', 0)) if pd.notna(row.get('E')) else 0,
            xbh=int(row.get('XBH', 0)) if pd.notna(row.get('XBH')) else 0,
        )
        db.add(hitter)
    
    db.commit()
    print(f"✅ {season}년 타자 통계 마이그레이션 완료")


def migrate_pitchers(db: Session, data_path: Path, season: int):
    """투수 통계 마이그레이션"""
    print(f"마이그레이션: {season}년 투수 통계...")
    
    file_path = data_path / f"kbo_pitcher_{season}.csv"
    if not file_path.exists():
        print(f"⚠️  파일 없음: {file_path}")
        return

    df = pd.read_csv(file_path)
    
    for _, row in df.iterrows():
        team_name = row.get('팀명', '')
        if not team_name:
            continue
        
        # 팀 객체 찾기 또는 생성
        team = db.query(Team).filter(Team.name == team_name).first()
        if not team:
            team = Team(name=team_name, season=season)
            db.add(team)
            db.flush()
        
        # 투수 데이터 추가
        pitcher = Pitcher(
            season=season,
            rank=row.get('순위', 0),
            player_name=row['선수명'],
            team_id=team.id,
            games=int(row.get('경기', 0)) if pd.notna(row.get('경기')) else 0,
            games_started=int(row.get('선발', 0)) if pd.notna(row.get('선발')) else 0,
            wins=int(row.get('승', 0)) if pd.notna(row.get('승')) else 0,
            losses=int(row.get('패', 0)) if pd.notna(row.get('패')) else 0,
            saves=int(row.get('세', 0)) if pd.notna(row.get('세')) else 0,
            era=float(row.get('평균자책점', 0)) if pd.notna(row.get('평균자책점')) else 0,
        )
        db.add(pitcher)
    
    db.commit()
    print(f"✅ {season}년 투수 통계 마이그레이션 완료")


def main():
    """메인 마이그레이션 함수"""
    print("=" * 50)
    print("🚀 KBO 데이터 DB 마이그레이션 시작")
    print("=" * 50)
    
    # DB 초기화
    init_db()
    print("✅ 데이터베이스 테이블 생성 완료")
    
    # 데이터 경로
    data_path = Path(__file__).parent.parent.parent / "data" / "raw" / "kbo_official"
    
    if not data_path.exists():
        print(f"❌ 데이터 경로를 찾을 수 없습니다: {data_path}")
        return
    
    db = SessionLocal()
    
    try:
        # 2020-2026년 데이터 마이그레이션
        for season in range(2020, 2027):
            migrate_standings(db, data_path, season)
            migrate_hitters(db, data_path, season)
            migrate_pitchers(db, data_path, season)
        
        print("\n" + "=" * 50)
        print("✅ 모든 마이그레이션 완료!")
        print("=" * 50)
    
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
