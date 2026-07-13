"""Two capacitively-coupled transmons: coupled spectrum and exchange coupling.

The first multi-qubit capability (Faz 2). Composes two ``scqubits.Transmon``
objects into a joint Hilbert space with a charge-charge interaction
``H_int = g * n1 * n2`` and diagonalizes it (the same ``scqubits.HilbertSpace``
machinery the dispersive solver already uses -- no new dependency, no physics
reimplemented, per CLAUDE.md).

From the joint spectrum we read the hallmark of qubit-qubit coupling: the
single-excitation manifold {|10>, |01>} forms an avoided crossing as the two
qubits are tuned through resonance. The one-excitation eigenvalues are

    E_pm = (w1 + w2)/2 +/- sqrt( (Delta/2)^2 + J^2 ),   Delta = w1 - w2,

so their splitting is ``2*sqrt((Delta/2)^2 + J^2)`` -- minimal (= 2J) exactly on
resonance. We invert this to report the exchange coupling J.

This module is intentionally parameterized by the charge-coupling coefficient
``g`` directly, NOT by a coupling capacitance: mapping a netlist coupling
capacitor to ``g`` (a capacitance-matrix inversion) is a separate, separately
validated step. That keeps the composition/diagonalization physics here
testable against the analytic avoided crossing on its own.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import scqubits as scq
from core.netlist import Netlist
from core.provenance import write_provenance
from scipy.constants import e as _ELEMENTARY_CHARGE
from scipy.constants import h as _PLANCK_H

from .quantization import element_josephson_params
from .topology import TwoQubitTopology, extract_two_qubit_topology

# Charge-basis truncation and per-transmon level truncation for the joint space.
_NCUT = 30
_LEVELS_EACH = 4

# HDF5 result format for two-qubit runs (distinct from the single-qubit format).
TWO_QUBIT_FORMAT = "jjqubit-two-qubit-result"
TWO_QUBIT_FORMAT_VERSION = "1.0"
_PROVENANCE_LIBS = ("numpy", "scipy", "h5py", "scqubits", "qutip")


@dataclass(frozen=True)
class TwoTransmonResult:
    """Coupled spectrum of two capacitively-coupled transmons, energies in GHz.

    Args:
        omega1_GHz, omega2_GHz: The two BARE (uncoupled) qubit 0<->1 frequencies.
        detuning_GHz: ``omega1 - omega2``.
        J_GHz: Exchange coupling extracted from the single-excitation avoided
            crossing (see module docstring). Always >= 0.
        one_excitation_splitting_GHz: Energy gap between the two lowest excited
            (single-excitation) joint levels; minimal (= 2J) on resonance.
        g_GHz: The input charge-charge coupling coefficient of ``n1 * n2``.
        zz_MHz: Static ZZ interaction ``E11 - E10 - E01 + E00``, in MHz -- the
            always-on frequency shift of one qubit conditioned on the other,
            the dominant coherent error in fixed-coupling multi-qubit chips.
            ``NaN`` at exact resonance, where the bare |10>/|01> product states
            are fully hybridized and cannot be individually labeled.
        anharmonicity1_MHz, anharmonicity2_MHz: Per-qubit anharmonicities
            ``(E12 - E01)``, in MHz (negative for a transmon; sets the CZ gate).
        iswap_gate_time_ns: Time for a full resonant iSWAP, ``1/(4J)`` in ns
            (``inf`` when the qubits are uncoupled). The population swaps between
            |10> and |01> at frequency 2J; a full swap takes 1/(4J).
        coupled_levels_GHz: The low-lying joint eigenenergies relative to the
            joint ground state.
    """

    omega1_GHz: float
    omega2_GHz: float
    detuning_GHz: float
    J_GHz: float
    one_excitation_splitting_GHz: float
    g_GHz: float
    zz_MHz: float
    anharmonicity1_MHz: float
    anharmonicity2_MHz: float
    iswap_gate_time_ns: float
    coupled_levels_GHz: np.ndarray


@dataclass(frozen=True)
class TwoQubitQuantization:
    """Ej/Ec of two coupled qubits and their charge coupling, from a netlist.

    Args:
        Ej1_GHz, Ec1_GHz, Ej2_GHz, Ec2_GHz: Per-qubit Josephson/charging
            energies, in GHz. Ec is the diagonal of the Maxwell charging-energy
            matrix, so it already accounts for the coupling capacitor's small
            renormalization of each island.
        g_GHz: Coefficient of the charge-charge coupling ``g * n1 * n2``, in GHz,
            derived from the off-diagonal charging energy (capacitance-matrix
            inversion).
        Cc_fF: Total island<->island coupling capacitance, in fF.
        topology: The raw :class:`TwoQubitTopology` this was derived from, or
            ``None`` when the quantization came from an external capacitance
            matrix (no netlist topology).
    """

    Ej1_GHz: float
    Ec1_GHz: float
    Ej2_GHz: float
    Ec2_GHz: float
    g_GHz: float
    Cc_fF: float
    topology: TwoQubitTopology | None = None


def _island_shunt_capacitance_si(
    netlist: Netlist, element, shunt_cap_ids: tuple[str, ...]
) -> float:
    """Island-to-ground capacitance: the element's Cj plus its shunt capacitors."""
    total = element.params["Cj"].to_si()
    for cid in shunt_cap_ids:
        cap = netlist.element_by_id(cid)
        assert cap is not None
        total += cap.params["C"].to_si()
    return total


