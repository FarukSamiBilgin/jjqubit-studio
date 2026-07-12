"""Independent physics reference for JJQubit validation.

This module computes ground-truth values *independently* of the project solvers,
so the validation tests are a genuine second witness rather than a rubber stamp
of whatever ``core/solvers`` does internally. Where possible the reference is a
from-scratch NumPy/SciPy computation (charge-basis Cooper-pair-box
diagonalization, RCSJ ODE integration); ``scqubits``/``QuTiP`` are used only as
a cross-check in the tests, never as the sole source of a target number.

Unit convention
----------------
Energies are reported as *frequencies* ``E/h`` in **hertz** (Hz). The junction
Josephson and charging energies are therefore ``Ej/h`` and ``Ec/h``. SI base
units are used for all physical inputs (A, F, ohm, s, V). Callers that want GHz
simply divide by ``1e9``.

Grounding references
--------------------
* Josephson relations and RCSJ model: Tinkham, *Introduction to
  Superconductivity*, 2nd ed., ch. 6.
* Transmon spectrum, anharmonicity and dispersive shift: J. Koch et al.,
  "Charge-insensitive qubit design derived from the Cooper pair box",
  Phys. Rev. A 76, 042319 (2007).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.constants as sc
from scipy.integrate import solve_ivp

# --- Physical constants (CODATA, via scipy.constants) ----------------------
H_PLANCK: float = sc.h            # J*s
E_CHARGE: float = sc.e            # C
HBAR: float = sc.hbar            # J*s
PHI0: float = H_PLANCK / (2.0 * E_CHARGE)  # superconducting flux quantum, Wb


# ---------------------------------------------------------------------------
# Junction energies
# ---------------------------------------------------------------------------
def josephson_energy_hz(critical_current_a: float) -> float:
    """Josephson energy ``Ej/h`` in Hz from the critical current.

    ``Ej = (Phi0 / 2*pi) * Ic = hbar * Ic / (2e)`` (Tinkham eq. 6.4). Dividing
    by Planck's constant gives a frequency.

    Args:
        critical_current_a: Junction critical current ``Ic`` in **amperes**.

    Returns:
        ``Ej/h`` in **hertz**.
    """
    ej_joule = PHI0 * critical_current_a / (2.0 * np.pi)
    return ej_joule / H_PLANCK


def charging_energy_hz(total_capacitance_f: float) -> float:
    """Single-electron charging energy ``Ec/h`` in Hz.

    ``Ec = e^2 / (2 C_Sigma)`` with the Koch 2007 convention (the charging
    energy of a *single* electron, so the transmon Hamiltonian reads
    ``4 Ec (n - ng)^2``). ``C_Sigma`` is the total capacitance shunting the
    junction island.

    Args:
        total_capacitance_f: Total island capacitance ``C_Sigma`` in **farads**.

    Returns:
        ``Ec/h`` in **hertz**.
    """
    ec_joule = E_CHARGE**2 / (2.0 * total_capacitance_f)
    return ec_joule / H_PLANCK


# ---------------------------------------------------------------------------
# Cooper-pair-box / transmon: from-scratch charge-basis diagonalization
# ---------------------------------------------------------------------------
def cpb_hamiltonian_hz(
    ej_hz: float, ec_hz: float, ng: float = 0.0, ncut: int = 30
) -> np.ndarray:
    """Cooper-pair-box Hamiltonian in the charge basis, in Hz.

    ``H = 4 Ec (n - ng)^2 - (Ej/2) sum_n (|n><n+1| + |n+1><n|)`` on the charge
    states ``n in [-ncut, ncut]`` (Koch 2007 eq. 2.1, in the charge basis).

    Args:
        ej_hz: Josephson energy ``Ej/h`` in Hz.
        ec_hz: Charging energy ``Ec/h`` in Hz.
        ng: Offset (gate) charge in units of ``2e`` (Cooper pairs).
        ncut: Charge-basis truncation; basis is ``2*ncut + 1`` states.

    Returns:
        A real symmetric ``(2*ncut+1, 2*ncut+1)`` matrix in Hz.
    """
    ns = np.arange(-ncut, ncut + 1)
    diag = 4.0 * ec_hz * (ns - ng) ** 2
    off = -0.5 * ej_hz * np.ones(len(ns) - 1)
    return np.diag(diag) + np.diag(off, 1) + np.diag(off, -1)


def cpb_eigensystem_hz(
    ej_hz: float, ec_hz: float, ng: float = 0.0, ncut: int = 30
) -> tuple[np.ndarray, np.ndarray]:
    """Eigenvalues (Hz, ascending) and eigenvectors of the CPB Hamiltonian.

    Returns:
        ``(evals_hz, evecs)`` where ``evecs[:, k]`` is the k-th eigenvector in
        the charge basis and ``evals_hz`` is sorted ascending.
    """
    h = cpb_hamiltonian_hz(ej_hz, ec_hz, ng=ng, ncut=ncut)
    evals, evecs = np.linalg.eigh(h)  # eigh already returns ascending evals
    return evals, evecs


def number_operator_matrix(evecs: np.ndarray, ncut: int, nlevels: int) -> np.ndarray:
    """Cooper-pair-number operator ``n`` in the low-lying eigenbasis.

    ``n`` is diagonal in the charge basis (values ``-ncut..ncut``); this returns
    its matrix elements ``<i|n|j>`` among the lowest ``nlevels`` eigenstates.
    Computed from scratch (no scqubits) so the dispersive-shift reference is
    fully independent.

    Args:
        evecs: Eigenvectors from :func:`cpb_eigensystem_hz`.
        ncut: The same truncation used to build the eigensystem.
        nlevels: Number of low-lying eigenstates to keep.

    Returns:
        A real ``(nlevels, nlevels)`` matrix of ``<i|n|j>`` (dimensionless).
    """
    ns = np.arange(-ncut, ncut + 1, dtype=float)
    v = evecs[:, :nlevels]
    return v.T @ (ns[:, None] * v)


@dataclass(frozen=True)
class TransmonReference:
    """Independent reference spectrum for a transmon, energies as ``E/h``.

    Attributes:
        ej_hz: Josephson energy ``Ej/h`` (Hz).
        ec_hz: Charging energy ``Ec/h`` (Hz).
        ej_ec_ratio: Dimensionless ``Ej/Ec``.
        e01_hz: 0->1 transition frequency ``(E1-E0)/h`` (Hz).
        e12_hz: 1->2 transition frequency ``(E2-E1)/h`` (Hz).
        anharmonicity_hz: ``(E12 - E01)`` (Hz); negative for a transmon.
    """

    ej_hz: float
    ec_hz: float
    ej_ec_ratio: float
    e01_hz: float
    e12_hz: float
    anharmonicity_hz: float


def transmon_reference(
    ej_hz: float, ec_hz: float, ng: float = 0.0, ncut: int = 40
) -> TransmonReference:
    """Diagonalize a transmon from scratch and return its reference spectrum.

    Args:
        ej_hz: Josephson energy ``Ej/h`` in Hz.
        ec_hz: Charging energy ``Ec/h`` in Hz.
        ng: Offset charge in Cooper pairs (0 by default).
        ncut: Charge-basis truncation.

    Returns:
        A :class:`TransmonReference`.
    """
    evals, _ = cpb_eigensystem_hz(ej_hz, ec_hz, ng=ng, ncut=ncut)
    e01 = evals[1] - evals[0]
    e12 = evals[2] - evals[1]
    return TransmonReference(
        ej_hz=ej_hz,
        ec_hz=ec_hz,
        ej_ec_ratio=ej_hz / ec_hz,
        e01_hz=e01,
        e12_hz=e12,
        anharmonicity_hz=e12 - e01,
    )


def charge_dispersion_hz(
    ej_hz: float, ec_hz: float, level: int = 0, ncut: int = 40
) -> float:
    """Peak-to-peak charge dispersion of an energy level, in Hz.

    The charge dispersion ``epsilon_m = E_m(ng=1/2) - E_m(ng=0)`` measures a
    level's sensitivity to offset charge. It is O(Ej,Ec) in the Cooper-pair-box
    limit ``Ej/Ec -> 0`` and is *exponentially suppressed* in the transmon limit
    ``Ej/Ec >> 1`` (Koch 2007 eq. 2.5). Returned as an absolute value in Hz.

    Args:
        ej_hz: Josephson energy ``Ej/h`` in Hz.
        ec_hz: Charging energy ``Ec/h`` in Hz.
        level: Which energy level ``m`` (0 = ground).
        ncut: Charge-basis truncation.

    Returns:
        ``|E_m(1/2) - E_m(0)|`` in Hz.
    """
    e0, _ = cpb_eigensystem_hz(ej_hz, ec_hz, ng=0.0, ncut=ncut)
    e5, _ = cpb_eigensystem_hz(ej_hz, ec_hz, ng=0.5, ncut=ncut)
    return abs(e5[level] - e0[level])


# ---------------------------------------------------------------------------
# Dispersive shift chi
# ---------------------------------------------------------------------------
def dispersive_shift_multilevel_hz(
    levels_hz: np.ndarray,
    n_matrix: np.ndarray,
    g01_hz: float,
    resonator_hz: float,
) -> float:
    """Dispersive shift ``chi`` (Hz) from multilevel perturbation theory.

    Second-order dispersive perturbation theory for a multilevel transmon
    capacitively coupled to a resonator. The resonator-frequency pull when the
    qubit is in state ``|i>`` is::

        S_i = sum_{j != i} g_ij^2 * 2*w_ij / (w_ij^2 - w_r^2)

    with ``w_ij = (E_i - E_j)/h`` and ``g_ij = g01 * |n_ij| / |n_01|`` (the
    coupling scales with the charge matrix element). The measured dispersive
    shift is ``chi = (S_1 - S_0) / 2``.

    Using the *real* transmon matrix elements matters: the popular compact
    formula ``chi = g^2 * alpha / (Delta * (Delta + alpha))`` implicitly assumes
    ideal harmonic-ladder matrix elements ``|n_12|/|n_01| = sqrt(2)`` and is
    ~30% off for a realistic transmon. This full-sum expression was verified
    against a direct QuTiP diagonalization (agreement < 1% in the dispersive
    limit); see ``test_dispersive_chi.py``.

    Args:
        levels_hz: Transmon eigen-energies ``E_i/h`` in Hz (index 0 = ground).
        n_matrix: Charge-operator matrix elements ``<i|n|j>`` in the same basis
            ordering as ``levels_hz`` (from :func:`number_operator_matrix`).
        g01_hz: Bare 0<->1 coupling strength ``g01`` in Hz.
        resonator_hz: Bare resonator frequency ``w_r`` in Hz.

    Returns:
        ``chi`` in Hz (negative when the qubit is below the resonator here).
    """
    n01 = abs(n_matrix[0, 1])
    nlev = len(levels_hz)

    def pull(i: int) -> float:
        total = 0.0
        for j in range(nlev):
            if j == i:
                continue
            g_ij = g01_hz * abs(n_matrix[i, j]) / n01
            w_ij = levels_hz[i] - levels_hz[j]
            total += g_ij**2 * (2.0 * w_ij) / (w_ij**2 - resonator_hz**2)
        return total

    return 0.5 * (pull(1) - pull(0))


def dispersive_shift_simple_hz(
    e01_hz: float, anharmonicity_hz: float, g01_hz: float, resonator_hz: float
) -> float:
    """Compact two-level+anharmonicity dispersive-shift formula (Hz).

    ``chi = g^2 * alpha / (Delta * (Delta + alpha))`` with ``Delta = w01 - wr``
    (Koch 2007 eq. 3.7 / Blais et al.). Provided for comparison ONLY: it assumes
    ideal harmonic matrix elements and is a systematically poor approximation
    for a realistic transmon. Do not use it as an acceptance target.
    """
    delta = e01_hz - resonator_hz
    return g01_hz**2 * anharmonicity_hz / (delta * (delta + anharmonicity_hz))


# ---------------------------------------------------------------------------
# Classical RCSJ junction: from-scratch ODE integration
# ---------------------------------------------------------------------------
def rcsj_dc_voltage_volt(
    critical_current_a: float,
    normal_resistance_ohm: float,
    capacitance_f: float,
    bias_current_a: float,
    n_plasma_periods: float = 400.0,
    settle_fraction: float = 0.5,
) -> float:
    """Time-averaged DC voltage across a current-biased RCSJ junction (volts).

    Integrates the resistively-and-capacitively-shunted-junction equation
    (Tinkham eq. 6.28), written for the gauge-invariant phase ``phi``::

        (hbar C / 2e) phi'' + (hbar / 2e R) phi' + Ic sin(phi) = I_bias

    The Josephson voltage is ``V = (hbar / 2e) phi'``. The integration starts
    ON the zero-voltage supercurrent branch, i.e. at the static fixed point
    ``phi0 = arcsin(I/Ic)`` (clipped to +/-pi/2 for ``|I| >= Ic``) with
    ``phi' = 0``. This is deliberate: the CLAUDE.md limit "I < Ic => V = 0"
    is a statement about that branch. For ``I_bias < Ic`` the fixed point is
    stable, ``phi'`` stays ~0, and the DC voltage is **zero**. For
    ``I_bias > Ic`` no static solution exists, the phase runs, and a finite DC
    voltage develops.

    (Hysteretic *dynamic switching* of an underdamped junction driven by a
    sudden bias step from rest is separate physics and is NOT what this limit
    probes; starting on the branch isolates the branch property cleanly.)

    Args:
        critical_current_a: ``Ic`` in amperes.
        normal_resistance_ohm: Shunt/normal resistance ``R`` in ohms.
        capacitance_f: Junction capacitance ``C`` in farads.
        bias_current_a: Applied bias current ``I_bias`` in amperes.
        n_plasma_periods: Integration span in units of the plasma period.
        settle_fraction: Fraction of the time trace (from the start) to discard
            as transient before averaging ``phi'``.

    Returns:
        The DC (time-averaged) voltage in **volts**. Non-negative for
        ``I_bias >= 0``.
    """
    a = HBAR / (2.0 * E_CHARGE)  # phi-to-flux factor; V = a * phi'
    # Plasma frequency sets the natural timescale: wp = sqrt(2e Ic / (hbar C)).
    wp = np.sqrt(critical_current_a / (a * capacitance_f))
    t_end = n_plasma_periods * (2.0 * np.pi / wp)
    # Start on the supercurrent branch (static fixed point).
    phi0 = float(np.arcsin(np.clip(bias_current_a / critical_current_a, -1.0, 1.0)))

    def rhs(_t: float, y: np.ndarray) -> list[float]:
        phi, phidot = y
        phiddot = (
            bias_current_a
            - critical_current_a * np.sin(phi)
            - (a / normal_resistance_ohm) * phidot
        ) / (capacitance_f * a)
        return [phidot, phiddot]

    n_eval = 20000
    t_eval = np.linspace(0.0, t_end, n_eval)
    sol = solve_ivp(
        rhs,
        (0.0, t_end),
        y0=[phi0, 0.0],
        t_eval=t_eval,
        method="RK45",
        rtol=1e-8,
        atol=1e-10,
        max_step=(2.0 * np.pi / wp) / 40.0,
    )
    phidot = sol.y[1]
    start = int(settle_fraction * len(phidot))
    v_dc = a * float(np.mean(phidot[start:]))
    return v_dc


# ---------------------------------------------------------------------------
# The project's reference transmon (examples/transmon_readout.json)
# ---------------------------------------------------------------------------
# Junction J1: Ic = 30 nA, Cj = 2 fF, Rn = 10 kohm; shunt Cs = 70 fF; the
# qubit island also carries the coupling capacitor Cg = 5 fF to the resonator.
EXAMPLE_IC_A: float = 30e-9
EXAMPLE_CJ_F: float = 2e-15
EXAMPLE_CS_F: float = 70e-15
EXAMPLE_CG_F: float = 5e-15
# Primary total island capacitance convention: Cj + Cs + Cg. The bare-island
# convention Cj + Cs (= 72 fF) is also plausible depending on how the solver
# treats the coupling capacitor; see notes in test_literature.py.
EXAMPLE_C_SIGMA_F: float = EXAMPLE_CJ_F + EXAMPLE_CS_F + EXAMPLE_CG_F  # 77 fF
EXAMPLE_RESONATOR_HZ: float = 7.2e9


def example_transmon_reference() -> TransmonReference:
    """Reference spectrum for the project's example transmon (Hz units).

    Built from ``examples/transmon_readout.json`` parameters using the
    ``Cj + Cs + Cg`` island-capacitance convention.
    """
    ej = josephson_energy_hz(EXAMPLE_IC_A)
    ec = charging_energy_hz(EXAMPLE_C_SIGMA_F)
    return transmon_reference(ej, ec)
