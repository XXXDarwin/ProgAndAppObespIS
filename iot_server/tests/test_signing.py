from crypto import signing

SECRET = bytes.fromhex('aa' * 32)
BODY = b'{"zone": "A"}'
TS = '2026-10-21T10:00:00+00:00'


def test_sign_and_verify():
    sig = signing.sign(SECRET, BODY, TS, 5)
    assert signing.verify(BODY, TS, 5, sig, SECRET)


def test_any_changed_field_breaks_signature():
    sig = signing.sign(SECRET, BODY, TS, 5)
    assert not signing.verify(b'{"zone": "B"}', TS, 5, sig, SECRET)
    assert not signing.verify(BODY, '2026-10-21T10:00:01+00:00', 5, sig, SECRET)
    assert not signing.verify(BODY, TS, 6, sig, SECRET)
    assert not signing.verify(BODY, TS, 5, sig, bytes.fromhex('bb' * 32))


def test_garbage_signature_does_not_crash():
    assert signing.verify(BODY, TS, 5, 'не-hex', SECRET) is False