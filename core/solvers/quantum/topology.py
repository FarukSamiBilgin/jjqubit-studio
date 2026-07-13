"""Topology extraction: find the qubit/resonator/coupling structure in a netlist.

The netlist contract (``core.netlist``, FROZEN, Task #1) gives us pure
topology: nodes, elements, and terminal-to-node wiring. This module walks
that topology with :meth:`~core.netlist.Netlist.nodes_of`,
:meth:`~core.netlist.Netlist.terminals_on_node` and
:meth:`~core.netlist.Netlist.ground_nodes` to answer circuit-quantization
questions -- "which node is the qubit island", "what capacitance sits on
that node", "which capacitor bridges the qubit to the resonator" -- WITHOUT
hardcoding element ids. This keeps the quantum solver correct for any
netlist that follows the single-transmon + single-resonator MVP topology,
not just the bundled example.

MVP scope (see docs/task.md, Gorev 3): exactly one ``junction`` element and
exactly one ``resonator`` element per netlist. Multi-qubit / multi-resonator
circuits are out of scope (docs/task.md, "Kapsam disi").
"""

from __future__ import annotations

from dataclasses import dataclass

from core.netlist import Element, Netlist


class TopologyError(Exception):
    """Raised when a netlist does not have the MVP single-transmon topology.

    This is deliberately distinct from :class:`core.netlist.ValidationError`:
    the netlist may be perfectly valid (well-formed, fully wired, grounded)
    and still be a topology this solver does not (yet) support, e.g. two
    junctions or zero resonators.
    """


@dataclass(frozen=True)
class QubitTopology:
    """The Josephson element (qubit) island located in a netlist.

    Args:
        junction: The sole qubit Josephson element -- either a ``junction``
            (fixed) or a ``squid`` (flux-tunable). Named ``junction`` for
            historical reasons; check ``.type`` to distinguish.
        island_node: The non-ground node the element's island terminal is
            wired to (i.e. the qubit's charge island).
        ground_node: The ground node the element's other terminal is wired to.
        capacitor_ids: Ids of every ``capacitor`` element with a terminal on
            ``island_node`` (shunt AND coupling capacitors alike -- any
            capacitance seen at the junction node contributes to Ec).
    """

    junction: Element
    island_node: str
    ground_node: str
    capacitor_ids: tuple[str, ...]

    @property
    def is_tunable(self) -> bool:
        """True if the qubit element is a flux-tunable ``squid``."""
        return self.junction.type == "squid"


@dataclass(frozen=True)
class ResonatorTopology:
    """The lumped LC resonator located in a netlist.

    Args:
        resonator: The sole ``resonator`` element.
        active_node: The non-ground node the resonator's "hot" terminal is
            wired to.
        ground_node: The ground node the resonator's other terminal is wired to.
    """

    resonator: Element
    active_node: str
    ground_node: str


@dataclass(frozen=True)
class CouplingTopology:
    """The capacitor(s) directly bridging the qubit island to the resonator.

    Args:
        capacitor_ids: Ids of every ``capacitor`` element wired directly
            between the qubit island node and the resonator's active node.
            Empty if the qubit and resonator are not directly capacitively
            coupled (in which case g = 0).
    """

    capacitor_ids: tuple[str, ...]


@dataclass(frozen=True)
class TwoQubitTopology:
    """Two Josephson qubits and their capacitive coupling, found in a netlist.

    Args:
        qubit_elements: The two ``junction``/``squid`` elements (order matches
            the other per-qubit tuples).
        island_nodes: Each qubit's charge-island node.
        ground_node: The shared 0 V reference.
        shunt_capacitor_ids: Per qubit, the ids of capacitors wired island<->
            ground (contribute to that qubit's island-to-ground capacitance).
        coupling_capacitor_ids: Ids of capacitors wired directly between the two
            islands (the qubit-qubit coupling).
    """

    qubit_elements: tuple[Element, Element]
    island_nodes: tuple[str, str]
    ground_node: str
    shunt_capacitor_ids: tuple[tuple[str, ...], tuple[str, ...]]
    coupling_capacitor_ids: tuple[str, ...]


def _elements_of_type(netlist: Netlist, element_type: str) -> list[Element]:
    return [el for el in netlist.elements if el.type == element_type]


def _josephson_elements(netlist: Netlist) -> list[Element]:
    """All qubit Josephson elements (junctions and squids), in netlist order."""
    return [el for el in netlist.elements if el.type in ("junction", "squid")]


