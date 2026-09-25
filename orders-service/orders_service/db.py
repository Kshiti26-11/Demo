from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def make_engine(url: str):
    if url.startswith("sqlite:///:memory:") or "+pysqlite" in url and ":memory:" in url:
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url)


def make_sessionmaker(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
