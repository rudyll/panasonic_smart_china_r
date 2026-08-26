"""Temperature decoding helpers for Panasonic AC status responses."""

import math


INVALID_TEMPERATURE_VALUES = frozenset({127, 255, 65535})


def decode_temperature(raw_value, scale: int = 2) -> float | None:
    """Decode a scaled AC temperature, returning None for protocol sentinels."""
    if raw_value is None or isinstance(raw_value, bool) or scale <= 0:
        return None
    try:
        numeric = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or numeric in INVALID_TEMPERATURE_VALUES:
        return None
    return numeric / scale
