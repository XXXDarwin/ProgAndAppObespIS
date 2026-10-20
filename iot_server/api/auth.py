from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from crypto import audit, cipher, signing
from crypto.cipher import CryptoError
from db import models as m

WINDOW_S = 60  # допустимое расхождение времени хаба и сервера, с


def _reject(db, device_id, reason, code=401):
    audit.append(db, f'auth_fail:{device_id}:{reason}'[:190])
    db.commit()
    raise HTTPException(code, reason)


def check(factory, headers, body):
    '''Проверяет подпись, время и seq. При успехе сохраняет новый last_seq.'''
    device_id = headers.get('x-device-id')
    seq_raw = headers.get('x-seq')
    ts = headers.get('x-timestamp')
    sig = headers.get('x-signature')
    with factory() as db:
        if not (device_id and seq_raw and ts and sig):
            _reject(db, device_id or '?', 'missing auth headers')
        try:
            seq = int(seq_raw)
        except ValueError:
            _reject(db, device_id, 'bad seq')
        dev = db.scalar(select(m.Device).where(m.Device.device_id == device_id)
                        .with_for_update())
        if dev is None:
            _reject(db, device_id, 'unknown device')
        if not dev.secret_enc:
            _reject(db, device_id, 'device has no key')
        try:
            secret = cipher.decrypt(dev.secret_enc, 'devices',
                                    signing.secret_aad(device_id))
        except CryptoError:
            _reject(db, device_id, 'device key unreadable')
        try:
            sent = datetime.fromisoformat(ts)
        except ValueError:
            _reject(db, device_id, 'bad timestamp')
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        if abs((datetime.now(timezone.utc) - sent).total_seconds()) > WINDOW_S:
            _reject(db, device_id, 'stale timestamp')
        if not signing.verify(body, ts, seq, sig, secret):
            _reject(db, device_id, 'bad signature')
        # seq проверяется только после подписи: неподписанный запрос состояние не меняет
        if dev.last_seq is not None and seq <= dev.last_seq:
            _reject(db, device_id, 'replayed seq', code=409)
        dev.last_seq = seq
        db.commit()