def quantize_two_qubit_circuit(netlist: Netlist) -> TwoQubitQuantization:
    """Extract Ej/Ec per qubit and the charge coupling g from a 2-qubit netlist.

    The two islands and coupling capacitor form the Maxwell capacitance matrix
    ``[[C1+Cc, -Cc], [-Cc, C2+Cc]]`` (C1, C2 the island-to-ground capacitances).
    Its inverse gives the charging-energy matrix: ``Ec_i = e^2 (C^-1)_ii / 2``
    on the diagonal and the coupling ``g = 4 e^2 (C^-1)_12`` off-diagonal
    (coefficient of ``n1 n2``). This is a capacitance-matrix INVERSION of netlist
    inputs, not a geometry solve (CLAUDE.md "Yapmayacaklarimiz" #1).

    Raises:
        core.solvers.quantum.topology.TopologyError: if the netlist is not a
            valid two-qubit coupled topology.
    """
    topo = extract_two_qubit_topology(netlist)
    q1, q2 = topo.qubit_elements

    jp1 = element_josephson_params(q1)
    jp2 = element_josephson_params(q2)

    c1 = _island_shunt_capacitance_si(netlist, q1, topo.shunt_capacitor_ids[0])
    c2 = _island_shunt_capacitance_si(netlist, q2, topo.shunt_capacitor_ids[1])
    cc = 0.0
    for cid in topo.coupling_capacitor_ids:
        cap = netlist.element_by_id(cid)
        assert cap is not None
        cc += cap.params["C"].to_si()

    ec1, ec2, g = _charging_energies_from_matrix_si(
        np.array([[c1 + cc, -cc], [-cc, c2 + cc]])
    )

    return TwoQubitQuantization(
        Ej1_GHz=jp1.Ej_GHz,
        Ec1_GHz=ec1,
        Ej2_GHz=jp2.Ej_GHz,
        Ec2_GHz=ec2,
        g_GHz=g,
        Cc_fF=cc * 1e15,
        topology=topo,
    )


