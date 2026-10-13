# iot_emulator/sensors/quantize.py
def quantize(x, step):
    '''Округление до шага разрешения q. Ошибка не больше q/2.'''
    return round(round(x / step) * step, 2)