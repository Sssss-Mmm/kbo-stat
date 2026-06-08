from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import standings, schedule, players
from database import init_db

app = FastAPI(title="KBO Dashboard API")

# 데이터베이스 초기화
init_db()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 포함
app.include_router(standings.router, prefix="/api", tags=["standings"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])
app.include_router(players.router, prefix="/api", tags=["players"])


@app.get("/")
async def root():
    return {"message": "KBO Dashboard API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
