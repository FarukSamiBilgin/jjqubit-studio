# JJQubit Studio

An interactive circuit simulator for superconducting-qubit designers, for
Windows. Drag Josephson junctions, capacitors, and readout resonators onto a
schematic canvas, wire them up, hit **Run**, and see both classical (RCSJ,
time-domain) and quantum (Hamiltonian, spectrum) results in a waveform
viewer.

Think PSIM/SPICE for superconducting qubits (schematic → netlist → solver →
waveform), not a 3D field solver (COMSOL). See `CLAUDE.md` for the full
project context and scope decisions (in Turkish).

## Requirements

- Windows 10/11
- Python 3.11+

## Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running from source

```powershell
python -m gui.app
```

This opens the main window: an element library + schematic canvas on the
left, and a results panel on the right.

### First run

1. **File → New Project** (or just start — a new window opens with an empty
   project already).
2. Drag a `junction`, `capacitor`, and `resonator` from the library panel
   onto the canvas.
3. Wire their terminals together and to a `ground` element (click a terminal
   handle, then click a node or empty canvas to drop a new node there).
   Use the **Validate** button in the canvas toolbar to check for floating
   nodes or missing parameters before running.
4. Select each element and set its parameters (Ic, Cj, Rn for the junction;
   C for the capacitor; f0, Q for the resonator) in the property panel on the
   right.
5. Pick a solver in the toolbar (**quantum** is available today; **classical**
   is wired up the same way once it lands) and click **Run** (or press F5).
   A progress bar tracks the run; the GUI stays responsive throughout.
6. On success, the result's HDF5 path is shown in the results panel. (The
   full waveform viewer — energy-level diagrams, S21 curves — is a separate,
   in-progress module; see "Project status" below.)
7. **File → Save Project** writes a `.jjq` file (netlist + run metadata) you
   can reopen later with **File → Open Project**.

An example transmon + readout-resonator circuit ships in `examples/` — open
it directly via the schematic canvas's own **Load Netlist…** button (note:
that loads a plain netlist JSON, not a `.jjq` project file) to see a working
circuit without building one from scratch.

## Project files (`.jjq`)

A `.jjq` file is UTF-8 JSON with two parts:

- `netlist`: the circuit, in the frozen `core.netlist` schema (elements,
  nodes, wiring, units) — the same format the solvers consume directly from
  the command line.
- `app_version` / `last_run`: metadata about the app version that saved the
  file and the most recent solver run (which solver, status, output path,
  timestamp).

A project with validation errors can still be saved (you'll be warned first)
so work in progress is never lost; solvers, however, only ever run against a
validated netlist.

## Running the solvers headlessly

Every solver is a standalone CLI over a netlist file — no GUI required:

```powershell
python -m core.solvers.quantum examples\transmon_readout.json out_quantum.h5
```

## Tests

```powershell
pytest
```

Each teammate's module has its own test directory (`tests/netlist`,
`tests/schematic`, `tests/solvers_quantum`, `tests/app`, ...) plus
`tests/validation`, which checks solver results against known analytic
physics limits — passing unit tests alone don't establish a numeric result
is *correct*, see `CLAUDE.md`.

## Building a Windows `.exe`

```powershell
python scripts\build_exe.py --clean
```

Produces a one-folder build under `dist\JJQubitStudio\`. Add `--onefile` for
a single `.exe` (slower to start, easier to hand someone); add `--console`
to keep the console window open while debugging a broken build. The script
bundles `examples\` alongside the executable and adds `--collect-all` hints
for `scqubits`/`qutip` and hidden-import hints for `h5py`, since PyInstaller's
static analysis tends to miss their dynamically-loaded submodules.

## Architecture

```
Schematic canvas  -->  netlist (JSON)  -->  solver core(s)  -->  HDF5 result  -->  waveform viewer
     [GUI]               [CONTRACT]           [core/]                              [GUI]
```

`core/` never imports PySide6 and can be driven entirely from the command
line; `gui/` does no physics of its own. `gui/app.py` (this module) is the
integrator: it owns the main window, `.jjq` project I/O, and the
worker-thread orchestration that runs a solver without freezing the UI.

Solver runs execute in a **subprocess**, not in-process on the worker
thread: calling `scqubits`'s sparse eigensolver directly from a `QThread`
was found to crash the app with a Windows access violation (native
BLAS/LAPACK code is not safe to invoke from an arbitrary secondary thread in
the GUI process). Shelling out to `python -m core.solvers.<name>` isolates
that native numerics from the GUI process entirely, so a solver crash can
only take down the subprocess.

## Project status

This app is built by several teammates against the netlist contract in
parallel; see `docs/task.md` for the full task breakdown and acceptance
criteria. As of this module's last update:

- Netlist schema, quantum solver, and schematic canvas: done.
- Classical solver and waveform viewer: in progress.
- App shell (this module): main window, menu/toolbar, `.jjq` save/load, and
  worker-thread solver orchestration are done and tested; the results panel
  is a placeholder until the waveform viewer is embeddable, and only the
  "quantum" solver is wired into the Run menu until the classical solver
  reports done.
