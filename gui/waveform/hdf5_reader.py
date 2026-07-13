"""Read solver-produced HDF5 result files into plain dataclasses.

This module does no physics -- it only opens the HDF5 files the solvers
write and reshapes their contents into dataclasses the view widgets can
plot. Both solver-output layouts are now finalized and this reader is built
against the authoritative docstrings:

* quantum: ``core/solvers/quantum/hdf5_io.py`` (Task #3) -- ``/qubit`` etc.
* classical: ``core/solvers/classical/hdf5_io.py`` (Task #2) -- an optional
  ``/readout`` group (S21 transmission) and/or an optional ``/rcsj`` group
  (I-V curve + phase dynamics); at least one is always present.

The view widgets consume the dataclasses below (:class:`QuantumResult`,
:class:`ClassicalResult`), never the HDF5 file directly, so a future layout
change is absorbed here rather than rippling into the plotting code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import h5py
import numpy as np

# Matches core.solvers.quantum.hdf5_io.FORMAT -- the frozen quantum-result
# format string. Hardcoded (rather than imported from core.solvers.quantum)
# to keep gui/waveform decoupled from core internals; it is a stable,
# documented data contract, not an implementation detail.
QUANTUM_FORMAT = "jjqubit-quantum-result"

# Matches core.solvers.classical.hdf5_io.FORMAT -- the finalized
# classical-result format string.
CLASSICAL_FORMAT = "jjqubit-classical-result"

# Matches core.solvers.quantum.multiqubit.TWO_QUBIT_FORMAT.
TWO_QUBIT_FORMAT = "jjqubit-two-qubit-result"

ResultKind = Literal["quantum", "classical", "two_qubit", "unknown"]

# The major result-format version this reader understands. A file may carry a
# higher MINOR (additive changes, e.g. the /provenance group added in 1.1) and
# still load; a higher MAJOR signals an incompatible layout and is refused so a
# newer file is not silently misread.
SUPPORTED_MAJOR_VERSION = 1


def _check_version(f: h5py.File, path: str | Path) -> None:
    """Refuse files whose MAJOR format version exceeds what this reader supports.

    Missing or unparseable version attrs are treated as compatible (legacy
    pre-versioning files), so this only ever hard-fails on a genuinely newer
    major layout.
    """
    raw = f.attrs.get("version")
    if raw is None:
        return
    try:
        major = int(str(raw).split(".", 1)[0])
    except ValueError:
        return
    if major > SUPPORTED_MAJOR_VERSION:
        raise ValueError(
            f"{path!r}: result format version {str(raw)!r} is newer than this "
            f"viewer supports (major <= {SUPPORTED_MAJOR_VERSION}); update JJQubit Studio."
        )


def read_provenance(path: str | Path) -> dict[str, Any]:
    """Return the ``/provenance`` group's attrs as a dict (empty if absent).

    Works for both quantum and classical result files; see
    ``core/provenance.py`` for the attribute set.
    """
    with h5py.File(path, "r") as f:
        if "provenance" not in f:
            return {}
        group = f["provenance"]
        return {
            k: (v.decode() if isinstance(v, bytes) else v)
            for k, v in group.attrs.items()
        }


def detect_result_kind(path: str | Path) -> ResultKind:
    """Inspect an HDF5 file's root attrs/groups and classify its contents.

    Uses the root ``format`` attribute first, then falls back to structural
    checks (presence of the ``/qubit`` group for quantum, or the ``/rcsj`` /
    ``/readout`` groups for classical) so a file written under an unexpected
    ``format`` string is still recognized from its structure.
    """
    with h5py.File(path, "r") as f:
        fmt = f.attrs.get("format")
        if fmt == QUANTUM_FORMAT:
            return "quantum"
        if fmt == CLASSICAL_FORMAT:
            return "classical"
        if fmt == TWO_QUBIT_FORMAT:
            return "two_qubit"
        # Structural fallbacks when the format attr is missing/unexpected.
        if "coupled" in f and "qubits" in f:
            return "two_qubit"
        if "qubit" in f:
            return "quantum"
        if "rcsj" in f or "readout" in f:
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
    element_type: str
    EjMax_GHz: float
    flux: float
    asymmetry_d: float

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
    g_over_Delta: float
    dispersive_regime_valid: bool

    # /assumptions
    resonator_Z0_ohm: float
    assumptions_note: str

    # /coherence (NaN when the file predates coherence output)
    T1_us: float
    T2_us: float
    Tphi_us: float
    T1_intrinsic_us: float
    T1_purcell_us: float
    temperature_K: float


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
        _check_version(f, path)
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
            # Back-compatible defaults for pre-squid files (a fixed junction).
            element_type=str(qubit.attrs.get("element_type", "junction")),
            EjMax_GHz=float(qubit.attrs.get("EjMax_GHz", qubit.attrs["Ej_GHz"])),
            flux=float(qubit.attrs.get("flux", 0.0)),
            asymmetry_d=float(qubit.attrs.get("asymmetry_d", 0.0)),
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
            # Back-compatible defaults for files written before 1.1's
            # dispersive-validity fields were added.
            g_over_Delta=float(coupling.attrs.get("g_over_Delta", float("nan"))),
            dispersive_regime_valid=bool(
                coupling.attrs.get("dispersive_regime_valid", True)
            ),
            resonator_Z0_ohm=float(assumptions.attrs["resonator_Z0_ohm"]),
            assumptions_note=str(assumptions.attrs["note"]),
            # /coherence is optional (added in format 1.2); NaN if absent.
            T1_us=_coherence_attr(f, "T1_us"),
            T2_us=_coherence_attr(f, "T2_us"),
            Tphi_us=_coherence_attr(f, "Tphi_us"),
            T1_intrinsic_us=_coherence_attr(f, "T1_intrinsic_us"),
            T1_purcell_us=_coherence_attr(f, "T1_purcell_us"),
            temperature_K=_coherence_attr(f, "temperature_K"),
        )


def _coherence_attr(f: h5py.File, name: str) -> float:
    """Read a scalar from the optional /coherence group, or NaN if absent."""
    if "coherence" not in f:
        return float("nan")
    return float(f["coherence"].attrs.get(name, float("nan")))


@dataclass(frozen=True)
class ReadoutS21:
    """The ``/readout`` S21 transmission sweep from a classical-solver file.

    All arrays share shape ``(n,)``. Units match the file (see
    ``core/solvers/classical/hdf5_io.py``): frequency in GHz, magnitude in
    dB, phase in degrees; the real/imaginary parts are dimensionless.

    Args:
        frequency_GHz: Sweep frequency axis.
        magnitude_dB: ``20*log10|S21|``.
        phase_deg: ``arg(S21)`` in degrees.
        s21_real, s21_imag: The complex S21, split into parts.
        f0_GHz: Resonator bare resonance frequency.
        Q_internal: Internal quality factor.
        kappa_total_MHz: Total linewidth (internal + external), in MHz.
        resonator_id, active_node: Netlist provenance.
    """

    frequency_GHz: np.ndarray
    magnitude_dB: np.ndarray
    phase_deg: np.ndarray
    s21_real: np.ndarray
    s21_imag: np.ndarray
    f0_GHz: float
    Q_internal: float
    kappa_total_MHz: float
    resonator_id: str
    active_node: str


@dataclass(frozen=True)
class RcsjIVCurve:
    """The ``/rcsj/iv_curve`` bias sweep (both directions, for hysteresis).

    Currents in nA, voltages in uV. The up/down sweeps trace the ascending
    and descending bias directions; for an underdamped junction they differ
    (retrapping-current hysteresis).
    """

    bias_current_up_nA: np.ndarray
    voltage_up_uV: np.ndarray
    bias_current_down_nA: np.ndarray
    voltage_down_uV: np.ndarray


@dataclass(frozen=True)
class RcsjPhaseDynamics:
    """The ``/rcsj/phase_dynamics`` time trace.

    Time in ns, phase in rad, voltage in uV.

    Args:
        time_ns, phase_rad, voltage_uV: The time-domain traces, shape ``(n,)``.
        dc_voltage_uV: Settled (time-averaged) DC voltage, in uV.
        bias_current_nA: Bias current the trace was computed at, in nA.
    """

    time_ns: np.ndarray
    phase_rad: np.ndarray
    voltage_uV: np.ndarray
    dc_voltage_uV: float
    bias_current_nA: float


@dataclass(frozen=True)
class RcsjData:
    """The ``/rcsj`` group: scalar junction parameters + I-V curve + phase dynamics."""

    iv_curve: RcsjIVCurve
    phase_dynamics: RcsjPhaseDynamics
    Ic_nA: float
    Rn_total_ohm: float
    C_total_fF: float
    bias_current_nA: float
    plasma_frequency_GHz: float
    quality_factor: float
    junction_id: str


@dataclass(frozen=True)
class ClassicalResult:
    """A classical-solver result: an optional S21 readout and/or an optional RCSJ analysis.

    At least one of :attr:`readout` / :attr:`rcsj` is non-``None`` (the
    solver raises upstream for a netlist with neither topology).

    Args:
        netlist_name: The netlist this result was computed from.
        readout: The S21 transmission sweep, or ``None`` if the netlist has
            no resonator+feedline readout topology.
        rcsj: The RCSJ I-V + phase-dynamics analysis, or ``None`` if the
            netlist has no current-biased junction.
    """

    netlist_name: str
    readout: ReadoutS21 | None
    rcsj: RcsjData | None


def _read_readout(group: h5py.Group) -> ReadoutS21:
    return ReadoutS21(
        frequency_GHz=np.asarray(group["frequency_GHz"][:]),
        magnitude_dB=np.asarray(group["s21_mag_db"][:]),
        phase_deg=np.asarray(group["s21_phase_deg"][:]),
        s21_real=np.asarray(group["s21_real"][:]),
        s21_imag=np.asarray(group["s21_imag"][:]),
        f0_GHz=float(group.attrs["f0_GHz"]),
        Q_internal=float(group.attrs["Q_internal"]),
        kappa_total_MHz=float(group.attrs["kappa_total_MHz"]),
        resonator_id=str(group.attrs["resonator_id"]),
        active_node=str(group.attrs["active_node"]),
    )


def _read_rcsj(group: h5py.Group) -> RcsjData:
    iv = group["iv_curve"]
    dyn = group["phase_dynamics"]
    return RcsjData(
        iv_curve=RcsjIVCurve(
            bias_current_up_nA=np.asarray(iv["bias_current_up_nA"][:]),
            voltage_up_uV=np.asarray(iv["voltage_up_uV"][:]),
            bias_current_down_nA=np.asarray(iv["bias_current_down_nA"][:]),
            voltage_down_uV=np.asarray(iv["voltage_down_uV"][:]),
        ),
        phase_dynamics=RcsjPhaseDynamics(
            time_ns=np.asarray(dyn["time_ns"][:]),
            phase_rad=np.asarray(dyn["phase_rad"][:]),
            voltage_uV=np.asarray(dyn["voltage_uV"][:]),
            dc_voltage_uV=float(dyn.attrs["dc_voltage_uV"]),
            bias_current_nA=float(dyn.attrs["bias_current_nA"]),
        ),
        Ic_nA=float(group.attrs["Ic_nA"]),
        Rn_total_ohm=float(group.attrs["Rn_total_ohm"]),
        C_total_fF=float(group.attrs["C_total_fF"]),
        bias_current_nA=float(group.attrs["bias_current_nA"]),
        plasma_frequency_GHz=float(group.attrs["plasma_frequency_GHz"]),
        quality_factor=float(group.attrs["quality_factor"]),
        junction_id=str(group.attrs["junction_id"]),
    )


def load_classical_result(path: str | Path) -> ClassicalResult:
    """Load a classical-solver HDF5 file (see module docstring) into a :class:`ClassicalResult`.

    Reads whichever of the ``/readout`` and ``/rcsj`` groups are present --
    both are optional, but the solver guarantees at least one.

    Args:
        path: Path to a file written by
            ``core.solvers.classical.hdf5_io.write_hdf5``.

    Raises:
        ValueError: if neither the ``/readout`` nor the ``/rcsj`` group is
            present (not a classical result this viewer can render).
        OSError: if the file cannot be opened (propagated from h5py).
    """
    with h5py.File(path, "r") as f:
        _check_version(f, path)
        readout = _read_readout(f["readout"]) if "readout" in f else None
        rcsj = _read_rcsj(f["rcsj"]) if "rcsj" in f else None
        if readout is None and rcsj is None:
            raise ValueError(
                f"{path!r}: classical result has neither a /readout nor a /rcsj group"
            )
        return ClassicalResult(
            netlist_name=str(f.attrs.get("netlist_name", "")),
            readout=readout,
            rcsj=rcsj,
        )


@dataclass(frozen=True)
class TwoQubitResult:
    """Everything needed from a two-qubit-solver HDF5 file. Energies in GHz."""

    netlist_name: str

    # /qubits
    Ej1_GHz: float
    Ec1_GHz: float
    Ej2_GHz: float
    Ec2_GHz: float
    g_GHz: float
    Cc_fF: float

    # /coupled
    omega1_GHz: float
    omega2_GHz: float
    detuning_GHz: float
    J_GHz: float
    one_excitation_splitting_GHz: float
    zz_MHz: float
    anharmonicity1_MHz: float
    anharmonicity2_MHz: float
    iswap_gate_time_ns: float
    coupled_levels_GHz: np.ndarray


def load_two_qubit_result(path: str | Path) -> TwoQubitResult:
    """Load a two-qubit-solver HDF5 file into a :class:`TwoQubitResult`.

    Raises:
        ValueError: if the file is not a two-qubit result.
        OSError: if the file cannot be opened.
    """
    with h5py.File(path, "r") as f:
        fmt = f.attrs.get("format")
        if fmt != TWO_QUBIT_FORMAT:
            raise ValueError(
                f"{path!r}: expected format {TWO_QUBIT_FORMAT!r}, got {fmt!r}"
            )
        _check_version(f, path)
        qubits = f["qubits"]
        coupled = f["coupled"]
        return TwoQubitResult(
            netlist_name=str(f.attrs.get("netlist_name", "")),
            Ej1_GHz=float(qubits.attrs["Ej1_GHz"]),
            Ec1_GHz=float(qubits.attrs["Ec1_GHz"]),
            Ej2_GHz=float(qubits.attrs["Ej2_GHz"]),
            Ec2_GHz=float(qubits.attrs["Ec2_GHz"]),
            g_GHz=float(qubits.attrs["g_GHz"]),
            Cc_fF=float(qubits.attrs["Cc_fF"]),
            omega1_GHz=float(coupled.attrs["omega1_GHz"]),
            omega2_GHz=float(coupled.attrs["omega2_GHz"]),
            detuning_GHz=float(coupled.attrs["detuning_GHz"]),
            J_GHz=float(coupled.attrs["J_GHz"]),
            one_excitation_splitting_GHz=float(
                coupled.attrs["one_excitation_splitting_GHz"]
            ),
            zz_MHz=float(coupled.attrs["zz_MHz"]),
            anharmonicity1_MHz=float(coupled.attrs["anharmonicity1_MHz"]),
            anharmonicity2_MHz=float(coupled.attrs["anharmonicity2_MHz"]),
            iswap_gate_time_ns=float(coupled.attrs["iswap_gate_time_ns"]),
            coupled_levels_GHz=np.asarray(coupled["coupled_levels_GHz"][:]),
        )