def _charging_energies_from_matrix_si(
    c_matrix_si: np.ndarray,
) -> tuple[float, float, float]:
    """Invert a 2x2 Maxwell capacitance matrix (Farad) into Ec1, Ec2, g (GHz).

    ``Ec_i = e^2 (C^-1)_ii / 2`` on the diagonal; the charge-charge coupling
    coefficient of ``n1 n2`` is ``g = 4 e^2 (C^-1)_12`` off-diagonal. Shared by
    the netlist and external-capacitance-matrix quantization paths.
    """
    c_inv = np.linalg.inv(c_matrix_si)
    ec1 = _ELEMENTARY_CHARGE**2 * c_inv[0, 0] / 2.0 / _PLANCK_H / 1e9
    ec2 = _ELEMENTARY_CHARGE**2 * c_inv[1, 1] / 2.0 / _PLANCK_H / 1e9
    g = 4.0 * _ELEMENTARY_CHARGE**2 * c_inv[0, 1] / _PLANCK_H / 1e9
    return float(ec1), float(ec2), float(g)


def quantize_two_qubit_from_capacitance(
    matrix_fF: np.ndarray,
    *,
    Ej1_GHz: float,
    Ej2_GHz: float,
) -> TwoQubitQuantization:
    """Quantize two qubits from an EXTERNAL 2x2 Maxwell capacitance matrix.

    Realizes the CLAUDE.md design rule that the capacitance matrix is an INPUT
    (e.g. an Ansys Q3D export loaded via :mod:`core.interop.capacitance_csv`),
    not something this program computes from geometry. The two Josephson
    energies (from the junction critical currents) are supplied separately.

    Args:
        matrix_fF: The 2x2 Maxwell capacitance matrix for the two qubit islands,
            in fF (symmetric; diagonal = island total capacitance, off-diagonal
            = negative mutual capacitance -- the standard short-circuit
            capacitance-matrix convention).
        Ej1_GHz, Ej2_GHz: Josephson energies of the two qubits, in GHz.

    Returns:
        A :class:`TwoQubitQuantization` (``topology`` is ``None``; ``Cc_fF`` is
        the mutual capacitance ``-matrix[0,1]``).

    Raises:
        ValueError: if the matrix is not 2x2 or not (numerically) symmetric.
    """
    m = np.asarray(matrix_fF, dtype=float)
    if m.shape != (2, 2):
        raise ValueError(
            f"expected a 2x2 capacitance matrix for two qubits, got shape {m.shape}; "
            "reduce/eliminate non-qubit nodes upstream first"
        )
    if not np.allclose(m, m.T, rtol=1e-6, atol=1e-9):
        raise ValueError("capacitance matrix must be symmetric")

    ec1, ec2, g = _charging_energies_from_matrix_si(m * 1e-15)  # fF -> Farad
    cc_fF = float(-m[0, 1])
    return TwoQubitQuantization(
        Ej1_GHz=Ej1_GHz,
        Ec1_GHz=ec1,
        Ej2_GHz=Ej2_GHz,
        Ec2_GHz=ec2,
        g_GHz=g,
        Cc_fF=cc_fF,
        topology=None,
    )


def solve_two_qubit_from_capacitance(
    matrix_fF: np.ndarray,
    *,
    Ej1_GHz: float,
    Ej2_GHz: float,
    evals_count: int = 6,
) -> TwoTransmonResult:
    """Solve two qubits from an external capacitance matrix + the two Ej values.

    Chains :func:`quantize_two_qubit_from_capacitance` and
    :func:`compute_two_transmon_spectrum` -- the capacitance-matrix-as-input
    path (e.g. an Ansys export via :mod:`core.interop`).
    """
    q = quantize_two_qubit_from_capacitance(matrix_fF, Ej1_GHz=Ej1_GHz, Ej2_GHz=Ej2_GHz)
    return compute_two_transmon_spectrum(
        q.Ej1_GHz, q.Ec1_GHz, q.Ej2_GHz, q.Ec2_GHz, q.g_GHz, evals_count=evals_count
    )


def solve_two_qubit_netlist(netlist: Netlist, *, evals_count: int = 6):
    """Quantize a 2-qubit netlist and return its coupled spectrum.

    Convenience that chains :func:`quantize_two_qubit_circuit` and
    :func:`compute_two_transmon_spectrum`.
    """
    q = quantize_two_qubit_circuit(netlist)
    return compute_two_transmon_spectrum(
        q.Ej1_GHz,
        q.Ec1_GHz,
        q.Ej2_GHz,
        q.Ec2_GHz,
        q.g_GHz,
        evals_count=evals_count,
    )


