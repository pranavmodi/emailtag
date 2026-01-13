"""Database session management."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create sync engine for Celery tasks
engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create async engine for FastAPI
async_engine = create_async_engine(str(settings.ASYNC_DATABASE_URL), echo=settings.DEBUG, future=True, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


# Dependency to get DB session
async def get_db() -> AsyncSession:
    """Get an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Synchronous session for Celery tasks
def get_sync_db():
    """Get a synchronous database session for background tasks."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 