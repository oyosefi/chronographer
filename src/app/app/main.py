from fastapi import FastAPI
from sqlalchemy import text

from .api import router
from .database import engine

app = FastAPI(title="Chronographer API", version="0.1.0")
app.include_router(router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}
