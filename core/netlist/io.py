"""JSON serialization / deserialization for netlists (lossless round-trip).

Public helpers:

* :func:`to_dict` / :func:`from_dict` -- convert between a :class:`Netlist` and
  a plain, JSON-ready ``dict``.
* :func:`dumps` / :func:`loads`       -- convert to / from a JSON string.
* :func:`dump`  / :func:`load`        -- write to / read from a file path.

The round-trip ``from_dict(to_dict(nl)) == nl`` is guaranteed to be lossless.
Structural problems raise :class:`SchemaError`; unknown units raise
:class:`UnitError`. Semantic validation is a SEPARATE step (pass
``validate=True`` or call :meth:`Netlist.validate`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import SchemaError
from .model import FORMAT, SCHEMA_VERSION, Connection, Element, Netlist


def to_dict(netlist: Netlist) -> dict[str, Any]:
    """Convert a :class:`Netlist` into a JSON-ready dictionary."""
    return {
        "format": FORMAT,
        "version": netlist.version,
        "name": netlist.name,
        "nodes": list(netlist.nodes),
        "elements": [el.to_dict() for el in netlist.elements],
        "connections": [c.to_dict() for c in netlist.connections],
    }


def from_dict(data: Any) -> Netlist:
    """Build a :class:`Netlist` from a plain dictionary.

    Args:
        data: A mapping matching the netlist schema (as produced by
            :func:`to_dict`).

    Returns:
        The reconstructed netlist (NOT yet semantically validated).

    Raises:
        SchemaError: if the layout, keys or value types are wrong.
        UnitError: if any parameter carries an unknown unit.
    """
    if not isinstance(data, dict):
        raise SchemaError(f"netlist must be an object, got {type(data).__name__}")

    fmt = data.get("format", FORMAT)
    if fmt != FORMAT:
        raise SchemaError(f"unexpected netlist format {fmt!r} (expected {FORMAT!r})")

    version = data.get("version", SCHEMA_VERSION)
    if not isinstance(version, str):
        raise SchemaError(f"'version' must be a string, got {version!r}")

    name = data.get("name", "")
    if not isinstance(name, str):
        raise SchemaError(f"'name' must be a string, got {name!r}")

    raw_nodes = data.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise SchemaError(f"'nodes' must be a list, got {type(raw_nodes).__name__}")
    nodes: list[str] = []
    for n in raw_nodes:
        if not isinstance(n, str):
            raise SchemaError(f"node id must be a string, got {n!r}")
        nodes.append(n)

    raw_elements = data.get("elements", [])
    if not isinstance(raw_elements, list):
        raise SchemaError(
            f"'elements' must be a list, got {type(raw_elements).__name__}"
        )
    elements = [Element.from_dict(e) for e in raw_elements]

    raw_connections = data.get("connections", [])
    if not isinstance(raw_connections, list):
        raise SchemaError(
            f"'connections' must be a list, got {type(raw_connections).__name__}"
        )
    connections = [Connection.from_dict(c) for c in raw_connections]

    return Netlist(
        name=name,
        nodes=nodes,
        elements=elements,
        connections=connections,
        version=version,
    )


def dumps(netlist: Netlist, *, indent: int = 2, validate: bool = False) -> str:
    """Serialize a :class:`Netlist` to a JSON string.

    Args:
        netlist: The netlist to serialize.
        indent: JSON indentation (pretty-printed by default).
        validate: If ``True``, run :meth:`Netlist.validate` first.

    Raises:
        ValidationError: if ``validate`` is ``True`` and the netlist is invalid.
    """
    if validate:
        netlist.validate()
    return json.dumps(to_dict(netlist), indent=indent, ensure_ascii=False)


def loads(text: str, *, validate: bool = False) -> Netlist:
    """Parse a JSON string into a :class:`Netlist`.

    Args:
        text: JSON text.
        validate: If ``True``, run :meth:`Netlist.validate` after parsing.

    Raises:
        SchemaError: if the JSON is malformed or does not match the schema.
        UnitError: if a parameter carries an unknown unit.
        ValidationError: if ``validate`` is ``True`` and the netlist is invalid.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"invalid JSON: {exc}") from exc
    netlist = from_dict(data)
    if validate:
        netlist.validate()
    return netlist


def dump(
    netlist: Netlist,
    path: str | Path,
    *,
    indent: int = 2,
    validate: bool = False,
) -> None:
    """Write a :class:`Netlist` to ``path`` as JSON (UTF-8).

    Args:
        netlist: The netlist to write.
        path: Destination file path.
        indent: JSON indentation.
        validate: If ``True``, run :meth:`Netlist.validate` before writing.
    """
    text = dumps(netlist, indent=indent, validate=validate)
    Path(path).write_text(text + "\n", encoding="utf-8")


def load(path: str | Path, *, validate: bool = False) -> Netlist:
    """Read a :class:`Netlist` from a JSON file at ``path``.

    Args:
        path: Source file path.
        validate: If ``True``, run :meth:`Netlist.validate` after loading.

    Raises:
        SchemaError: if the file is malformed or does not match the schema.
        UnitError: if a parameter carries an unknown unit.
        ValidationError: if ``validate`` is ``True`` and the netlist is invalid.
    """
    text = Path(path).read_text(encoding="utf-8")
    return loads(text, validate=validate)
