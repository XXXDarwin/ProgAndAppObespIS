# iot_emulator/sensors/climate.py
from sensors.quantize import quantize

T_MIN, T_MAX = -40.0, 85.0     # физический диапазон датчика (контракт ЛР №2)
H_MIN, H_MAX = 0.0, 100.0


class ClimateSensor:
    '''Цифровой датчик T/H: истина + шум + дрейф + квантование + сбои.'''

    FAULTS = (None, 'dropout', 'stuck')

    def __init__(self, env, rng, sigma_t=0.3, sigma_h=1.0,
                 step_t=0.1, step_h=0.1, drift_per_h=0.0):
        self.env, self.rng = env, rng
        self.sigma_t, self.sigma_h = sigma_t, sigma_h
        self.step_t, self.step_h = step_t, step_h
        self.drift = drift_per_h
        self.fault = None
        self._last = None
        self._outlier = None

    @classmethod
    def from_config(cls, env, rng, cfg):
        c = cfg['climate']
        return cls(env, rng, c['sigma_t'], c['sigma_h'],
                   c['step_t'], c['step_h'], c['drift_per_h'])

    def set_fault(self, kind):
        if kind not in self.FAULTS:
            raise ValueError(f'Неизвестный сбой: {kind}')
        self.fault = kind

    def inject_outlier(self, delta_t=8.5, delta_h=0.0):
        '''Одиночный выброс: добавляется только к следующему отсчёту.'''
        self._outlier = (delta_t, delta_h)

    def read(self, t):
        '''Возвращает (T, H) или None при пропадании ответа.'''
        if self.fault == 'dropout':
            return None
        if self.fault == 'stuck' and self._last is not None:
            return self._last
        temp = (self.env.temperature_at(t) + self.rng.gauss(0, self.sigma_t)
                + self.drift * t / 3600)
        hum = self.env.humidity + self.rng.gauss(0, self.sigma_h)
        if self._outlier is not None:
            temp += self._outlier[0]
            hum += self._outlier[1]
            self._outlier = None
        temp = quantize(min(max(temp, T_MIN), T_MAX), self.step_t)
        hum = quantize(min(max(hum, H_MIN), H_MAX), self.step_h)
        self._last = (temp, hum)
        return self._last