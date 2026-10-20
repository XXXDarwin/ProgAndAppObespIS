import pytest

from crypto import cipher
from crypto.cipher import CryptoError

AAD = b'shelf|A1-1-1|2026-10-08T10:00:00+00:00'


def test_roundtrip():
    blob = cipher.encrypt(b'{"weight_g": 2000.0}', 'measurements', AAD)
    assert cipher.decrypt(blob, 'measurements', AAD) == b'{"weight_g": 2000.0}'


def test_same_plaintext_gives_different_ciphertext():
    a = cipher.encrypt(b'22.5', 'measurements', AAD)
    b = cipher.encrypt(b'22.5', 'measurements', AAD)
    assert a != b


def test_wrong_aad_rejected():
    blob = cipher.encrypt(b'22.5', 'measurements', AAD)
    with pytest.raises(CryptoError):
        cipher.decrypt(blob, 'measurements', b'shelf|A1-1-2|other')


def test_tampered_blob_rejected():
    blob = bytearray(cipher.encrypt(b'22.5', 'measurements', AAD))
    blob[-1] ^= 1
    with pytest.raises(CryptoError):
        cipher.decrypt(bytes(blob), 'measurements', AAD)


def test_wrong_master_key_rejected(monkeypatch):
    blob = cipher.encrypt(b'22.5', 'measurements', AAD)
    monkeypatch.setenv('IOT_MASTER_KEY', '22' * 32)
    with pytest.raises(CryptoError):
        cipher.decrypt(blob, 'measurements', AAD)


def test_key_rotation():
    old = cipher.encrypt(b'old', 'measurements', AAD, version=1)
    new = cipher.encrypt(b'new', 'measurements', AAD, version=2)
    assert old[0] == 1 and new[0] == 2
    assert cipher.decrypt(old, 'measurements', AAD) == b'old'
    assert cipher.decrypt(new, 'measurements', AAD) == b'new'


def test_purposes_are_isolated():
    blob = cipher.encrypt(b'x', 'measurements', AAD)
    with pytest.raises(CryptoError):
        cipher.decrypt(blob, 'alerts', AAD)


def test_missing_master_key(monkeypatch):
    monkeypatch.delenv('IOT_MASTER_KEY')
    monkeypatch.setattr(cipher, '_load_env', lambda: None)
    with pytest.raises(CryptoError):
        cipher.encrypt(b'x', 'measurements', AAD)