# JJQubit Studio

An interactive circuit simulator for superconducting-qubit designers, for
Windows. Drag Josephson junctions, capacitors, and readout resonators onto a
schematic canvas, wire them up, hit **Run**, and see both classical (RCSJ,
time-domain) and quantum (Hamiltonian, spectrum) results in a waveform viewer.

Think PSIM / SPICE for superconducting qubits, not a 3D field solver (COMSOL).

## The pipeline

Everything in JJQubit Studio flows one way, through a frozen netlist contract:

```
Schematic canvas  -->  netlist (JSON)  -->  solver core(s)  -->  HDF5 result  -->  waveform viewer
     [GUI]               [CONTRACT]           [core/]                              [GUI]
```

- **Schematic canvas (GUI).** You place and wire circuit elements. The canvas
  produces a netlist and reads results; it does no physics of its own.
- **Netlist (JSON).** The single source of truth: elements (with unit-carrying
  parameters), nodes, and terminal-to-node connections. This is the *contract*
  both sides code against. See [Netlist Schema](schema.md).
- **Solver core (`core/`).** The classical (RCSJ / I-V / S21) and quantum
  (Ej/Ec, spectrum, dispersive shift, coherence) solvers. They consume a
  netlist and never import any GUI code, so they run headlessly from the
  command line or the scripting API. See [Solvers](solvers.md).
- **HDF5 result.** Each solver writes a self-describing HDF5 file with a
  `/provenance` group (solver + library versions, Python, timestamp, netlist
  hash). See [Architecture](architecture.md).
- **Waveform viewer (GUI).** Reads the HDF5 and plots energy-level diagrams,
  the dispersive shift, RCSJ phase / I-V, and the readout S21 curve.

## What you can do

- Build a transmon + readout-resonator circuit on the canvas, run it, and read
  E01, anharmonicity, the dispersive shift chi, and T1/T2 estimates.
- Drive the same solver core from Python for parameter sweeps and batch runs,
  with no GUI. See [Scripting API](scripting.md).
- Solve two capacitively-coupled transmons for the avoided crossing, exchange
  coupling J, static ZZ, and the iSWAP gate time. See [Multi-qubit](multi-qubit.md).

## Project status

The MVP vertical slice is complete, and multi-qubit support has been added:

- **Faz 0/1 (MVP) — done.** Netlist schema, quantum solver, classical solver,
  schematic canvas, and waveform viewer. App shell: main window, menu/toolbar,
  `.jjq` save/load, and worker-thread (subprocess) solver orchestration are
  done and tested. Engineering baseline: reproducible venv, ruff + mypy,
  pre-commit hooks, and CI on Python 3.11 and 3.13.
- **Faz 2 — multi-qubit.** Two capacitively-coupled transmons: the coupled
  spectrum, exchange coupling J, static ZZ, and iSWAP gate time, via
  `jjqubit.solve_two_qubit` and `core.solvers.quantum.multiqubit`.

The authoritative task breakdown and acceptance criteria live in the project's
`docs/task.md`; the full test suite (including the `tests/validation`
analytic-limit checks) passes end to end.

## Scope (deliberately out)

By design, JJQubit Studio does **not** include a 3D Maxwell / FEM field solver,
a mesh generator, a GDS layout editor, or pulse-shaping / gate-fidelity
optimization. The capacitance matrix is an *input* to this tool (entered by
hand or loaded from CSV), not something it computes from geometry.
