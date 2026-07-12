"""Data model for JJQubit netlists: element-type registry and dataclasses.

Topology model (SPICE-faithful, single source of truth)
-------------------------------------------------------
A netlist has three top-level collections:

* ``nodes``       -- the declared electrical nodes (a list of string ids).
* ``elements``    -- the circuit components (id, type, parameters-with-units).
* ``connections`` -- the wiring: each connection binds one *terminal* of one
  element (identified by a 0-based terminal index) to exactly one node.

Every element type has a FIXED number of terminals with fixed names (see
:data:`ELEMENT_TYPES`). Two terminals bound to the same node are electrically
the same point; that is how components are wired together.

This module is pure data (stdlib only). It contains NO GUI imports, per the
project's netlist-contract rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import SchemaError
from .units import Quantity

# Schema identification, written into every serialized netlist.
FORMAT = "jjqubit-netlist"
SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ParamSpec:
    """Specification of a single element parameter.

    Args:
        name: Parameter key as it appears in ``element.params``.
        dimension: Required physical dimension (e.g. ``"current"``). A parameter
            value whose unit has a different dimension is a validation error.
        required: If ``True`` the parameter must be present on the element.
    """

    name: str
    dimension: str
    required: bool = True


@dataclass(frozen=True)
class ElementType:
    """Static description of a circuit element type.

    Args:
        name: The ``type`` string used in the netlist (e.g. ``"junction"``).
        terminals: Ordered terminal names. Its length is the terminal count;
            connections address terminals by 0-based index into this tuple.
        params: The parameters this element type accepts, with dimensions.
    """

    name: str
    terminals: tuple[str, ...]
    params: tuple[ParamSpec, ...]

    @property
    def n_terminals(self) -> int:
        """Number of terminals this element type exposes."""
        return len(self.terminals)

    def param(self, name: str) -> ParamSpec | None:
        """Return the :class:`ParamSpec` named ``name``, or ``None``."""
        for spec in self.params:
            if spec.name == name:
                return spec
        return None

    def required_params(self) -> tuple[str, ...]:
        """Names of the parameters that must be present on this element type."""
        return tuple(p.name for p in self.params if p.required)


# ---------------------------------------------------------------------------
# The MVP element-type registry. This is the frozen contract every teammate
# codes against: terminal counts/names and parameter names/dimensions.
# ---------------------------------------------------------------------------
ELEMENT_TYPES: dict[str, ElementType] = {
    "junction": ElementType(
        name="junction",
        terminals=("p", "n"),
        params=(
            ParamSpec("Ic", "current"),      # critical current, e.g. nA
            ParamSpec("Cj", "capacitance"),  # junction self-capacitance, e.g. fF
            ParamSpec("Rn", "resistance"),   # normal-state resistance, e.g. kohm
        ),
    ),
    "capacitor": ElementType(
        name="capacitor",
        terminals=("a", "b"),
        params=(ParamSpec("C", "capacitance"),),  # e.g. fF
    ),
    "inductor": ElementType(
        name="inductor",
        terminals=("a", "b"),
        params=(ParamSpec("L", "inductance"),),  # e.g. nH
    ),
    "resonator": ElementType(
        name="resonator",
        terminals=("a", "b"),
        params=(
            ParamSpec("f0", "frequency"),      # resonance frequency, e.g. GHz
            ParamSpec("Q", "dimensionless"),   # quality factor
        ),
    ),
    "transmission_line": ElementType(
        name="transmission_line",
        terminals=("in", "out"),
        params=(
            ParamSpec("Z0", "resistance"),         # characteristic impedance, ohm
            ParamSpec("length", "length"),         # physical length, e.g. mm
            ParamSpec("eps_eff", "dimensionless"),  # effective permittivity
        ),
    ),
    "current_source": ElementType(
        name="current_source",
        terminals=("pos", "neg"),
        params=(ParamSpec("I", "current"),),  # bias current, e.g. nA
    ),
    "ground": ElementType(
        name="ground",
        terminals=("gnd",),
        params=(),  # ground marks the 0 V reference; no parameters
    ),
}


@dataclass
class Element:
    """A single circuit component.

    Args:
        id: Unique identifier within the netlist (e.g. ``"J1"``).
        type: One of the keys of :data:`ELEMENT_TYPES` (e.g. ``"junction"``).
        params: Mapping of parameter name to :class:`Quantity` (value + unit).
    """

    id: str
    type: str
    params: dict[str, Quantity] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-ready dict."""
        return {
            "id": self.id,
            "type": self.type,
            "params": {k: q.to_dict() for k, q in self.params.items()},
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Element":
        """Build an :class:`Element` from a mapping.

        Raises:
            SchemaError: if the layout or types are wrong.
            UnitError: if a parameter carries an unknown unit.
        """
        if not isinstance(data, dict):
            raise SchemaError(f"element must be an object, got {type(data).__name__}")
        if "id" not in data or "type" not in data:
            raise SchemaError(f"element is missing 'id'/'type': {data!r}")
        if not isinstance(data["id"], str):
            raise SchemaError(f"element 'id' must be a string, got {data['id']!r}")
        if not isinstance(data["type"], str):
            raise SchemaError(f"element 'type' must be a string, got {data['type']!r}")
        raw_params = data.get("params", {})
        if not isinstance(raw_params, dict):
            raise SchemaError(
                f"element {data['id']!r}: 'params' must be an object, "
                f"got {type(raw_params).__name__}"
            )
        params: dict[str, Quantity] = {}
        for name, qdata in raw_params.items():
            if not isinstance(name, str):
                raise SchemaError(
                    f"element {data['id']!r}: parameter name must be a string, "
                    f"got {name!r}"
                )
            params[name] = Quantity.from_dict(qdata)
        return cls(id=data["id"], type=data["type"], params=params)


@dataclass
class Connection:
    """A binding of one element terminal to one node (a wire endpoint).

    Args:
        element: The ``id`` of the element being wired.
        terminal: 0-based index into the element type's ``terminals`` tuple.
        node: The id of the node this terminal is tied to.
    """

    element: str
    terminal: int
    node: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-ready dict."""
        return {"element": self.element, "terminal": self.terminal, "node": self.node}

    @classmethod
    def from_dict(cls, data: Any) -> "Connection":
        """Build a :class:`Connection` from a mapping.

        Raises:
            SchemaError: if the layout or types are wrong.
        """
        if not isinstance(data, dict):
            raise SchemaError(
                f"connection must be an object, got {type(data).__name__}"
            )
        for key in ("element", "terminal", "node"):
            if key not in data:
                raise SchemaError(f"connection is missing {key!r}: {data!r}")
        if not isinstance(data["element"], str):
            raise SchemaError(
                f"connection 'element' must be a string, got {data['element']!r}"
            )
        terminal = data["terminal"]
        if isinstance(terminal, bool) or not isinstance(terminal, int):
            raise SchemaError(
                f"connection 'terminal' must be an integer, got {terminal!r}"
            )
        if not isinstance(data["node"], str):
            raise SchemaError(
                f"connection 'node' must be a string, got {data['node']!r}"
            )
        return cls(element=data["element"], terminal=terminal, node=data["node"])


@dataclass
class Netlist:
    """A complete circuit netlist: nodes, elements and their wiring.

    This is the contract object exchanged between the schematic GUI and the
    solver cores. Build it directly, or load one with
    :func:`core.netlist.load`. Call :meth:`validate` before handing it to a
    solver.

    Args:
        name: Human-readable circuit name.
        nodes: Declared node ids. Every node referenced by a connection must
            appear here.
        elements: The circuit components.
        connections: The terminal-to-node wiring.
        version: Schema version (defaults to the current :data:`SCHEMA_VERSION`).
    """

    name: str = ""
    nodes: list[str] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    connections: list[Connection] = field(default_factory=list)
    version: str = SCHEMA_VERSION

    # -- convenience accessors (handy for solvers / GUI) --------------------

    def element_by_id(self, element_id: str) -> Element | None:
        """Return the element with id ``element_id``, or ``None`` if absent."""
        for el in self.elements:
            if el.id == element_id:
                return el
        return None

    def connections_of(self, element_id: str) -> list[Connection]:
        """Return the connections belonging to ``element_id``, terminal-ordered."""
        found = [c for c in self.connections if c.element == element_id]
        return sorted(found, key=lambda c: c.terminal)

    def nodes_of(self, element_id: str) -> list[str]:
        """Return the nodes each terminal of ``element_id`` is tied to.

        The result is ordered by terminal index. A terminal with no binding
        appears as ``""`` so the list length equals the terminal count when the
        element is fully and validly wired.
        """
        el = self.element_by_id(element_id)
        if el is None:
            return []
        etype = ELEMENT_TYPES.get(el.type)
        n = etype.n_terminals if etype is not None else len(self.connections_of(element_id))
        result = [""] * n
        for c in self.connections_of(element_id):
            if 0 <= c.terminal < n:
                result[c.terminal] = c.node
        return result

    def terminals_on_node(self, node: str) -> list[Connection]:
        """Return every connection (terminal binding) attached to ``node``."""
        return [c for c in self.connections if c.node == node]

    def ground_nodes(self) -> list[str]:
        """Return the node ids that carry a ``ground`` element terminal."""
        grounds: list[str] = []
        for el in self.elements:
            if el.type == "ground":
                for c in self.connections_of(el.id):
                    grounds.append(c.node)
        return grounds

    def validate(self) -> None:
        """Validate this netlist, raising :class:`ValidationError` on problems.

        See :func:`core.netlist.validation.validate` for the full rule list.
        """
        from .validation import validate

        validate(self)
