"""JJQubit Studio -- scriptable Python API.

This is the GUI-free entry point for driving the solver core from a script or
notebook, so parameter sweeps and batch runs don't need the schematic editor::

    import jjqubit

    net = jjqubit.load_netlist("examples/transmon_readout.json")
    q = jjqubit.solve_quantum(net)
    print(q.E01_GHz, q.anharmonicity_GHz, q.chi_MHz)

    c = jjqubit.solve_classical(net)
    print(c.rcsj.phase_dynamics.dc_voltage_v)

    # Same HDF5 the GUI's waveform viewer reads:
    q.write_hdf5("out_quantum.h5")

It is a thin, faithful layer over ``core.solvers.*``: it reuses the exact same
quantization/spectrum/dispersive and RCSJ/readout code paths the CLIs and GUI
use (CLAUDE.md "Yapmayacaklarimiz" #2 -- no physics is reimplemented here), and
never imports PySide6, so it is safe to use headless.

Heavy scientific imports (scqubits/qutip) are deferred into the solve
functions, so ``import jjqubit`` itself stays cheap.
"""

from __future__ import annotations

from .api import (
    ClassicalSolution,
    QuantumSolution,
    TwoQubitSolution,
    load_netlist,
    solve_classical,
    solve_quantum,
    solve_two_qubit,
)

# Mirrors gui.app.APP_VERSION; kept here too so the headless API carries a
# version without importing the GUI. Unify into a single source later.
__version__ = "0.1.0"

__all__ = [
    "ClassicalSolution",
    "QuantumSolution",
    "TwoQubitSolution",
    "load_netlist",
    "solve_classical",
    "solve_quantum",
    "solve_two_qubit",
    "__version__",
]
