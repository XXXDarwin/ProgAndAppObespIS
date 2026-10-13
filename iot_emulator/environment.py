# iot_emulator/environment.py
import math


def check_nyquist(frequencies, fs_hz):
    '''Все частоты гармоник должны быть строго меньше Fs/2, иначе aliasing.'''
    limit = fs_hz / 2
    for f in frequencies:
        if f >= limit:
            raise ValueError(f'Частота {f} Гц не меньше предела Найквиста {limit} Гц')


class Environment:
    '''Истинная температура и влажность зоны (до датчика).'''

    def __init__(self, t_start=22.0, humidity=45.0, tau_s=120.0,
                 amplitudes=(0.8, 0.3, 0.1), frequencies=(0.010, 0.030, 0.080),
                 fs_hz=0.2):
        if len(amplitudes) != len(frequencies):
            raise ValueError('Длины векторов A и F должны совпадать')
        check_nyquist(frequencies, fs_hz)
        self.t_base = t_start
        self.t_target = t_start
        self.humidity = humidity
        self.tau_s = tau_s
        self.amplitudes = tuple(amplitudes)
        self.frequencies = tuple(frequencies)

    @classmethod
    def from_config(cls, cfg):
        c = cfg['climate']
        return cls(t_start=c['t_start'], humidity=c['humidity'], tau_s=c['tau_s'],
                   amplitudes=c['harmonics']['amplitudes'],
                   frequencies=c['harmonics']['frequencies_hz'],
                   fs_hz=c['fs_hz'])

    def set_target(self, temperature):
        self.t_target = temperature

    def update(self, dt):
        '''Инерция: T(t+dt) = T(t) + (1 - exp(-dt/tau)) * (T_цель - T(t)).'''
        k = 1 - math.exp(-dt / self.tau_s)
        self.t_base += k * (self.t_target - self.t_base)

    def temperature_at(self, t):
        '''T_ист(t) = T_баз + сумма Ak * sin(2*pi*Fk*t).'''
        harm = sum(a * math.sin(2 * math.pi * f * t)
                   for a, f in zip(self.amplitudes, self.frequencies))
        return self.t_base + harm


class ShelfModel:
    '''Истинный вес полки. События вызывать в хронологическом порядке.'''

    def __init__(self, shelf_id, unit_weight_g, items, base_g=0.0,
                 tau_s=0.15, omega_rad_s=15.0):
        if unit_weight_g <= 0 or items < 0:
            raise ValueError('Некорректные параметры полки')
        self.shelf_id = shelf_id
        self.unit_weight_g = unit_weight_g
        self.items = float(items)
        self.base_g = base_g          # масса пустой тары
        self.tau_s = tau_s
        self.omega = omega_rad_s
        self._w_end = base_g + items * unit_weight_g
        self._w_start = self._w_end
        self._t0 = 0.0

    @classmethod
    def from_config(cls, cfg, shelf_id, unit_weight_g, items, base_g=0.0):
        w = cfg['weight']
        return cls(shelf_id, unit_weight_g, items, base_g,
                   tau_s=w['settle_tau_s'], omega_rad_s=w['omega_rad_s'])

    def true_weight(self, t):
        '''W(t) = W_кон + (W_нач - W_кон) * exp(-(t-t0)/tau) * cos(omega*(t-t0)).'''
        dt = t - self._t0
        if dt <= 0:
            return self._w_start
        decay = math.exp(-dt / self.tau_s) * math.cos(self.omega * dt)
        return self._w_end + (self._w_start - self._w_end) * decay

    def _change(self, delta_items, t0):
        current = self.true_weight(t0)
        self.items += delta_items
        self._w_start = current
        self._w_end = self.base_g + self.items * self.unit_weight_g
        self._t0 = t0

    def remove_items(self, n, t0):
        '''Снять n штук (можно дробное, например 1.5 для сценария anomaly).'''
        if n < 0 or n > self.items + 1e-9:
            raise ValueError('Нельзя снять такое количество')
        self._change(-n, t0)

    def add_items(self, n, t0):
        if n < 0:
            raise ValueError('Количество должно быть неотрицательным')
        self._change(n, t0)