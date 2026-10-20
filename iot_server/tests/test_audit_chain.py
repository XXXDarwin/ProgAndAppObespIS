import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from crypto import audit
from db import models as m


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "a.db"}')
    m.Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def fill(db, n=3):
    for i in range(n):
        audit.append(db, f'event {i}')
    db.commit()


def row(db, id_):
    return db.scalars(select(m.AuditLog).where(m.AuditLog.id == id_)).one()


def test_empty_chain_is_valid(db):
    assert audit.verify_chain(db) is None


def test_chain_is_valid(db):
    fill(db)
    assert audit.verify_chain(db) is None


def test_modified_row_detected(db):
    fill(db)
    row(db, 2).event = 'forged'
    db.commit()
    assert audit.verify_chain(db) == 2


def test_deleted_row_detected(db):
    fill(db)
    db.delete(row(db, 2))
    db.commit()
    assert audit.verify_chain(db) == 3