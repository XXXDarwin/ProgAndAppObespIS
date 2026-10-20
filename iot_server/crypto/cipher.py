import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from db.session import _load_env


class CryptoError(Exception):
    '''Ключ не задан, данные изменены или привязаны к другой записи.'''


def _master():
    _load_env()
    raw = os.environ.get('IOT_MASTER_KEY')
    if not raw:
        raise CryptoError('IOT_MASTER_KEY не задан')
    key = bytes.fromhex(raw)
    if len(key) != 32:
        raise CryptoError('IOT_MASTER_KEY должен быть 32 байта (64 hex-символа)')
    return key


def current_version():
    _load_env()
    return int(os.environ.get('IOT_KEY_VERSION', '1'))


def derive(purpose, version):
    '''Отдельный ключ на каждое назначение (таблицу) и версию.'''
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=f'{purpose}:v{version}'.encode()).derive(_master())


def encrypt(plain, purpose, aad, version=None):
    version = current_version() if version is None else version
    nonce = os.urandom(12)
    ct = AESGCM(derive(purpose, version)).encrypt(nonce, plain, aad)
    return bytes([version]) + nonce + ct       # ct содержит тег 16 байт


def decrypt(blob, purpose, aad):
    if len(blob) < 1 + 12 + 16:
        raise CryptoError('шифртекст слишком короткий')
    version, nonce, ct = blob[0], blob[1:13], blob[13:]
    try:
        return AESGCM(derive(purpose, version)).decrypt(nonce, ct, aad)
    except InvalidTag:
        raise CryptoError('данные изменены или привязаны к другой записи')