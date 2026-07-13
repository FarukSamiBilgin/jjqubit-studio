"""Quantum solver for JJQubit Studio: circuit quantization + transmon spectrum.

This package turns a frozen :mod:`core.netlist` circuit description into a
quantized transmon-plus-resonator model and computes its spectrum (energy
levels, E01, anharmonicity) and its dispersive coupling to a readout
resonator (g, chi). It is a thin layer on top of ``scqubits`` and ``QuTiP``
-- it does NOT reimplement transmon physics; see ``docs/task.md`` (Gorev 3)
and CLAUDE.md's "Yapmayacaklarimiz" section.

No PySide6 / GUI import anywhere in this package (project-wide rule).

Pipeline
--------
    netlist (JSON) --load--> Netlist
                     --topology.py--> QubitTopology (Ej/Ec/Cg inputs)
                     --spectrum.py--> TransmonSpectrum (via scqubits)
                     --dispersive.py--> DispersiveResult (g, chi via scqubits)
                     --hdf5_io.py--> HDF5 result file

CLI: ``python -m core.solvers.quantum <netlist.json> <output.h5>``
"""

from __future__ import annotations

from .dispersive import DispersiveResult, compute_dispersive_shift, dressed_chi_ghz
from .hdf5_io import write_hdf5
from .quantization import QubitQuantization, quantize_circuit
from .spectrum import TransmonSpectrum, compute_transmon_spectrum
from .topology import (
    CouplingTopology,
    QubitTopology,
    ResonatorTopology,
    TopologyError,
    extract_coupling_topology,
    extract_qubit_topology,
    extract_resonator_topology,
)

__all__ = [
    "QubitTopology",
    "ResonatorTopology",
    "CouplingTopology",
    "TopologyError",
    "extract_qubit_topology",
    "extract_resonator_topology",
    "extract_coupling_topology",
    "QubitQuantization",
    "quantize_circuit",
    "TransmonSpectrum",
    "compute_transmon_spectrum",
    "DispersiveResult",
    "compute_dispersive_shift",
    "dressed_chi_ghz",
    "write_hdf5",
]
