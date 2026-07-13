# Netlist Schema

The netlist is the **contract** at the center of JJQubit Studio: the schematic
canvas produces it, and the classical and quantum solvers consume it. Both
sides code against the field names and Python API defined here.

The authoritative, full specification (in Turkish) lives in the project's
`docs/netlist_schema.md`. This page is a short English orientation and pointer;
for the complete rules, units table, and validation error modes, read that
document.

## Top-level structure

A netlist is UTF-8 JSON with these top-level fields:

| Field         | Type          | Meaning                                            |
|---------------|---------------|----------------------------------------------------|
| `format`      | string        | Always `"jjqubit-netlist"`.                        |
| `version`     | string        | Schema version. Current: `"1.0"`.                  |
| `name`        | string        | Human-readable circuit name.                       |
| `nodes`       | string[]      | Declared electrical node ids.                      |
| `elements`    | Element[]     | Circuit elements (see below).                      |
| `connections` | Connection[]  | Terminal-to-node bindings.                         |

The topology model follows SPICE: two terminals wired to the same node are
electrically the same point. There is no separate "wire" object; all wiring is
in the `connections` list, where each connection binds one **terminal** of an
element (a 0-based index into that element type's terminal list) to exactly one
node.

Every numeric parameter carries an **explicit unit** (a `Quantity`, e.g.
`{ "value": 7.2, "unit": "GHz" }`). Unit confusion is the most common error
source in this domain, so units are first-class. A parameter's unit must be of
the expected *dimension* for that parameter (giving `Ic`, a current, a unit of
`GHz` is a validation error). Micro is written with the ASCII prefix `u`
(`uA`, `um`, `us`); dimensionless quantities use the empty unit `""`.

## Element types

Each element type has a fixed, named set of terminals; the `terminal` index in
a connection is a 0-based index into that list. The units below are the
typical/suggested ones; the schema accepts any unit of the same dimension.

| Type                | Terminals      | Parameters                                             |
|---------------------|----------------|--------------------------------------------------------|
| `junction`          | `[p, n]`       | `Ic` (current), `Cj` (capacitance), `Rn` (resistance)  |
| `squid`             | `[p, n]`       | `Ic_max`, `Cj`, `Rn`; optional `d`, `flux` (dimensionless) |
| `capacitor`         | `[a, b]`       | `C` (capacitance)                                      |
| `inductor`          | `[a, b]`       | `L` (inductance)                                       |
| `resistor`          | `[a, b]`       | `R` (resistance)                                       |
| `resonator`         | `[a, b]`       | `f0` (frequency), `Q` (dimensionless)                  |
| `transmission_line` | `[in, out]`    | `Z0` (resistance/ohm), `length`, `eps_eff` (dimensionless) |
| `current_source`    | `[pos, neg]`   | `I` (current)                                          |
| `ground`            | `[gnd]`        | none (the node it connects to is the 0 V reference)    |

Notes:

- **`squid`** models a flux-tunable two-junction SQUID as a single two-terminal
  element. Its effective Josephson energy is tuned by external flux:
  `Ej(f) = Ic_max-derived EjMax * sqrt(cos^2(pi*f) + d^2*sin^2(pi*f))`,
  `f = Phi/Phi0`. It maps directly to scqubits' `TunableTransmon`.
- **`resistor`** is used for matched-load / port termination (for example
  terminating a feed line at 50 ohm) and for lossy elements.
- **`transmission_line`** treats the common return as ground; phase velocity is
  `v = c / sqrt(eps_eff)`.

## Validation

`validate(netlist)` checks the netlist and raises `ValidationError` (whose
`.errors` lists every problem, collected in one pass) on any issue. Checked
failure modes include: duplicate element / node ids, unknown element type,
missing required or unexpected parameter, a parameter unit of the wrong
dimension, connections referencing a nonexistent element or undeclared node,
out-of-range terminal index, a terminal that is unconnected or connected more
than once, no `ground` element, a floating node (fewer than two terminals), and
a node not electrically connected to ground.

## Python API

Import root: `core.netlist` (pure data, stdlib only, no GUI import).

```python
from core.netlist import (
    Netlist, Element, Connection, Quantity,      # data model
    ElementType, ParamSpec, ELEMENT_TYPES,       # type registry
    load, loads, dump, dumps, to_dict, from_dict,# JSON I/O
    validate, collect_errors,                    # validation
    NetlistError, SchemaError, UnitError, ValidationError,  # exceptions
)

nl = load("examples/transmon_readout.json", validate=True)
nl.nodes_of("J1")          # -> nodes the junction's terminals connect to
nl.terminals_on_node("q")  # -> connections on node "q"
```

`Quantity.to_si()` converts a value to the SI base unit of its dimension
(`Quantity(2, "fF").to_si()` -> `2e-15` F), so solvers do not do unit
arithmetic by hand. The round-trip `from_dict(to_dict(nl)) == nl` and
`loads(dumps(nl)) == nl` is lossless.

## Example netlists

`examples/` ships netlists that pass their own validation and together cover all
nine element types:

- `examples/transmon_readout.json` — a transmon (junction + shunt capacitor)
  coupled through a capacitor to a readout resonator, read out over a
  transmission line terminated in a 50 ohm `resistor`.
- `examples/rcsj_bias.json` — a current-driven RCSJ junction, for the classical
  I-V.
- `examples/tunable_transmon.json` — the same circuit as `transmon_readout` but
  with a flux-tunable `squid` in place of the fixed junction.
- `examples/two_transmon.json` — two capacitively-coupled transmons, for the
  multi-qubit avoided crossing / J.
