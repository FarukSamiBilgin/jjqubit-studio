"""JJQubit netlist package: schema, data model, validation and JSON I/O.

This package is the netlist CONTRACT: the schematic GUI produces netlists and
the solver cores consume them, and both sides code against the names exported
here. It is pure data (stdlib only) with NO GUI imports.

Quick start
-----------
    from core.netlist import load, dump, Netlist, ValidationError

    nl = load("examples/transmon_readout.json", validate=True)
    for el in nl.elements:
        print(el.id, el.type, {k: (q.value, q.unit) for k, q in el.params.items()})

Public API
----------
Data model:      :class:`Netlist`, :class:`Element`, :class:`Connection`,
                 :class:`Quantity`, :class:`ElementType`, :class:`ParamSpec`.
Registry:        :data:`ELEMENT_TYPES`, :data:`FORMAT`, :data:`SCHEMA_VERSION`.
Units:           :func:`known_units`, :func:`unit_dimension`, :func:`is_known_unit`,
                 :data:`SI_BASE_UNIT`.
JSON I/O:        :func:`load`, :func:`loads`, :func:`dump`, :func:`dumps`,
                 :func:`to_dict`, :func:`from_dict`.
Validation:      :func:`validate`, :func:`collect_errors`.
Exceptions:      :class:`NetlistError` (base), :class:`SchemaError`,
                 :class:`UnitError`, :class:`ValidationError`.
"""
from __future__ import annotations

from .errors import NetlistError, SchemaError, UnitError, ValidationError
from .io import dump, dumps, from_dict, load, loads, to_dict
from .model import (
    ELEMENT_TYPES,
    FORMAT,
    SCHEMA_VERSION,
    Connection,
    Element,
    ElementType,
    Netlist,
    ParamSpec,
)
from .units import (
    SI_BASE_UNIT,
    Quantity,
    is_known_unit,
    known_units,
    unit_dimension,
)
from .validation import collect_errors, validate

__all__ = [
    # data model
    "Netlist",
    "Element",
    "Connection",
    "Quantity",
    "ElementType",
    "ParamSpec",
    # registry / schema constants
    "ELEMENT_TYPES",
    "FORMAT",
    "SCHEMA_VERSION",
    # units
    "known_units",
    "unit_dimension",
    "is_known_unit",
    "SI_BASE_UNIT",
    # io
    "load",
    "loads",
    "dump",
    "dumps",
    "to_dict",
    "from_dict",
    # validation
    "validate",
    "collect_errors",
    # exceptions
    "NetlistError",
    "SchemaError",
    "UnitError",
    "ValidationError",
]
