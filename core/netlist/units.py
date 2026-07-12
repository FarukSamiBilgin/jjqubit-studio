"""Physical quantities and the unit registry for JJQubit netlists.

Every numeric parameter in a netlist carries an EXPLICIT unit. Unit confusion is
the most common source of bugs in superconducting-circuit design, so units are
first-class here: they are validated against a known registry and can be
converted to SI base units via :meth:`Quantity.to_si`.

Conventions
-----------
* All identifiers and unit tokens are ASCII.
* The micro prefix is written ``u`` (e.g. ``uA`` = microampere, ``um`` = micron).
* Dimensionless quantities (quality factor ``Q``, effective permittivity
  ``eps_eff``) use an EMPTY unit string ``""``. The aliases ``"1"`` and
  ``"dimensionless"`` are also accepted on input.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import SchemaError, UnitError

# Canonical SI base unit token for each physical dimension.
SI_BASE_UNIT: dict[str, str] = {
    "frequency": "Hz",
    "capacitance": "F",
    "inductance": "H",
    "current": "A",
    "resistance": "ohm",
    "length": "m",
    "time": "s",
    "voltage": "V",
    "dimensionless": "",
}

# unit token -> (dimension, multiplicative factor to the SI base unit).
_UNITS: dict[str, tuple[str, float]] = {
    # frequency (SI: Hz)
    "Hz": ("frequency", 1.0),
    "kHz": ("frequency", 1e3),
    "MHz": ("frequency", 1e6),
    "GHz": ("frequency", 1e9),
    "THz": ("frequency", 1e12),
    # capacitance (SI: F)
    "F": ("capacitance", 1.0),
    "mF": ("capacitance", 1e-3),
    "uF": ("capacitance", 1e-6),
    "nF": ("capacitance", 1e-9),
    "pF": ("capacitance", 1e-12),
    "fF": ("capacitance", 1e-15),
    "aF": ("capacitance", 1e-18),
    # inductance (SI: H)
    "H": ("inductance", 1.0),
    "mH": ("inductance", 1e-3),
    "uH": ("inductance", 1e-6),
    "nH": ("inductance", 1e-9),
    "pH": ("inductance", 1e-12),
    # current (SI: A)
    "A": ("current", 1.0),
    "mA": ("current", 1e-3),
    "uA": ("current", 1e-6),
    "nA": ("current", 1e-9),
    "pA": ("current", 1e-12),
    # resistance / impedance (SI: ohm)
    "ohm": ("resistance", 1.0),
    "kohm": ("resistance", 1e3),
    "Mohm": ("resistance", 1e6),
    # length (SI: m)
    "m": ("length", 1.0),
    "cm": ("length", 1e-2),
    "mm": ("length", 1e-3),
    "um": ("length", 1e-6),
    "nm": ("length", 1e-9),
    # time (SI: s)
    "s": ("time", 1.0),
    "ms": ("time", 1e-3),
    "us": ("time", 1e-6),
    "ns": ("time", 1e-9),
    "ps": ("time", 1e-12),
    # voltage (SI: V)
    "V": ("voltage", 1.0),
    "mV": ("voltage", 1e-3),
    "uV": ("voltage", 1e-6),
    # dimensionless (SI: none) -- "" is canonical, "1"/"dimensionless" are aliases
    "": ("dimensionless", 1.0),
    "1": ("dimensionless", 1.0),
    "dimensionless": ("dimensionless", 1.0),
}


def is_known_unit(unit: str) -> bool:
    """Return ``True`` if ``unit`` is a token in the unit registry."""
    return unit in _UNITS


def unit_dimension(unit: str) -> str:
    """Return the physical dimension (e.g. ``"current"``) for a unit token.

    Raises:
        UnitError: if ``unit`` is not in the registry.
    """
    try:
        return _UNITS[unit][0]
    except KeyError:
        raise UnitError(f"unknown unit {unit!r}") from None


def known_units() -> list[str]:
    """Return all registered unit tokens, sorted for stable display."""
    return sorted(_UNITS)


@dataclass(frozen=True)
class Quantity:
    """A physical value together with its EXPLICIT unit.

    The unit is validated against the registry at construction time, so a
    ``Quantity`` can never hold an unknown unit. Use :meth:`to_si` to obtain the
    value in SI base units for numerical work.

    Args:
        value: The numeric magnitude. Ints are coerced to ``float``.
        unit: A registered unit token (e.g. ``"GHz"``, ``"fF"``, ``"nA"``,
            ``"ohm"``, or ``""`` for a dimensionless quantity).

    Raises:
        UnitError: if ``unit`` is not a registered token.
    """

    value: float
    unit: str

    def __post_init__(self) -> None:
        # Coerce numeric value to float for stable equality / round-trip.
        object.__setattr__(self, "value", float(self.value))
        if self.unit not in _UNITS:
            raise UnitError(
                f"unknown unit {self.unit!r} for value {self.value!r}"
            )

    @property
    def dimension(self) -> str:
        """The physical dimension of this quantity (e.g. ``"capacitance"``)."""
        return _UNITS[self.unit][0]

    def to_si(self) -> float:
        """Return the magnitude converted to the SI base unit for its dimension.

        Examples: ``Quantity(5, "GHz").to_si()`` -> ``5e9`` (Hz);
        ``Quantity(2, "fF").to_si()`` -> ``2e-15`` (F).
        """
        return self.value * _UNITS[self.unit][1]

    def si_unit(self) -> str:
        """Return the SI base unit token for this quantity's dimension."""
        return SI_BASE_UNIT[self.dimension]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain ``{"value": ..., "unit": ...}`` dict."""
        return {"value": self.value, "unit": self.unit}

    @classmethod
    def from_dict(cls, data: Any) -> "Quantity":
        """Build a :class:`Quantity` from a ``{"value", "unit"}`` mapping.

        Raises:
            SchemaError: if ``data`` is not a mapping with numeric ``value`` and
                string ``unit`` keys.
            UnitError: if the ``unit`` token is unknown.
        """
        if not isinstance(data, dict):
            raise SchemaError(
                f"quantity must be an object with 'value' and 'unit', "
                f"got {type(data).__name__}"
            )
        if "value" not in data or "unit" not in data:
            raise SchemaError(
                f"quantity is missing required keys 'value'/'unit': {data!r}"
            )
        value = data["value"]
        unit = data["unit"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaError(f"quantity 'value' must be a number, got {value!r}")
        if not isinstance(unit, str):
            raise SchemaError(f"quantity 'unit' must be a string, got {unit!r}")
        return cls(value=float(value), unit=unit)