def _transmon(Ej_GHz: float, Ec_GHz: float) -> scq.Transmon:
    return scq.Transmon(
        EJ=Ej_GHz, EC=Ec_GHz, ng=0.0, ncut=_NCUT, truncated_dim=_LEVELS_EACH
    )


def compute_two_transmon_spectrum(
    Ej1_GHz: float,
    Ec1_GHz: float,
    Ej2_GHz: float,
    Ec2_GHz: float,
    g_GHz: float,
    *,
    evals_count: int = 6,
) -> TwoTransmonResult:
    """Diagonalize two charge-coupled transmons and extract J.

    Args:
        Ej1_GHz, Ec1_GHz: Josephson and charging energy of qubit 1, in GHz.
        Ej2_GHz, Ec2_GHz: Josephson and charging energy of qubit 2, in GHz.
        g_GHz: Coefficient of the charge-charge coupling ``g * n1 * n2``, in GHz.
        evals_count: Number of joint eigenvalues to return.

    Returns:
        The :class:`TwoTransmonResult`.

    Raises:
        ValueError: if any energy is non-positive or ``evals_count`` < 3
            (need the ground and both single-excitation levels).
    """
    if min(Ej1_GHz, Ec1_GHz, Ej2_GHz, Ec2_GHz) <= 0.0:
        raise ValueError("Ej/Ec must be positive")
    if evals_count < 3:
        raise ValueError("evals_count must be >= 3 to see the coupled qubit levels")

    t1 = _transmon(Ej1_GHz, Ec1_GHz)
    t2 = _transmon(Ej2_GHz, Ec2_GHz)
    omega1 = float(t1.E01())
    omega2 = float(t2.E01())

    hilbert_space = scq.HilbertSpace([t1, t2])  # type: ignore[abstract]
    # n1, n2 are Hermitian, so n1 (x) n2 is Hermitian: add_hc=False (no double count).
    hilbert_space.add_interaction(
        g=g_GHz,
        op1=t1.n_operator,
        op2=t2.n_operator,
        add_hc=False,
    )

    evals = hilbert_space.eigenvals(evals_count=evals_count)
    levels = np.asarray(evals) - evals[0]  # relative to the joint ground state

    # The two lowest excited joint states are the single-excitation manifold.
    splitting = float(levels[2] - levels[1])

    # Invert E_pm splitting = 2 sqrt((Delta/2)^2 + J^2) for J.
    detuning = omega1 - omega2
    j_squared = (splitting / 2.0) ** 2 - (detuning / 2.0) ** 2
    j_ghz = math.sqrt(j_squared) if j_squared > 0.0 else 0.0

    zz_mhz = _static_zz_mhz(hilbert_space)
    anh1_mhz = _anharmonicity_mhz(t1)
    anh2_mhz = _anharmonicity_mhz(t2)
    iswap_ns = 1.0 / (4.0 * j_ghz) if j_ghz > 0.0 else math.inf

    return TwoTransmonResult(
        omega1_GHz=omega1,
        omega2_GHz=omega2,
        detuning_GHz=detuning,
        J_GHz=j_ghz,
        one_excitation_splitting_GHz=splitting,
        g_GHz=g_GHz,
        zz_MHz=zz_mhz,
        anharmonicity1_MHz=anh1_mhz,
        anharmonicity2_MHz=anh2_mhz,
        iswap_gate_time_ns=iswap_ns,
        coupled_levels_GHz=levels,
    )


def _anharmonicity_mhz(transmon: scq.Transmon) -> float:
    """Single-transmon anharmonicity (E12 - E01), in MHz."""
    ev = transmon.eigenvals(evals_count=3)
    return float((ev[2] - ev[1]) - (ev[1] - ev[0])) * 1e3


