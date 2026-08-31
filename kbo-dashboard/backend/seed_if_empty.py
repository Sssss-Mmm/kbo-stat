"""DB가 비어 있으면 migrate.py 로 최초 1회 시드한다.

컨테이너 진입점(entrypoint.sh)에서 uvicorn 기동 전에 호출한다. 마이그레이션은
시즌별 delete-after 라 멱등하지만, 매 기동마다 전체 재적재를 피하려고 standings
가 비어 있을 때만 실행한다. postgres 볼륨이 살아 있으면 재기동 시 시드를 건너뛴다.
"""
from database import SessionLocal
from models import Standing


def already_seeded() -> bool:
    try:
        db = SessionLocal()
        try:
            return db.query(Standing).first() is not None
        finally:
            db.close()
    except Exception:
        # 테이블 미생성 등 → 시드 필요로 간주.
        return False


def main() -> None:
    # 시드는 부가 작업이다. 실패해도 API(특히 CSV 라우터)는 떠야 하므로
    # 예외를 사유와 함께 로그로만 남기고 정상 종료한다(NFR-05 장애 격리).
    try:
        if already_seeded():
            print("[seed] DB already seeded — skipping migration.")
            return
        print("[seed] empty DB detected — running migration...")
        import migrate

        migrate.main()
    except Exception as exc:
        print(f"[seed] skipped — {type(exc).__name__}: {exc}")
        print("[seed] DB 기반 라우터는 503 을 반환하고 CSV 기반 라우터만 동작한다.")


if __name__ == "__main__":
    main()
