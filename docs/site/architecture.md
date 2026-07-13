# Architecture

JJQubit Studio's central design rule is that the **GUI and the solver core are
separate, and they communicate only through the netlist**. Everything else
follows from that contract.

```
Schematic canvas  -->  netlist (JSON)  -->  solver core(s)  -->  HDF5 result  -->  waveform viewer
     [GUI]               [CONTRACT]           [core/]                              [GUI]
```

## The netlist contract

The netlist (JSON) is the single source of truth and the boundary between the
two halves of the program:

- The **core (`core/`)** can be run and tested with only a netlist file — no
  GUI. Importing PySide6 anywhere under `core/` is forbidden.
- The **GUI (`gui/`)** does no physics. It only produces a netlist and reads
  results.

This separation is enforced, and one of the project's acceptance criteria is
that PySide6 is never imported anywhere in `core/`. In practice it means the
scripting API (`jjqubit`) and the solver CLIs run headless, and the schematic
canvas and waveform viewer never do numerics.

See [Netlist Schema](schema.md) for the contract itself.

## File ownership

Each area of the codebase is owned by one teammate, to avoid write conflicts:

```
core/netlist/            netlist schema, data model, validation
core/solvers/classical/  RCSJ, ODE, I-V, S-parameters
core/solvers/quantum/    quantization, Hamiltonian, spectrum, multi-qubit
gui/schematic/           schematic canvas, element library, wiring
gui/waveform/            waveform viewer
gui/app.py               main window (only the gui owner touches it)
tests/                   each module's own tests
tests/validation/        analytic-limit / physics validation
```

## Subprocess solver orchestration

`gui/app.py` is the integrator: it owns the main window, `.jjq` project I/O, and
the worker-thread orchestration that runs a solver without freezing the UI.

Solver runs execute in a **subprocess**, not in-process on a worker thread.
Calling scqubits' sparse eigensolver directly from a `QThread` was found to
crash the app with a Windows access violation (native BLAS/LAPACK code is not
safe to invoke from an arbitrary secondary thread in the GUI process). Shelling
out to `python -m core.solvers.<name>` isolates that native numerics from the
GUI process entirely, so a solver crash can only take down the subprocess.

## Result files and provenance

Each solver writes a self-describing HDF5 result. Beyond the physics datasets,
every result carries a `/provenance` group (`core/provenance.py`) recording how
it was produced, so a file is reproducible on its own:

- `provenance_version` — the provenance-group schema version (currently `1.0`).
- `generated_by` — the dotted module path of the producing solver.
- `created_at_utc`, `python_version`, `platform` — when and where it ran.
- `lib_<name>` — the installed versions of the scientific libraries used
  (numpy, scipy, h5py, scqubits, qutip).
- `netlist_sha256` — a stable SHA-256 of the source netlist's canonical JSON, so
  a result can be tied to exactly the netlist that produced it. The hash is
  computed over `core.netlist.to_dict` with sorted keys, so any two netlists
  that serialize identically hash identically.

Both the single-qubit and two-qubit writers emit an identical `/provenance`
group, and `read_provenance` returns an empty dict for files that predate
provenance, so it stays forward-compatible.

## Project files (`.jjq`)

A `.jjq` project file is UTF-8 JSON with two parts:

- `netlist` — the circuit in the frozen `core.netlist` schema (the same format
  the solvers consume directly).
- `app_version` / `last_run` — metadata about the app version that saved the
  file and the most recent solver run (which solver, status, output path,
  timestamp).

A project with validation errors can still be saved (you are warned first) so
work in progress is never lost; solvers, however, only ever run against a
validated netlist.

## Versioning

Several versions travel with the system so results and files stay
self-describing: the netlist schema `version` (`"1.0"`), the provenance-group
`provenance_version` (`"1.0"`), the per-solver HDF5 result `format` /
`version` (for example the two-qubit format `jjqubit-two-qubit-result` `"1.0"`),
and the application / API version (`jjqubit.__version__`, mirrored from the
app). Recorded library versions in each result's provenance pin the exact
scientific stack a number came from.