def _static_zz_mhz(hilbert_space: scq.HilbertSpace) -> float:
    """Static ZZ shift E11 - E10 - E01 + E00, in MHz (NaN if not resolvable).

    Uses the dressed-state lookup to identify the joint levels adiabatically
    connected to the bare products |00>,|10>,|01>,|11>. At exact resonance the
    single-excitation states are fully hybridized and the lookup cannot assign
    |10> vs |01> (returns NaN), so ZZ is reported as NaN there.
    """
    hilbert_space.generate_lookup()

    def energy(i: int, j: int) -> float:
        e = hilbert_space.energy_by_bare_index((i, j))
        return float(e) if e is not None else math.nan

    e00 = energy(0, 0)
    e10 = energy(1, 0)
    e01 = energy(0, 1)
    e11 = energy(1, 1)
    zz_ghz = e11 - e10 - e01 + e00
    return zz_ghz * 1e3  # GHz -> MHz


def write_two_qubit_hdf5(
    path: str | Path,
    *,
    netlist_name: str,
    quantization: TwoQubitQuantization,
    result: TwoTransmonResult,
    netlist_hash: str | None = None,
) -> None:
    """Write a two-qubit result to HDF5.

    Layout::

        / (root)   attrs: format, version, generated_by, netlist_name
        /provenance                  (see core/provenance.py)
        /qubits    attrs: Ej1_GHz, Ec1_GHz, Ej2_GHz, Ec2_GHz, g_GHz, Cc_fF
        /coupled   attrs: omega1_GHz, omega2_GHz, detuning_GHz, J_GHz,
                          one_excitation_splitting_GHz, zz_MHz
                   dataset: coupled_levels_GHz (float64[n], unit="GHz")

    Args:
        path: Output file path (parent directory created if needed).
        netlist_name: The source netlist's name.
        quantization: Result of :func:`quantize_two_qubit_circuit`.
        result: Result of :func:`compute_two_transmon_spectrum` /
            :func:`solve_two_qubit_netlist`.
        netlist_hash: Optional SHA-256 of the source netlist for provenance.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        f.attrs["format"] = TWO_QUBIT_FORMAT
        f.attrs["version"] = TWO_QUBIT_FORMAT_VERSION
        f.attrs["generated_by"] = "core.solvers.quantum.multiqubit"
        f.attrs["netlist_name"] = netlist_name

        write_provenance(
            f,
            generated_by="core.solvers.quantum.multiqubit",
            netlist_hash=netlist_hash,
            libraries=_PROVENANCE_LIBS,
        )

        qubits = f.create_group("qubits")
        qubits.attrs["Ej1_GHz"] = quantization.Ej1_GHz
        qubits.attrs["Ec1_GHz"] = quantization.Ec1_GHz
        qubits.attrs["Ej2_GHz"] = quantization.Ej2_GHz
        qubits.attrs["Ec2_GHz"] = quantization.Ec2_GHz
        qubits.attrs["g_GHz"] = quantization.g_GHz
        qubits.attrs["Cc_fF"] = quantization.Cc_fF

        coupled = f.create_group("coupled")
        coupled.attrs["omega1_GHz"] = result.omega1_GHz
        coupled.attrs["omega2_GHz"] = result.omega2_GHz
        coupled.attrs["detuning_GHz"] = result.detuning_GHz
        coupled.attrs["J_GHz"] = result.J_GHz
        coupled.attrs["one_excitation_splitting_GHz"] = (
            result.one_excitation_splitting_GHz
        )
        coupled.attrs["zz_MHz"] = result.zz_MHz
        coupled.attrs["anharmonicity1_MHz"] = result.anharmonicity1_MHz
        coupled.attrs["anharmonicity2_MHz"] = result.anharmonicity2_MHz
        coupled.attrs["iswap_gate_time_ns"] = result.iswap_gate_time_ns
        levels = coupled.create_dataset(
            "coupled_levels_GHz", data=np.asarray(result.coupled_levels_GHz)
        )
        levels.attrs["unit"] = "GHz"
