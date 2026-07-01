from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.async_database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        yield session


_MIGRATIONS = [
    "ALTER TABLE merchants ADD COLUMN password VARCHAR(255)",
    "ALTER TABLE products ADD COLUMN category VARCHAR(100)",
    "ALTER TABLE products ADD COLUMN sort_order INTEGER DEFAULT 0",
]


async def init_db():
    async with engine.begin() as conn:
        from app.models import Merchant, Catalog, Product
        await conn.run_sync(Base.metadata.create_all)

        for sql in _MIGRATIONS:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass
