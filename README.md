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

For development (linting, type checking, and the pre-commit hooks that CI
enforces), also install the dev tooling into the same environment:

```powershell
pip install -r requirements-dev.txt
pre-commit install
```

The app is developed and tested against the pinned versions in
`requirements.txt` on Python 3.11 and 3.13; CI runs the full suite on both.

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
5. Pick a solver in the toolbar (**quantum** and **classical** are both
   available) and click **Run** (or press F5). A progress bar tracks the run;
   the GUI stays responsive throughout.
6. On success, the result is rendered in the embedded waveform viewer:
   energy-level diagrams and the dispersive shift for quantum runs, and the
   RCSJ phase/I-V (plus the readout S21 curve when the circuit has a
   resonator) for classical runs.
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

The quantum solver auto-detects a two-qubit netlist (two Josephson elements)
and runs the coupled two-transmon solver instead:

```powershell
python -m core.solvers.quantum examples\two_transmon.json out_2q.h5
```

## Scripting (the `jjqubit` API)

For notebooks and batch/parameter sweeps there is a GUI-free Python API that
wraps the same solver core (it never imports PySide6):

```python
import jjqubit

net = jjqubit.load_netlist("examples/transmon_readout.json")

q = jjqubit.solve_quantum(net)
print(q.Ej_over_Ec, q.E01_GHz, q.anharmonicity_GHz, q.chi_MHz)
print(q.T1_us, q.T2_us)            # scqubits-based coherence estimates
q.write_hdf5("out_quantum.h5")     # same HDF5 the waveform viewer reads

c = jjqubit.solve_classical(net)
print(c.rcsj.phase_dynamics.dc_voltage_v)
```

Worked examples: sweep the junction critical current and tabulate
E01 / anharmonicity / χ versus Ej/Ec, or tune a flux-tunable **squid**
transmon across an external-flux arc:

```powershell
python examples\sweep_transmon.py
python examples\sweep_flux.py       # flux-tunable (squid) transmon
python examples\sweep_coupling.py   # two coupled qubits: the avoided crossing
```

Two capacitively-coupled qubits are solved with `jjqubit.solve_two_qubit`,
which reports the bare frequencies, the single-excitation splitting, and the
exchange coupling J (minimal 2J at resonance — the avoided crossing).

## Physics validation

Passing unit tests does not establish that a numerical result is correct, so
`tests/validation/` checks every solver against independent references:

| Test file | Reference |
| --- | --- |
| `test_transmon_limit.py` | Transmon limit (E_J/E_C >> 1): anharmonicity approaches -E_C |
| `test_cpb_limit.py` | E_J/E_C -> 0: Cooper-pair-box behaviour vs. a from-scratch charge-basis reference |
| `test_dispersive_chi.py` | Dispersive shift chi converges to the analytic expression (correct multi-level form) |
| `test_rcsj.py` | RCSJ zero-voltage branch for I < I_c, via an independent from-scratch ODE integrator |
| `test_solver_classical.py`, `test_solver_quantum.py` | Live comparison of both solver pipelines against the independent references in `reference.py` |
| `test_tunable_transmon.py` | Flux-tunable (SQUID) transmon, asymmetric E_J(flux) |
| `test_two_transmon.py` | Avoided crossing of two coupled transmons, splitting = 2 sqrt((Delta/2)^2 + J^2) |
| `test_literature.py` | Analytic expressions and scaling laws of Koch et al., PRA 76, 042319 (2007) |
| `test_coherence.py` | Physical sanity of T1/T2 estimates (e.g. T2 <= 2 T1) |
| `test_units.py` | Netlist unit registry and dimensional correctness of derived energies |

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
criteria. The MVP vertical slice is complete:

- Netlist schema, quantum solver, classical solver, schematic canvas, and
  waveform viewer: done.
- App shell: main window, menu/toolbar, `.jjq` save/load, and worker-thread
  (subprocess) solver orchestration are done and tested. Both the quantum and
  classical solvers are wired into the Run menu, and results render in the
  embedded waveform viewer.
- Engineering baseline: reproducible venv from `requirements.txt`, ruff lint +
  format and mypy configured (`pyproject.toml`), pre-commit hooks, and CI
  (`.github/workflows/ci.yml`) running the full suite on Python 3.11 and 3.13.

The full test suite (362 tests, including the `tests/validation` analytic-limit
checks) passes end to end.

## AI assistance

AI assistance: AI coding assistants were used for code development and for adversarial review. All load-bearing results were re-derived by independent methods and checked by automated tests; the author is responsible for every claim.

The "teammates" mentioned above and in `CLAUDE.md` / `docs/task.md` (Turkish
project brief and task breakdown) are AI coding agents, each owning one
module, coordinated by the author.

## Citation

See `CITATION.cff`. Author: Faruk Sami Bilgin (ORCID
[0009-0001-9064-4410](https://orcid.org/0009-0001-9064-4410)).

## License

MIT, see `LICENSE`.
