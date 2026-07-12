"""Read solver-produced HDF5 result files into plain dataclasses.

This module does no physics -- it only opens the HDF5 files the solvers
write and reshapes their contents into dataclasses the view widgets can
plot. See ``core/solvers/quantum/hdf5_io.py`` for the authoritative,
frozen quantum-result layout this reader is built against (Task #3, done).

The classical-solver (Task #2) result layout is NOT finalized yet -- it is
being built in parallel. :func:`load_classical_result` below is written
against a PROVISIONAL schema we invented ourselves purely so the S21 view
has something real to render and test against today (see
``tests/waveform/classical_synthetic.py`` for the fixture that builds a
file matching it). Once ``main`` relays the real layout from
solver-classical, only ``_CLASSICAL_FORMAT_PROVISIONAL`` and
:func:`load_classical_result` need to change -- the view widgets consume
:class:`ClassicalResult`, not the file directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import h5py
import numpy as np

# Matches core.solvers.quantum.hdf5_io.FORMAT -- the frozen quantum-result
# format string. Hardcoded (rather than imported from core.solvers.quantum)
# to keep gui/waveform decoupled from core internals; it is a stable,
# documented data contract, not an implementation detail.
QUANTUM_FORMAT = "jjqubit-quantum-result"

# PROVISIONAL -- our own placeholder for the not-yet-finalized classical
# solver output, used only until main relays the real layout.
CLASSICAL_FORMAT_PROVISIONAL = "jjqubit-classical-result-provisional"

ResultKind = Literal["quantum", "classical", "unknown"]


def detect_result_kind(path: str | Path) -> ResultKind:
    """Inspect an HDF5 file's root attrs/groups and classify its contents.

    Uses the root ``format`` attribute first, and falls back to structural
    checks (presence of the ``/qubit`` or ``/s21`` groups) so a classical
    file written under a different ``format`` string than our provisional
    guess is still recognized once solver-classical lands.
    """
    with h5py.File(path, "r") as f:
        fmt = f.attrs.get("format")
        if fmt == QUANTUM_FORMAT:
            return "quantum"
        if fmt == CLASSICAL_FORMAT_PROVISIONAL:
            return "classical"
        if "qubit" in f:
            return "quantum"
        if "s21" in f:
            return "classical"
    return "unknown"


@dataclass(frozen=True)
class QuantumResult:
    """Everything the energy-level view needs from a quantum-solver HDF5 file.

    All energies in GHz, capacitances in fF, currents in nA -- matching the
    units already baked into the file (see ``core/solvers/quantum/hdf5_io.py``).
    """

    netlist_name: str

    # /qubit
    energy_levels_GHz: np.ndarray
    Ej_GHz: float
    Ec_GHz: float
    Ej_over_Ec: float
    E01_GHz: float
    anharmonicity_GHz: float
    Ic_nA: float
    C_sigma_fF: float
    junction_id: str
    island_node: str
    n01: float

    # /resonator
    f0_GHz: float
    Q: float
    kappa_GHz: float
    resonator_id: str
    active_node: str

    # /coupling
    g_GHz: float
    g_GHz_description: str
    chi_GHz: float
    Delta_GHz: float
    beta: float
    Cg_fF: float

    # /assumptions
    resonator_Z0_ohm: float
    assumptions_note: str


def load_quantum_result(path: str | Path) -> QuantumResult:
    """Load a quantum-solver HDF5 file (see module docstring) into a :class:`QuantumResult`.

    Args:
        path: Path to a file written by ``core.solvers.quantum.hdf5_io.write_hdf5``.

    Raises:
        ValueError: if the file's root ``format`` attr is not the expected
            quantum-result format.
        OSError: if the file cannot be opened (propagated from h5py).
    """
    with h5py.File(path, "r") as f:
        fmt = f.attrs.get("format")
        if fmt != QUANTUM_FORMAT:
            raise ValueError(
                f"{path!r}: expected format {QUANTUM_FORMAT!r}, got {fmt!r}"
            )
        qubit = f["qubit"]
        resonator = f["resonator"]
        coupling = f["coupling"]
        assumptions = f["assumptions"]
        return QuantumResult(
            netlist_name=str(f.attrs["netlist_name"]),
            energy_levels_GHz=np.asarray(qubit["energy_levels"][:]),
            Ej_GHz=float(qubit.attrs["Ej_GHz"]),
            Ec_GHz=float(qubit.attrs["Ec_GHz"]),
            Ej_over_Ec=float(qubit.attrs["Ej_over_Ec"]),
            E01_GHz=float(qubit.attrs["E01_GHz"]),
            anharmonicity_GHz=float(qubit.attrs["anharmonicity_GHz"]),
            Ic_nA=float(qubit.attrs["Ic_nA"]),
            C_sigma_fF=float(qubit.attrs["C_sigma_fF"]),
            junction_id=str(qubit.attrs["junction_id"]),
            island_node=str(qubit.attrs["island_node"]),
            n01=float(qubit.attrs["n01"]),
            f0_GHz=float(resonator.attrs["f0_GHz"]),
            Q=float(resonator.attrs["Q"]),
            kappa_GHz=float(resonator.attrs["kappa_GHz"]),
            resonator_id=str(resonator.attrs["resonator_id"]),
            active_node=str(resonator.attrs["active_node"]),
            g_GHz=float(coupling.attrs["g_GHz"]),
            g_GHz_description=str(coupling.attrs["g_GHz_description"]),
            chi_GHz=float(coupling.attrs["chi_GHz"]),
            Delta_GHz=float(coupling.attrs["Delta_GHz"]),
            beta=float(coupling.attrs["beta"]),
            Cg_fF=float(coupling.attrs["Cg_fF"]),
            resonator_Z0_ohm=float(assumptions.attrs["resonator_Z0_ohm"]),
            assumptions_note=str(assumptions.attrs["note"]),
        )


@dataclass(frozen=True)
class ClassicalResult:
    """S21 transmission sweep, read from a (currently provisional) classical-solver file.

    Args:
        netlist_name: The netlist this sweep was computed from.
        frequency_GHz: Sweep frequency axis, shape ``(n,)``.
        magnitude_dB: ``|S21|`` in dB, shape ``(n,)``.
        phase_deg: ``arg(S21)`` in degrees, shape ``(n,)``.
    """

    netlist_name: str
    frequency_GHz: np.ndarray
    magnitude_dB: np.ndarray
    phase_deg: np.ndarray


def load_classical_result(path: str | Path) -> ClassicalResult:
    """Load an S21 sweep from a classical-solver HDF5 file.

    PROVISIONAL: reads the placeholder schema documented at the top of this
    module (``/s21/frequency_GHz``, ``/s21/magnitude_dB``, ``/s21/phase_deg``),
    invented for development purposes since solver-classical's real layout
    (Task #2) has not been relayed yet. Replace this function's body (only)
    once ``main`` provides the real layout -- :class:`ClassicalResult` and
    the S21 view are written against the dataclass, not this function, so
    they should not need to change.

    Args:
        path: Path to an HDF5 file with an ``/s21`` group.

    Raises:
        KeyError: if the expected provisional datasets are not present.
        OSError: if the file cannot be opened (propagated from h5py).
    """
    with h5py.File(path, "r") as f:
        s21 = f["s21"]
        return ClassicalResult(
            netlist_name=str(f.attrs.get("netlist_name", "")),
            frequency_GHz=np.asarray(s21["frequency_GHz"][:]),
            magnitude_dB=np.asarray(s21["magnitude_dB"][:]),
            phase_deg=np.asarray(s21["phase_deg"][:]),
        )
