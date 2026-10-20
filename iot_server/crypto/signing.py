import hashlib
import hmac


def secret_aad(device_id):
    '''Привязка зашифрованного секрета к устройству (AAD для cipher).'''
    return f'device|{device_id}'.encode()


def sign(secret, body, ts, seq):
    msg = body + b'|' + ts.encode() + b'|' + str(seq).encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify(body, ts, seq, sig, secret):
    expected = sign(secret, body, ts, seq)
    # compare_digest: сравнение за постоянное время (защита от атак по времени)
    return hmac.compare_digest(expected.encode(), sig.encode('utf-8'))