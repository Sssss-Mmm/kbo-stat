import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import analytics, player_stats, players, rag, schedule, standings, story, today, zones


app = FastAPI(title="KBO Dashboard API")

# Database-backed routes can use PostgreSQL, but CSV-backed RAG should still
# run when a local database is not available.
try:
    init_db()
except Exception as exc:
    print(f"[startup] database init skipped: {exc}")

# CORS: 콤마로 구분된 CORS_ORIGINS 환경변수로 허용 출처 지정 (기본 "*").
# 와일드카드와 credentials 동시 사용은 브라우저가 무시하므로 함께 켜지 않는다.
cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(standings.router, prefix="/api", tags=["standings"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])
app.include_router(players.router, prefix="/api", tags=["players"])
app.include_router(rag.router, prefix="/api", tags=["rag"])
app.include_router(analytics.router, prefix="/api", tags=["analytics"])
app.include_router(zones.router, prefix="/api", tags=["zones"])
app.include_router(player_stats.router, prefix="/api", tags=["player-stats"])
app.include_router(today.router, prefix="/api", tags=["today"])
app.include_router(story.router, prefix="/api", tags=["story"])


@app.get("/")
async def root():
    return {"message": "KBO Dashboard API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
