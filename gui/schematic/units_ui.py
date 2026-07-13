"""UI-facing helpers for working with the frozen netlist unit registry.

Keeps the property editor honest to the contract: unit choices for a given
parameter are derived from ``core.netlist.ELEMENT_TYPES``/``known_units``/
``unit_dimension`` at call time, never hardcoded per element type. If the
netlist-core team adds a unit or a dimension, the property editor picks it up
automatically.
"""

from __future__ import annotations

from core.netlist import ELEMENT_TYPES, ParamSpec, known_units, unit_dimension


def units_for_dimension(dimension: str) -> list[str]:
    """Return every registered unit token whose dimension is ``dimension``.

    Args:
        dimension: A physical dimension name, e.g. ``"current"`` or
            ``"dimensionless"``.

    Returns:
        Unit tokens accepted for that dimension, sorted for stable display
        (e.g. ``["A", "mA", "nA", "pA", "uA"]`` for ``"current"``). For
        ``"dimensionless"`` this includes the canonical empty-string token
        alongside its aliases.
    """
    return [u for u in known_units() if unit_dimension(u) == dimension]


def param_specs_for(type_name: str) -> tuple[ParamSpec, ...]:
    """Return the ordered parameter specs for element type ``type_name``.

    Raises:
        KeyError: if ``type_name`` is not a registered element type.
    """
    return ELEMENT_TYPES[type_name].params


def default_unit_for(dimension: str) -> str:
    """Return a reasonable default unit token to preselect for ``dimension``.

    Picks the registry's typical/"nice" unit rather than the raw SI base unit
    where one is documented in ``docs/netlist_schema.md`` (e.g. ``nA`` for
    ``current``, ``fF`` for ``capacitance``, ``GHz`` for ``frequency``).
    Falls back to whichever unit sorts first for dimensions with no preferred
    default.
    """
    preferred = {
        "current": "nA",
        "capacitance": "fF",
        "inductance": "nH",
        "resistance": "ohm",
        "frequency": "GHz",
        "length": "mm",
        "time": "ns",
        "voltage": "mV",
        "dimensionless": "",
    }
    choices = units_for_dimension(dimension)
    if not choices:
        raise ValueError(f"no registered units for dimension {dimension!r}")
    pick = preferred.get(dimension)
    if pick is not None and pick in choices:
        return pick
    return choices[0]
