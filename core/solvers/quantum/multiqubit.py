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

import numpy as np
import scqubits as scq
from core.netlist import Netlist
from scipy.constants import e as _ELEMENTARY_CHARGE
from scipy.constants import h as _PLANCK_H

from .quantization import element_josephson_params
from .topology import TwoQubitTopology, extract_two_qubit_topology

# Charge-basis truncation and per-transmon level truncation for the joint space.
_NCUT = 30
_LEVELS_EACH = 4


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
        coupled_levels_GHz: The low-lying joint eigenenergies relative to the
            joint ground state.
    """

    omega1_GHz: float
    omega2_GHz: float
    detuning_GHz: float
    J_GHz: float
    one_excitation_splitting_GHz: float
    g_GHz: float
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
        topology: The raw :class:`TwoQubitTopology` this was derived from.
    """

    Ej1_GHz: float
    Ec1_GHz: float
    Ej2_GHz: float
    Ec2_GHz: float
    g_GHz: float
    Cc_fF: float
    topology: TwoQubitTopology


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

    c_matrix = np.array([[c1 + cc, -cc], [-cc, c2 + cc]])
    c_inv = np.linalg.inv(c_matrix)
    ec1 = _ELEMENTARY_CHARGE**2 * c_inv[0, 0] / 2.0 / _PLANCK_H / 1e9
    ec2 = _ELEMENTARY_CHARGE**2 * c_inv[1, 1] / 2.0 / _PLANCK_H / 1e9
    g = 4.0 * _ELEMENTARY_CHARGE**2 * c_inv[0, 1] / _PLANCK_H / 1e9

    return TwoQubitQuantization(
        Ej1_GHz=jp1.Ej_GHz,
        Ec1_GHz=ec1,
        Ej2_GHz=jp2.Ej_GHz,
        Ec2_GHz=ec2,
        g_GHz=g,
        Cc_fF=cc * 1e15,
        topology=topo,
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

    return TwoTransmonResult(
        omega1_GHz=omega1,
        omega2_GHz=omega2,
        detuning_GHz=detuning,
        J_GHz=j_ghz,
        one_excitation_splitting_GHz=splitting,
        g_GHz=g_GHz,
        coupled_levels_GHz=levels,
    )
