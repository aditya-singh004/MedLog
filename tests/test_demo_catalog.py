from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models import Department, Hospital
from app.utils.seed_demo_catalog import (
    DEMO_DEPARTMENTS,
    DEMO_HOSPITALS,
    ensure_demo_catalog,
)


def test_demo_catalog_is_complete_and_idempotent():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with TestingSession() as db:
        assert ensure_demo_catalog(db) == (
            len(DEMO_HOSPITALS),
            len(DEMO_HOSPITALS) * len(DEMO_DEPARTMENTS),
        )
        assert ensure_demo_catalog(db) == (0, 0)
        assert db.scalar(select(func.count()).select_from(Hospital)) == len(
            DEMO_HOSPITALS
        )
        assert db.scalar(select(func.count()).select_from(Department)) == len(
            DEMO_HOSPITALS
        ) * len(DEMO_DEPARTMENTS)

    Base.metadata.drop_all(engine)
