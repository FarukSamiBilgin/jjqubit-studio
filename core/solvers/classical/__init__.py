"""Classical solver for JJQubit Studio: RCSJ time-domain dynamics + readout S21.

This package turns a frozen :mod:`core.netlist` circuit description into:

* Resistively-and-capacitively-shunted-junction (RCSJ) time-domain phase
  dynamics for a current-biased junction (:mod:`rcsj`).
* A hysteretic I-V curve (current sweep) for the same junction.
* A readout S21 transmission curve for a resonator capacitively coupled to a
  terminated transmission-line feedline (:mod:`s21`).

It does NOT reimplement general circuit simulation -- only the specific MVP
topologies docs/task.md (Gorev 2) calls for; see
``core/solvers/classical/topology.py`` for exactly what shapes of netlist are
supported.

No PySide6 / GUI import anywhere in this package (project-wide rule).

Pipeline
--------
    netlist (JSON) --load--> Netlist
                     --topology.py--> RCSJTopology / ReadoutTopology
                     --runner.py--> RCSJAnalysis / ReadoutAnalysis
                       (rcsj.py / s21.py do the actual physics)
                     --hdf5_io.py--> HDF5 result file

CLI: ``python -m core.solvers.classical <netlist.json> <output.h5>``
"""
from __future__ import annotations

from .hdf5_io import write_hdf5
from .rcsj import (
    IVCurveResult,
    PhaseDynamicsResult,
    dc_voltage,
    integrate_phase_dynamics,
    plasma_frequency_rad_s,
    sweep_iv_curve,
)
from .runner import ReadoutAnalysis, RCSJAnalysis, run_rcsj_analysis, run_readout_analysis
from .s21 import S21Curve, compute_s21_curve
from .topology import (
    RCSJTopology,
    ReadoutTopology,
    TopologyError,
    extract_rcsj_topology,
    extract_readout_topology,
)

__all__ = [
    "TopologyError",
    "RCSJTopology",
    "ReadoutTopology",
    "extract_rcsj_topology",
    "extract_readout_topology",
    "PhaseDynamicsResult",
    "IVCurveResult",
    "plasma_frequency_rad_s",
    "integrate_phase_dynamics",
    "dc_voltage",
    "sweep_iv_curve",
    "S21Curve",
    "compute_s21_curve",
    "RCSJAnalysis",
    "ReadoutAnalysis",
    "run_rcsj_analysis",
    "run_readout_analysis",
    "write_hdf5",
]