def extract_two_qubit_topology(netlist: Netlist) -> TwoQubitTopology:
    """Locate two capacitively-coupled qubits and their coupling capacitor(s).

    Args:
        netlist: A validated :class:`~core.netlist.Netlist` with exactly two
            Josephson elements (junction/squid), each wired between the shared
            ground and its own island, and at least one capacitor bridging the
            two islands.

    Returns:
        The :class:`TwoQubitTopology`.

    Raises:
        TopologyError: if there are not exactly two Josephson elements, if an
            element is not wired ground<->island, or if the two islands are the
            same node.
    """
    qubits = _josephson_elements(netlist)
    if len(qubits) != 2:
        raise TopologyError(
            f"two-qubit topology needs exactly 2 Josephson elements, found "
            f"{len(qubits)} ({[q.id for q in qubits]})"
        )
    ground_node = _single_ground_node(netlist)

    islands: list[str] = []
    for q in qubits:
        p_node, n_node = netlist.nodes_of(q.id)
        if not p_node or not n_node:
            raise TopologyError(f"{q.type} {q.id!r} has an unbound terminal")
        non_ground = {p_node, n_node} - {ground_node}
        if len(non_ground) != 1:
            raise TopologyError(
                f"{q.type} {q.id!r} is wired {p_node!r}<->{n_node!r}; expected one "
                f"terminal on ground {ground_node!r} and one on its island"
            )
        islands.append(next(iter(non_ground)))

    if islands[0] == islands[1]:
        raise TopologyError(
            f"both qubits share island node {islands[0]!r}; they must be distinct"
        )

    island_set = {islands[0], islands[1]}
    coupling_ids: list[str] = []
    shunt_ids: tuple[list[str], list[str]] = ([], [])
    for cap in _elements_of_type(netlist, "capacitor"):
        nodes = set(netlist.nodes_of(cap.id))
        if nodes == island_set:
            coupling_ids.append(cap.id)
        else:
            for i, island in enumerate(islands):
                if nodes == {island, ground_node}:
                    shunt_ids[i].append(cap.id)

    if not coupling_ids:
        raise TopologyError(
            "no capacitor bridges the two qubit islands; the qubits are "
            "uncoupled (nothing to solve as a coupled pair)"
        )

    return TwoQubitTopology(
        qubit_elements=(qubits[0], qubits[1]),
        island_nodes=(islands[0], islands[1]),
        ground_node=ground_node,
        shunt_capacitor_ids=(tuple(shunt_ids[0]), tuple(shunt_ids[1])),
        coupling_capacitor_ids=tuple(coupling_ids),
    )


def _single_ground_node(netlist: Netlist) -> str:
    """Return the netlist's ground node, requiring exactly one distinct one.

    MVP circuits have a single 0 V reference; if a netlist declares several
    distinct ground nodes we cannot pick one without guessing, so we raise.
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


def extract_qubit_topology(netlist: Netlist) -> QubitTopology:
    """Locate the single transmon junction and its island node.

    Args:
        netlist: A validated :class:`~core.netlist.Netlist`.

    Returns:
        The :class:`QubitTopology` describing the junction's island node and
        every capacitor with a terminal on that node.

    Raises:
        TopologyError: if there is not exactly one Josephson element
            (``junction`` or ``squid``) total, if its terminals are not wired
            to exactly one ground node and one non-ground node, or if there is
            no unambiguous 0V reference.
    """
    # The qubit's Josephson element is either a fixed junction or a flux-tunable
    # squid; exactly one across both types (multi-qubit is out of MVP scope).
    junctions = _elements_of_type(netlist, "junction") + _elements_of_type(
        netlist, "squid"
    )
    if len(junctions) == 0:
        raise TopologyError(
            "netlist has no 'junction' or 'squid' element; nothing to quantize"
        )
    if len(junctions) > 1:
        raise TopologyError(
            f"netlist has {len(junctions)} Josephson elements "
            f"({[j.id for j in junctions]}); multi-qubit circuits are out of MVP scope"
        )
    junction = junctions[0]
    ground_node = _single_ground_node(netlist)

    p_node, n_node = netlist.nodes_of(junction.id)
    if not p_node or not n_node:
        raise TopologyError(f"junction {junction.id!r} has an unbound terminal")

    non_ground = {p_node, n_node} - {ground_node}
    if len(non_ground) != 1:
        raise TopologyError(
            f"junction {junction.id!r} is wired {p_node!r}<->{n_node!r}; expected exactly "
            f"one terminal on ground node {ground_node!r} and one on the qubit island"
        )
    island_node = next(iter(non_ground))

    capacitor_ids = tuple(
        c.element
        for c in netlist.terminals_on_node(island_node)
        if (el := netlist.element_by_id(c.element)) is not None
        and el.type == "capacitor"
    )
    return QubitTopology(
        junction=junction,
        island_node=island_node,
        ground_node=ground_node,
        capacitor_ids=capacitor_ids,
    )


def extract_resonator_topology(netlist: Netlist) -> ResonatorTopology:
    """Locate the single lumped LC resonator and its active node.

    Args:
        netlist: A validated :class:`~core.netlist.Netlist`.

    Returns:
        The :class:`ResonatorTopology` describing the resonator's active node.

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
    return ResonatorTopology(
        resonator=resonator, active_node=active_node, ground_node=ground_node
    )


def extract_coupling_topology(
    netlist: Netlist, qubit: QubitTopology, resonator: ResonatorTopology
) -> CouplingTopology:
    """Find the capacitor(s) wired directly between the qubit island and resonator.

    Args:
        netlist: A validated :class:`~core.netlist.Netlist`.
        qubit: Result of :func:`extract_qubit_topology`.
        resonator: Result of :func:`extract_resonator_topology`.

    Returns:
        The :class:`CouplingTopology`; ``capacitor_ids`` is empty if the qubit
        island and resonator are not directly capacitively coupled.
    """
    coupling_ids = []
    for cap in _elements_of_type(netlist, "capacitor"):
        nodes = set(netlist.nodes_of(cap.id))
        if nodes == {qubit.island_node, resonator.active_node}:
            coupling_ids.append(cap.id)
    return CouplingTopology(capacitor_ids=tuple(coupling_ids))
