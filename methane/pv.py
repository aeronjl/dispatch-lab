"""Pure reference-plane DC conversion. Inputs are hourly mean irradiance and temperature."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Parameters:
    solar_kw: float
    loss_fraction: float
    noct_c: float
    temperature_coefficient: float

    def __post_init__(self):
        if (
            not all(isfinite(v) for v in vars(self).values())
            or self.solar_kw < 0
            or not 0 <= self.loss_fraction <= 1
        ):
            raise ValueError("Invalid reference solar conversion parameters")


def convert(p: Parameters, irradiance_wm2, ambient_c):
    if not all(isfinite(v) for v in (irradiance_wm2, ambient_c)) or irradiance_wm2 < 0:
        raise ValueError("Nonnegative finite irradiance and finite temperature required")
    panel = ambient_c + (p.noct_c - 20) * irradiance_wm2 / 800
    factor = max(0, 1 + p.temperature_coefficient * (panel - 25))
    return min(
        p.solar_kw, max(0, p.solar_kw * irradiance_wm2 / 1000 * (1 - p.loss_fraction) * factor)
    )


def dc_power(irradiance, ambient, p, w):
    """Compatibility adapter; conversion kernel requires no plant configuration."""
    return convert(
        Parameters(p.solar_kw, w.loss_fraction, w.noct_c, w.temperature_coefficient),
        irradiance,
        ambient,
    )
