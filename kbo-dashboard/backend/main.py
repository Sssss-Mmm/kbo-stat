from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import players, rag, schedule, standings


app = FastAPI(title="KBO Dashboard API")

# Database-backed routes can use PostgreSQL, but CSV-backed RAG should still
# run when a local database is not available.
try:
    init_db()
except Exception as exc:
    print(f"[startup] database init skipped: {exc}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(standings.router, prefix="/api", tags=["standings"])
app.include_router(schedule.router, prefix="/api", tags=["schedule"])
app.include_router(players.router, prefix="/api", tags=["players"])
app.include_router(rag.router, prefix="/api", tags=["rag"])


@app.get("/")
async def root():
    return {"message": "KBO Dashboard API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
