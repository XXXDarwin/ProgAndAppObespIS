# iot_emulator/sensors/weight.py
from sensors.quantize import quantize


class WeightSensor:
    '''Аналоговый тензодатчик с АЦП: истина + смещение нуля + шум + квантование.'''

    def __init__(self, shelf, rng, sigma_g=1.5, step_g=0.5, zero_offset_g=0.0):
        self.shelf, self.rng = shelf, rng
        self.sigma, self.step, self.offset = sigma_g, step_g, zero_offset_g

    @classmethod
    def from_config(cls, shelf, rng, cfg):
        w = cfg['weight']
        return cls(shelf, rng, w['sigma_g'], w['step_g'], w['zero_offset_g'])

    def read(self, t):
        w = self.shelf.true_weight(t) + self.offset + self.rng.gauss(0, self.sigma)
        return max(0.0, quantize(w, self.step))   # контракт: weight_g >= 0