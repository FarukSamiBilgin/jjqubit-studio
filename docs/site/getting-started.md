# Getting Started

JJQubit Studio targets Windows 10/11 and Python 3.11+. It is developed and
tested against the pinned versions in `requirements.txt` on Python 3.11 and
3.13; CI runs the full suite on both.

## Install

From the repository root, create a virtual environment and install the pinned
runtime dependencies:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For development (linting, type checking, and the pre-commit hooks CI enforces),
also install the dev tooling into the same environment:

```powershell
pip install -r requirements-dev.txt
pre-commit install
```

## Run the app

```powershell
python -m gui.app
```

This opens the main window: an element library plus schematic canvas on the
left, and a results panel on the right.

A first run, end to end:

1. **File -> New Project** (or just start; an empty project opens).
2. Drag a `junction`, `capacitor`, and `resonator` from the library onto the
   canvas.
3. Wire their terminals together and to a `ground` element (click a terminal
   handle, then click a node or empty canvas to drop a new node). Use the
   **Validate** button in the canvas toolbar to catch floating nodes or missing
   parameters before running.
4. Select each element and set its parameters (Ic, Cj, Rn for the junction; C
   for the capacitor; f0, Q for the resonator) in the property panel.
5. Pick a solver in the toolbar (**quantum** and **classical** are both
   available) and click **Run** (or press F5). A progress bar tracks the run;
   the GUI stays responsive.
6. On success the result renders in the embedded waveform viewer: energy-level
   diagrams and the dispersive shift for quantum runs; the RCSJ phase / I-V
   (plus the readout S21 curve when the circuit has a resonator) for classical
   runs.
7. **File -> Save Project** writes a `.jjq` file (netlist + run metadata) you
   can reopen later.

An example transmon + readout-resonator circuit ships in `examples/`; open it
via the canvas's **Load Netlist...** button (that loads a plain netlist JSON,
not a `.jjq` project file).

## Run the solvers headlessly

Every solver is a standalone CLI over a netlist file. No GUI required:

```powershell
python -m core.solvers.quantum examples\transmon_readout.json out_quantum.h5
python -m core.solvers.classical examples\rcsj_bias.json out_classical.h5
```

The quantum solver auto-detects a two-qubit netlist (two Josephson elements)
and runs the coupled two-transmon solver instead:

```powershell
python -m core.solvers.quantum examples\two_transmon.json out_2q.h5
```

The HDF5 output is exactly what the waveform viewer reads. For a scripted,
in-process alternative that returns live result objects, see the
[Scripting API](scripting.md).

## Run the tests

```powershell
pytest
```

Each teammate's module has its own test directory (`tests/netlist`,
`tests/schematic`, `tests/solvers_quantum`, `tests/app`, ...) plus
`tests/validation`, which checks solver results against known analytic physics
limits. Passing unit tests alone do not establish that a numeric result is
*correct*; the validation suite is what does that.

## Build a Windows `.exe`

```powershell
python scripts\build_exe.py --clean
```

This produces a one-folder build under `dist\JJQubitStudio\`. Add `--onefile`
for a single `.exe`, or `--console` to keep a console window open while
debugging a broken build.
