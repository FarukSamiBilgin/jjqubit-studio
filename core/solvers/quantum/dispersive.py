"""Dispersive coupling to the readout resonator: g and chi.

Coupling strength g
-------------------
Standard circuit-QED capacitive coupling formula (Blais et al., PRA 69,
062320 (2004); Koch et al., PRA 76, 042319 (2007); Krantz et al., "A Quantum
Engineer's Guide to Superconducting Qubits", Appl. Phys. Rev. 6, 021318
(2019), Eq. for g_{i,j})::

    g_01 = 2 * e * beta * <0|n|1> * delta_V0 / h       [[GHz]]

    beta       = Cg / C_sigma                         (capacitive divider ratio)
    delta_V0   = omega_r * sqrt(hbar * Z_r / pi)      (resonator zero-point
                                                        voltage fluctuation)
    <0|n|1>    = transmon charge matrix element (from scqubits, see spectrum.py)

``g_01`` above is the COMPLETE, ready-to-use physical vacuum Rabi coupling
for the 0<->1 transition -- this is what :data:`DispersiveResult.g_GHz`
reports, and what any downstream consumer (waveform-ui, docs, other
solvers) should read "g" as meaning.

Internally, however, the non-perturbative chi calculation below drives the
composite Hilbert space with the FULL (un-projected) transmon charge
operator ``n`` -- not a 2-level sigma_01 -- because that operator's own
matrix elements (n01, n12, ...) are what let the diagonalization see the
real multi-level transmon physics. Since ``n``'s matrix element between
levels 0 and 1 is already <0|n|1>, the coefficient multiplying the FULL
operator must be the "bare" ``g_bare = 2*e*beta*delta_V0/h`` -- WITHOUT an
extra factor of <0|n|1> -- so that the 0<->1 block of the resulting
Hamiltonian reproduces ``g_01`` above exactly once. Multiplying by <0|n|1>
twice (once by hand, once via the operator's own matrix element) would
double-count it and inflate the effective coupling seen by the composite
system by a factor of <0|n|1> (~14% for the bundled example) -- this
solver computes ``g_bare`` internally and reports ``g_bare * n01 = g_01``
as ``g_GHz``, precisely to avoid that trap.

ASSUMPTION (approved by lead, see team log): the netlist's ``resonator``
element only carries ``f0`` and ``Q`` (docs/netlist_schema.md section 3) --
no capacitance or characteristic impedance. delta_V0 needs the resonator's
own impedance scale, which the frozen schema does not expose, so we assume
``Z_r = 50 ohm`` -- the standard on-chip CPW resonator design impedance,
and the same value already used for ``transmission_line.Z0`` in both
bundled example netlists. This is a solver-side physical assumption, not a
netlist schema change; it is recorded in the HDF5 output
(``/assumptions`` group) so it is auditable, per the project's physics
validation rule (CLAUDE.md).

Dispersive shift chi
---------------------
Rather than hand-rolling the textbook 2-level chi = g^2/Delta formula (which
ignores the transmon's higher levels and its non-two-level charge operator),
we build the full qubit+resonator composite Hilbert space with
``scqubits.HilbertSpace`` (transmon truncated to several levels, oscillator
mode for the resonator, capacitive interaction g*n*(a+a-dagger)) and
diagonalize it EXACTLY (non-perturbatively). This is the "prefer the
library's own implementation" path CLAUDE.md asks for, and it is *more*
correct than the perturbative formula: it captures the real multi-level
transmon physics (which shifts chi substantially from the naive 2-level
estimate -- see tests/solvers_quantum/test_dispersive.py for the
convergence check) and the (small) non-RWA/Bloch-Siegert-type correction
from keeping the full n*(a+a-dagger) coupling rather than a
rotating-wave-approximated Jaynes-Cummings term.

chi is extracted from the dressed spectrum as::

    chi = [(E_{1,1} - E_{1,0}) - (E_{0,1} - E_{0,0})] / 2

where E_{q,n} is the dressed energy adiabatically connected to the bare
product state |qubit level q, resonator photon number n>. This is the
resonator-frequency shift picked up when the qubit is excited (a fully
non-perturbative generalization of "chi = g^2/Delta"); see the module
docstring test in test_dispersive.py for the closed-form cross-check this
was validated against (exact agreement in the 2-level limit, then a
convergent, physically expected multi-level correction).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import scqubits as scq
from scipy.constants import e as _ELEMENTARY_CHARGE
from scipy.constants import h as _PLANCK_H
from scipy.constants import hbar as _HBAR

from .quantization import QubitQuantization
from .spectrum import TransmonSpectrum

# See module docstring: the netlist's `resonator` element has no impedance
# parameter, so we assume the standard on-chip CPW design value. Approved by
# lead; documented here and mirrored into the HDF5 `/assumptions` group.
DEFAULT_RESONATOR_IMPEDANCE_OHM = 50.0

# Oscillator (resonator mode) truncation for the composite Hilbert space.
# Only the |0>,|1> photon manifolds are physically needed for chi, but a
# larger truncation keeps the diagonalization stable/insensitive to basis
# edge effects; 6 is comfortably converged for the weak-coupling regime this
# solver targets (see test_dispersive.py convergence checks).
_OSCILLATOR_TRUNCATED_DIM = 6


@dataclass(frozen=True)
class DispersiveResult:
    """Qubit-resonator coupling and dispersive shift, in GHz.

    Args:
        g_GHz: The PHYSICAL qubit-resonator vacuum Rabi coupling for the
            0<->1 transition, g_01 = 2*e*beta*<0|n|1>*delta_V0/h (frequency
            units, i.e. g/2pi in the usual angular-frequency convention --
            consistent with scqubits' GHz-as-frequency convention
            throughout). This is the number to read as "the coupling
            strength g" -- see module docstring for why the internal
            diagonalization uses a different ("bare", n01-free)
            coefficient and how the two relate.
        chi_GHz: Dispersive shift chi, computed non-perturbatively (see
            module docstring for the exact definition and sign convention).
        Delta_GHz: E01 - f0 (qubit-resonator detuning), for reference/HDF5.
        beta: Capacitive divider ratio Cg / C_sigma (dimensionless).
        resonator_Z0_ohm: The assumed resonator impedance used for
            delta_V0 (see module docstring; always
            :data:`DEFAULT_RESONATOR_IMPEDANCE_OHM` for now).
        f0_GHz: The resonator's bare resonance frequency (as given in the
            netlist), for reference/HDF5.
        kappa_GHz: Resonator linewidth f0/Q, for reference/HDF5.
    """

    g_GHz: float
    chi_GHz: float
    Delta_GHz: float
    beta: float
    resonator_Z0_ohm: float
    f0_GHz: float
    kappa_GHz: float


def dressed_chi_ghz(
    transmon: scq.Transmon, oscillator: scq.Oscillator, g_ghz: float
) -> float:
    """Diagonalize the qubit+resonator composite system and return chi, in GHz.

    Exposed as a standalone helper (not just inlined in
    :func:`compute_dispersive_shift`) so it can be exercised directly against
    known analytic limits in tests/solvers_quantum/test_dispersive.py --
    e.g. a 2-level-truncated transmon should reproduce the exact closed-form
    dispersive shift chi = 2*g_eff^2*omega_q / (omega_q^2 - omega_r^2)
    (2nd-order non-degenerate perturbation theory for the full, non-RWA
    capacitive coupling n*(a+a-dagger); reduces to the textbook g^2/Delta
    near resonance).

    Args:
        transmon: A ``scqubits.Transmon`` (any truncation).
        oscillator: A ``scqubits.Oscillator`` representing the resonator mode.
        g_ghz: Coupling strength multiplying ``n * (a + a-dagger)``, in GHz.

    Returns:
        chi, in GHz, defined as
        ``[(E_{1,1}-E_{1,0}) - (E_{0,1}-E_{0,0})] / 2`` where ``E_{q,n}`` is
        the dressed energy adiabatically connected to bare product state
        |qubit level q, photon number n>.
    """
    hilbert_space = scq.HilbertSpace([transmon, oscillator])
    hilbert_space.add_interaction(
        g=g_ghz,
        op1=(transmon.n_operator, transmon),
        op2=(oscillator.creation_operator, oscillator),
        add_hc=True,
    )
    hilbert_space.generate_lookup()

    e00 = hilbert_space.energy_by_bare_index((0, 0))
    e01 = hilbert_space.energy_by_bare_index((0, 1))
    e10 = hilbert_space.energy_by_bare_index((1, 0))
    e11 = hilbert_space.energy_by_bare_index((1, 1))
    return ((e11 - e10) - (e01 - e00)) / 2.0


def _coupling_strengths_ghz(
    quantization: QubitQuantization,
    spectrum: TransmonSpectrum,
    f0_ghz: float,
    z_r_ohm: float,
) -> tuple[float, float, float]:
    """Return (g_bare_GHz, g_01_GHz, beta) via the Blais/Koch/Krantz formula.

    ``g_bare`` is the coefficient of the FULL charge operator (feed this to
    :func:`dressed_chi_ghz`); ``g_01 = g_bare * <0|n|1>`` is the complete
    physical coupling (report this as :attr:`DispersiveResult.g_GHz`). See
    the module docstring for why these are NOT the same number.
    """
    beta = (
        quantization.Cg_fF / quantization.C_sigma_fF
        if quantization.C_sigma_fF > 0
        else 0.0
    )
    if beta == 0.0:
        return 0.0, 0.0, 0.0

    omega_r = 2.0 * math.pi * f0_ghz * 1e9  # rad/s
    delta_v0 = omega_r * math.sqrt(
        _HBAR * z_r_ohm / math.pi
    )  # Volts (zero-point fluctuation)

    g_bare_joules = (
        2.0 * _ELEMENTARY_CHARGE * beta * delta_v0
    )  # NO n01 factor here (see above)
    g_bare_ghz = (g_bare_joules / _PLANCK_H) / 1e9
    g_01_ghz = g_bare_ghz * spectrum.n01
    return g_bare_ghz, g_01_ghz, beta


def compute_dispersive_shift(
    quantization: QubitQuantization,
    spectrum: TransmonSpectrum,
    *,
    resonator_impedance_ohm: float = DEFAULT_RESONATOR_IMPEDANCE_OHM,
) -> DispersiveResult:
    """Compute the qubit-resonator coupling g and dispersive shift chi.

    Args:
        quantization: Result of
            :func:`core.solvers.quantum.quantization.quantize_circuit`
            (supplies Cg, C_sigma and the resonator's f0/Q).
        spectrum: Result of
            :func:`core.solvers.quantum.spectrum.compute_transmon_spectrum`
            for the SAME quantization (supplies E01 and the transmon object
            reused for the composite Hilbert space).
        resonator_impedance_ohm: Assumed resonator characteristic impedance;
            see module docstring. Overridable for sensitivity testing, but
            production callers should leave the documented MVP default.

    Returns:
        The :class:`DispersiveResult`, all frequencies in GHz.
    """
    f0_ghz = quantization.resonator_topology.resonator.params["f0"].to_si() / 1e9
    q_factor = quantization.resonator_topology.resonator.params["Q"].to_si()
    kappa_ghz = f0_ghz / q_factor

    g_bare_ghz, g_01_ghz, beta = _coupling_strengths_ghz(
        quantization, spectrum, f0_ghz, resonator_impedance_ohm
    )
    delta_ghz = spectrum.E01_GHz - f0_ghz

    if g_bare_ghz == 0.0:
        return DispersiveResult(
            g_GHz=0.0,
            chi_GHz=0.0,
            Delta_GHz=delta_ghz,
            beta=beta,
            resonator_Z0_ohm=resonator_impedance_ohm,
            f0_GHz=f0_ghz,
            kappa_GHz=kappa_ghz,
        )

    # NOTE: dressed_chi_ghz takes the BARE coefficient (of the full n
    # operator), not g_01 -- see module docstring. Passing g_01 here would
    # double-count <0|n|1> and inflate the effective simulated coupling.
    oscillator = scq.Oscillator(E_osc=f0_ghz, truncated_dim=_OSCILLATOR_TRUNCATED_DIM)
    chi_ghz = dressed_chi_ghz(spectrum.transmon, oscillator, g_bare_ghz)

    return DispersiveResult(
        g_GHz=g_01_ghz,
        chi_GHz=chi_ghz,
        Delta_GHz=delta_ghz,
        beta=beta,
        resonator_Z0_ohm=resonator_impedance_ohm,
        f0_GHz=f0_ghz,
        kappa_GHz=kappa_ghz,
    )
