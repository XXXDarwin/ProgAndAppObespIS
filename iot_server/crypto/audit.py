import hashlib
from datetime import datetime, timezone

from sqlalchemy import select

from db import models as m


def _utc(ts):
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _hash(prev, event, ts):
    return hashlib.sha256(f'{prev or ""}|{event}|{ts.isoformat()}'.encode()).hexdigest()


def append(db, event):
    '''Добавляет запись в цепочку; вызывается внутри транзакции запроса.'''
    last = db.scalars(select(m.AuditLog).order_by(m.AuditLog.id.desc())
                      .limit(1).with_for_update()).first()
    prev = last.hash if last else None
    ts = datetime.now(timezone.utc)
    db.add(m.AuditLog(event=event, ts=ts, prev_hash=prev,
                      hash=_hash(prev, event, ts)))


def verify_chain(db):
    '''None, если цепочка целостна; иначе id первой испорченной записи.'''
    prev = None
    for r in db.scalars(select(m.AuditLog).order_by(m.AuditLog.id)):
        if r.prev_hash != prev or r.hash != _hash(prev, r.event, _utc(r.ts)):
            return r.id
        prev = r.hash
    return None