"""Topology extraction: find the RCSJ-bias and readout structure in a netlist.

The netlist contract (``core.netlist``, FROZEN, Task #1) gives us pure
topology: nodes, elements, and terminal-to-node wiring. This module walks
that topology (:meth:`~core.netlist.Netlist.nodes_of`,
:meth:`~core.netlist.Netlist.terminals_on_node`,
:meth:`~core.netlist.Netlist.ground_nodes`) to answer classical-solver
questions -- "which node is the current-biased junction on", "what shunts
it", "which resonator feeds which transmission line and into what load" --
WITHOUT hardcoding element ids, mirroring the approach already used by
``core/solvers/quantum/topology.py``.

MVP scope (docs/task.md, Gorev 2):

* RCSJ bias circuit: exactly one ``junction`` driven by exactly one
  ``current_source`` on the same node (see :func:`extract_rcsj_topology`).
* Readout circuit: exactly one ``resonator`` capacitively coupled to a
  ``transmission_line`` that is terminated by a real ``resistor`` (see
  :func:`extract_readout_topology`, and ``docs/netlist_schema.md`` section 4's
  note on why a matched-load resistor -- not a port capacitor -- terminates
  the feedline).

A netlist may satisfy either, both, or neither topology; the CLI (see
``cli.py``) computes whichever parts are available and skips the rest.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.netlist import Element, Netlist


class TopologyError(Exception):
    """Raised when a netlist does not have a topology this solver supports.

    Deliberately distinct from :class:`core.netlist.ValidationError`: the
    netlist may be perfectly valid (well-formed, fully wired, grounded) and
    still describe a topology this MVP solver does not (yet) handle, e.g. two
    junctions, no current source, or a resonator with no real termination.
    """


def _elements_of_type(netlist: Netlist, element_type: str) -> list[Element]:
    return [el for el in netlist.elements if el.type == element_type]


def _single_ground_node(netlist: Netlist) -> str:
    """Return the netlist's ground node, requiring exactly one distinct one.

    MVP circuits have a single 0V reference; if a netlist declares several we
    cannot pick one without guessing, so we raise.
    """
    grounds = set(netlist.ground_nodes())
    if len(grounds) == 0:
        raise TopologyError(
            "netlist has no 'ground' element; cannot identify the 0V reference"
        )
    if len(grounds) > 1:
        raise TopologyError(
            f"netlist has {len(grounds)} distinct ground nodes {sorted(grounds)}; "
            "multi-ground-plane circuits are out of MVP scope"
        )
    return next(iter(grounds))


# ---------------------------------------------------------------------------
# RCSJ bias circuit
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RCSJTopology:
    """The current-biased Josephson junction located in a netlist.

    Args:
        junction: The sole ``junction`` element.
        current_source: The sole ``current_source`` element, injecting into
            ``bias_node``.
        bias_node: The non-ground node both the junction and the current
            source are wired to.
        ground_node: The ground node the junction's other terminal is on.
        capacitor_ids: Ids of every ``capacitor`` element with a terminal on
            ``bias_node`` (shunt capacitance seen by the junction, in
            addition to its own ``Cj`` -- any capacitance at the node
            contributes to the total shunt capacitance, exactly as
            ``core/solvers/quantum/topology.py`` sums capacitors for Ec).
        shunt_resistor_ids: Ids of any *separate* ``resistor`` element(s)
            with a terminal on ``bias_node``, wired in parallel with the
            junction's own normal-state resistance ``Rn``. Empty in the
            bundled ``examples/rcsj_bias.json`` (Rn alone shunts the
            junction there).
        inductor_ids: Ids of any ``inductor`` element with a terminal on
            ``bias_node``. NOT included in the v1 RCSJ ODE -- see the module
            docstring in ``rcsj.py`` for why -- but reported here (and
            surfaced in the HDF5 ``/assumptions`` group) for transparency
            rather than silently dropped.
    """

    junction: Element
    current_source: Element
    bias_node: str
    ground_node: str
    capacitor_ids: tuple[str, ...]
    shunt_resistor_ids: tuple[str, ...]
    inductor_ids: tuple[str, ...]


def extract_rcsj_topology(netlist: Netlist) -> RCSJTopology:
    """Locate the single current-biased junction and everything shunting it.

    Args:
        netlist: A validated :class:`~core.netlist.Netlist`.

    Returns:
        The :class:`RCSJTopology`.

    Raises:
        TopologyError: if there is not exactly one ``junction`` element, not
            exactly one ``current_source`` element, the current source does
            not inject into the junction's bias node, or there is no
            unambiguous 0V reference.
    """
    junctions = _elements_of_type(netlist, "junction")
    if len(junctions) == 0:
        raise TopologyError("netlist has no 'junction' element; nothing to bias")
    if len(junctions) > 1:
        raise TopologyError(
            f"netlist has {len(junctions)} junctions "
            f"({[j.id for j in junctions]}); multi-junction circuits are out of MVP scope"
        )
    junction = junctions[0]

    sources = _elements_of_type(netlist, "current_source")
    if len(sources) == 0:
        raise TopologyError(
            "netlist has no 'current_source' element; nothing biases the junction "
            "(RCSJ time-domain/I-V analysis needs a driving current)"
        )
    if len(sources) > 1:
        raise TopologyError(
            f"netlist has {len(sources)} current sources "
            f"({[s.id for s in sources]}); multi-source RCSJ bias is out of MVP scope"
        )
    current_source = sources[0]

    ground_node = _single_ground_node(netlist)

    p_node, n_node = netlist.nodes_of(junction.id)
    if not p_node or not n_node:
        raise TopologyError(f"junction {junction.id!r} has an unbound terminal")
    non_ground = {p_node, n_node} - {ground_node}
    if len(non_ground) != 1:
        raise TopologyError(
            f"junction {junction.id!r} is wired {p_node!r}<->{n_node!r}; expected exactly "
            f"one terminal on ground node {ground_node!r} and one on the bias node"
        )
    bias_node = next(iter(non_ground))

    pos_node, neg_node = netlist.nodes_of(current_source.id)
    if {pos_node, neg_node} != {bias_node, ground_node}:
        raise TopologyError(
            f"current source {current_source.id!r} is wired {pos_node!r}<->{neg_node!r}; "
            f"expected it to drive the junction's bias node {bias_node!r} against "
            f"ground node {ground_node!r}"
        )

    capacitor_ids = tuple(
        c.element
        for c in netlist.terminals_on_node(bias_node)
        if (el := netlist.element_by_id(c.element)) is not None
        and el.type == "capacitor"
    )
    shunt_resistor_ids = tuple(
        c.element
        for c in netlist.terminals_on_node(bias_node)
        if (el := netlist.element_by_id(c.element)) is not None
        and el.type == "resistor"
    )
    inductor_ids = tuple(
        c.element
        for c in netlist.terminals_on_node(bias_node)
        if (el := netlist.element_by_id(c.element)) is not None
        and el.type == "inductor"
    )

    return RCSJTopology(
        junction=junction,
        current_source=current_source,
        bias_node=bias_node,
        ground_node=ground_node,
        capacitor_ids=capacitor_ids,
        shunt_resistor_ids=shunt_resistor_ids,
        inductor_ids=inductor_ids,
    )


# ---------------------------------------------------------------------------
# Readout circuit: resonator -> coupling capacitor -> transmission line -> load
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReadoutTopology:
    """The resonator + feedline + termination chain located in a netlist.

    Args:
        resonator: The sole ``resonator`` element.
        active_node: The non-ground node the resonator's "hot" terminal is on.
        ground_node: The ground node the resonator's other terminal is on.
        coupling_capacitor_ids: Ids of every ``capacitor`` bridging
            ``active_node`` directly to ``feedline_node``.
        feedline_node: The node on the near side of the transmission line
            (the side coupled to the resonator).
        transmission_line: The sole ``transmission_line`` element.
        far_node: The transmission line's other terminal (opposite
            ``feedline_node``).
        termination: The ``resistor`` element terminating ``far_node`` to
            ``ground_node`` (the real matched-load resistance the S21
            calculation needs -- see docs/netlist_schema.md section 4).
    """

    resonator: Element
    active_node: str
    ground_node: str
    coupling_capacitor_ids: tuple[str, ...]
    feedline_node: str
    transmission_line: Element
    far_node: str
    termination: Element


def extract_resonator_topology(netlist: Netlist) -> tuple[Element, str, str]:
    """Locate the single lumped LC resonator and its active node.

    Returns:
        ``(resonator, active_node, ground_node)``.

    Raises:
        TopologyError: if there is not exactly one ``resonator`` element or
            its terminals are not wired to exactly one ground node and one
            non-ground node.
    """
    resonators = _elements_of_type(netlist, "resonator")
    if len(resonators) == 0:
        raise TopologyError("netlist has no 'resonator' element; nothing to read out")
    if len(resonators) > 1:
        raise TopologyError(
            f"netlist has {len(resonators)} resonators "
            f"({[r.id for r in resonators]}); multi-resonator circuits are out of MVP scope"
        )
    resonator = resonators[0]
    ground_node = _single_ground_node(netlist)

    a_node, b_node = netlist.nodes_of(resonator.id)
    if not a_node or not b_node:
        raise TopologyError(f"resonator {resonator.id!r} has an unbound terminal")
    non_ground = {a_node, b_node} - {ground_node}
    if len(non_ground) != 1:
        raise TopologyError(
            f"resonator {resonator.id!r} is wired {a_node!r}<->{b_node!r}; expected exactly "
            f"one terminal on ground node {ground_node!r} and one on the active node"
        )
    active_node = next(iter(non_ground))
    return resonator, active_node, ground_node


def extract_readout_topology(netlist: Netlist) -> ReadoutTopology:
    """Locate the resonator, its feedline coupling, and the line's termination.

    Args:
        netlist: A validated :class:`~core.netlist.Netlist`.

    Returns:
        The :class:`ReadoutTopology`.

    Raises:
        TopologyError: if there is not exactly one resonator, it is not
            capacitively coupled to a node of a ``transmission_line``, or
            that line's far end is not terminated by a real ``resistor`` to
            ground.
    """
    resonator, active_node, ground_node = extract_resonator_topology(netlist)

    transmission_lines = _elements_of_type(netlist, "transmission_line")
    if len(transmission_lines) == 0:
        raise TopologyError(
            "netlist has no 'transmission_line' element; nothing to compute S21 through"
        )
    if len(transmission_lines) > 1:
        raise TopologyError(
            f"netlist has {len(transmission_lines)} transmission lines "
            f"({[t.id for t in transmission_lines]}); multi-line feedlines are out of MVP scope"
        )
    tl = transmission_lines[0]
    in_node, out_node = netlist.nodes_of(tl.id)
    if not in_node or not out_node:
        raise TopologyError(f"transmission_line {tl.id!r} has an unbound terminal")

    coupling_capacitor_ids: list[str] = []
    feedline_node = ""
    for cap in _elements_of_type(netlist, "capacitor"):
        nodes = set(netlist.nodes_of(cap.id))
        if active_node in nodes:
            other = next(iter(nodes - {active_node}), None)
            if other in (in_node, out_node):
                coupling_capacitor_ids.append(cap.id)
                feedline_node = other
    if not coupling_capacitor_ids:
        raise TopologyError(
            f"resonator {resonator.id!r} (active node {active_node!r}) is not capacitively "
            f"coupled to transmission_line {tl.id!r} ({in_node!r}<->{out_node!r})"
        )

    far_node = out_node if feedline_node == in_node else in_node

    termination = None
    for c in netlist.terminals_on_node(far_node):
        el = netlist.element_by_id(c.element)
        if el is not None and el.type == "resistor":
            other_nodes = set(netlist.nodes_of(el.id))
            if ground_node in other_nodes:
                termination = el
                break
    if termination is None:
        raise TopologyError(
            f"transmission_line {tl.id!r} far end ({far_node!r}) is not terminated by a "
            f"'resistor' to ground; S21 needs a real termination resistance "
            "(see docs/netlist_schema.md section 4)"
        )

    return ReadoutTopology(
        resonator=resonator,
        active_node=active_node,
        ground_node=ground_node,
        coupling_capacitor_ids=tuple(coupling_capacitor_ids),
        feedline_node=feedline_node,
        transmission_line=tl,
        far_node=far_node,
        termination=termination,
    )
