"""Semantic validation of a :class:`~core.netlist.model.Netlist`.

:func:`validate` collects EVERY problem it can find (it does not stop at the
first) and raises a single :class:`ValidationError` whose ``.errors`` list names
each offending element, node or parameter. This makes it useful both as a hard
gate before solving and as the data source for GUI error highlighting.

Checked failure modes
----------------------
1. Duplicate element id.
2. Duplicate node id.
3. Unknown element type.
4. Missing required parameter on an element.
5. Unknown (unexpected) parameter on an element.
6. Parameter unit has the wrong physical dimension (e.g. ``Ic`` given in GHz).
7. Connection references a non-existent element.
8. Connection references an undeclared node.
9. Terminal index out of range for the element type.
10. Element terminal left unbound, or bound more than once.
11. No ``ground`` element present (no 0 V reference).
12. Floating node: fewer than two terminals attached.
13. Node not electrically connected to any ground node.
"""

from __future__ import annotations

from collections import Counter

from .errors import ValidationError
from .model import ELEMENT_TYPES, Netlist


def validate(netlist: Netlist) -> None:
    """Validate ``netlist``; raise :class:`ValidationError` if anything is wrong.

    Args:
        netlist: The netlist to check.

    Raises:
        ValidationError: if one or more problems are found. The exception's
            ``.errors`` attribute holds one message per problem.
    """
    errors: list[str] = collect_errors(netlist)
    if errors:
        raise ValidationError(errors)


def collect_errors(netlist: Netlist) -> list[str]:
    """Return the list of validation problems in ``netlist`` (empty if valid).

    Unlike :func:`validate`, this never raises; it is convenient for GUIs that
    want to display all issues without exception handling.
    """
    errors: list[str] = []

    # -- 1. duplicate element ids -----------------------------------------
    id_counts = Counter(el.id for el in netlist.elements)
    for el_id, count in id_counts.items():
        if count > 1:
            errors.append(f"duplicate element id {el_id!r} ({count} elements)")

    # -- 2. duplicate node ids --------------------------------------------
    node_counts = Counter(netlist.nodes)
    for node_id, count in node_counts.items():
        if count > 1:
            errors.append(f"duplicate node id {node_id!r} ({count} declarations)")
    declared_nodes = set(netlist.nodes)

    # -- 3..6. per-element type and parameter checks ----------------------
    for el in netlist.elements:
        etype = ELEMENT_TYPES.get(el.type)
        if etype is None:
            known = ", ".join(sorted(ELEMENT_TYPES))
            errors.append(
                f"element {el.id!r}: unknown element type {el.type!r} "
                f"(known types: {known})"
            )
            continue

        # 4. missing required parameters
        for spec in etype.params:
            if spec.required and spec.name not in el.params:
                errors.append(
                    f"element {el.id!r} ({el.type}): missing required "
                    f"parameter {spec.name!r} ({spec.dimension})"
                )

        # 5. unexpected parameters + 6. wrong dimension
        for pname, q in el.params.items():
            # Distinct name from the `spec` loop variable above (which is a
            # non-optional ParamSpec); `param()` returns ParamSpec | None.
            param_spec = etype.param(pname)
            if param_spec is None:
                allowed = ", ".join(p.name for p in etype.params) or "(none)"
                errors.append(
                    f"element {el.id!r} ({el.type}): unknown parameter "
                    f"{pname!r} (allowed: {allowed})"
                )
                continue
            if q.dimension != param_spec.dimension:
                errors.append(
                    f"element {el.id!r} ({el.type}): parameter {pname!r} has "
                    f"unit {q.unit!r} of dimension {q.dimension!r}, "
                    f"expected {param_spec.dimension!r}"
                )

    element_ids = {el.id for el in netlist.elements}
    element_types = {el.id: el.type for el in netlist.elements}

    # -- 7..9. connection integrity ---------------------------------------
    # terminal index -> how many bindings, per element
    bindings: dict[str, Counter] = {el.id: Counter() for el in netlist.elements}
    for c in netlist.connections:
        # 7. element must exist
        if c.element not in element_ids:
            errors.append(
                f"connection references unknown element {c.element!r} "
                f"(terminal {c.terminal}, node {c.node!r})"
            )
            continue
        # 8. node must be declared
        if c.node not in declared_nodes:
            errors.append(
                f"connection on element {c.element!r} references undeclared "
                f"node {c.node!r}"
            )
        # 9. terminal index in range
        etype = ELEMENT_TYPES.get(element_types[c.element])
        if etype is not None:
            if c.terminal < 0 or c.terminal >= etype.n_terminals:
                errors.append(
                    f"element {c.element!r} ({etype.name}): terminal index "
                    f"{c.terminal} out of range [0, {etype.n_terminals - 1}]"
                )
            else:
                bindings[c.element][c.terminal] += 1

    # -- 10. every terminal bound exactly once ----------------------------
    for el in netlist.elements:
        etype = ELEMENT_TYPES.get(el.type)
        if etype is None:
            continue
        counts = bindings[el.id]
        for idx in range(etype.n_terminals):
            tname = etype.terminals[idx]
            n = counts.get(idx, 0)
            if n == 0:
                errors.append(
                    f"element {el.id!r} ({el.type}): terminal {idx} "
                    f"({tname!r}) is not connected"
                )
            elif n > 1:
                errors.append(
                    f"element {el.id!r} ({el.type}): terminal {idx} "
                    f"({tname!r}) is connected {n} times (expected once)"
                )

    # -- 11. a ground element must exist ----------------------------------
    ground_node_list = netlist.ground_nodes()
    if not any(el.type == "ground" for el in netlist.elements):
        errors.append(
            "no ground element present: the circuit has no 0 V reference "
            "(add a 'ground' element)"
        )

    # -- 12. floating nodes (fewer than two terminals attached) -----------
    degree: Counter = Counter(
        c.node for c in netlist.connections if c.node in declared_nodes
    )
    for node in netlist.nodes:
        d = degree.get(node, 0)
        if d < 2:
            errors.append(
                f"floating node {node!r}: connected to {d} terminal(s), "
                f"needs at least 2"
            )

    # -- 13. every node must reach a ground node --------------------------
    ground_set = set(ground_node_list) & declared_nodes
    if ground_set:
        reachable = _nodes_reachable_from(netlist, ground_set)
        for node in netlist.nodes:
            # Only report genuinely isolated nodes that are at least wired up;
            # fully floating nodes are already reported by check 12.
            if node not in reachable and degree.get(node, 0) >= 2:
                errors.append(f"node {node!r} is not electrically connected to ground")

    return errors


def _nodes_reachable_from(netlist: Netlist, seeds: set[str]) -> set[str]:
    """Return all nodes reachable from ``seeds`` through element terminals.

    Two nodes are adjacent if some element has terminals bound to both of them
    (an element is treated as linking all of its own nodes). This is topological
    reachability, ignoring whether a component passes DC.
    """
    # Build adjacency: for each element, connect all the nodes it touches.
    adjacency: dict[str, set[str]] = {n: set() for n in netlist.nodes}
    for el in netlist.elements:
        el_nodes = [
            c.node for c in netlist.connections_of(el.id) if c.node in adjacency
        ]
        for i, a in enumerate(el_nodes):
            for b in el_nodes[i + 1 :]:
                adjacency[a].add(b)
                adjacency[b].add(a)

    reachable: set[str] = set()
    stack = [s for s in seeds if s in adjacency]
    while stack:
        node = stack.pop()
        if node in reachable:
            continue
        reachable.add(node)
        stack.extend(adjacency[node] - reachable)
    return reachable
