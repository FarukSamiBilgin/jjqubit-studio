"""Exception hierarchy for the JJQubit netlist package.

All exceptions raised by :mod:`core.netlist` derive from :class:`NetlistError`,
so callers can catch the whole family with a single ``except NetlistError``.

The distinct subclasses let teammates react to specific failure modes:

* :class:`SchemaError`     -- the JSON structure is malformed (missing keys,
  wrong types). Raised during deserialization, before any physics is inspected.
* :class:`UnitError`       -- a unit token is not in the known unit registry.
* :class:`ValidationError` -- the netlist is structurally well-formed but
  semantically invalid (floating node, no ground, missing parameter, wrong
  parameter dimension, ...). Carries the full list of problems in ``.errors``.
"""
from __future__ import annotations


class NetlistError(Exception):
    """Base class for every error raised by :mod:`core.netlist`."""


class SchemaError(NetlistError):
    """Raised when the raw JSON/dict layout does not match the netlist schema."""


class UnitError(NetlistError):
    """Raised when a unit token is not part of the known unit registry."""


class ValidationError(NetlistError):
    """Raised when a well-formed netlist fails semantic validation.

    Attributes:
        errors: Human-readable messages, one per detected problem. Each message
            names the offending element id, node id and/or parameter so the
            caller can point the user straight at the mistake.
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors: list[str] = list(errors)
        if len(self.errors) == 1:
            summary = self.errors[0]
        else:
            joined = "\n  - ".join(self.errors)
            summary = f"{len(self.errors)} validation error(s):\n  - {joined}"
        super().__init__(summary)
