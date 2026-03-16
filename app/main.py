from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.database import get_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm the DB connection pool
    await get_pool()
    yield
    # Shutdown: close all connections
    await close_pool()


app = FastAPI(
    title="PartSelect Chatbot API",
    description="Dishwasher and refrigerator parts assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
