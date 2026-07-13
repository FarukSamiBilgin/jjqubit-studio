"""Qubit coherence times T1, T2 and pure dephasing Tphi.

Thin layer over scqubits' noise/coherence API (CLAUDE.md "Yapmayacaklarimiz"
#2 -- we do not reimplement the noise physics). scqubits already implements the
standard superconducting-qubit noise channels (1/f flux/charge/critical-current
dephasing, dielectric-loss and charge-impedance T1, quasiparticle tunneling,
flux-bias-line T1) with literature-standard default amplitudes; we call its
``t1_effective`` / ``t2_effective`` and report the result in microseconds, plus
a per-channel breakdown.

Why the qubit object is rebuilt here (not reused from the spectrum): the squid
path collapses flux tuning into an effective Ej and diagonalizes a plain
``Transmon``, which has NO flux-noise channels. But flux noise is the dominant
dephasing source for a tunable qubit AWAY from its flux sweet spot -- ignoring
it would badly overestimate T2. So for a squid we build a real
``scqubits.TunableTransmon`` at the applied flux, which carries
``tphi_1_over_f_flux`` and ``t1_flux_bias_line``; for a fixed junction we build
a ``Transmon``. This reproduces the textbook behavior that T2 is protected at
the sweet spot (flux = 0) and degrades sharply away from it.

Units: with EJ/EC in GHz, scqubits returns coherence times in nanoseconds; we
convert to microseconds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import scqubits as scq

from .quantization import QubitQuantization

if TYPE_CHECKING:
    from .dispersive import DispersiveResult

# Dilution-refrigerator base temperature (scqubits' own default), in kelvin.
STANDARD_TEMPERATURE_K = 0.015

# Charge basis truncation for the coherence qubit object; 40 is well converged
# in the transmon regime this solver targets (matches the spectrum module).
_NCUT = 40


@dataclass(frozen=True)
class CoherenceResult:
    """Estimated coherence times, in microseconds.

    Args:
        T1_us: Total relaxation time T1, in us -- the intrinsic (scqubits)
            channels combined in parallel with the Purcell channel when a
            resonator coupling is known.
        T2_us: Ramsey coherence time T2 (uses the total T1 + pure dephasing), us.
        Tphi_us: Pure dephasing time from 1/T2 = 1/(2 T1) + 1/Tphi, in us;
            ``inf`` when dephasing is negligible.
        T1_intrinsic_us: T1 from the scqubits noise channels alone (no Purcell).
        T1_purcell_us: Purcell-limited T1 through the readout resonator, in us;
            ``inf`` when no resonator coupling was provided (g = 0).
        temperature_K: Bath temperature the estimate assumed, in kelvin.
        t1_channels_us: Per-channel T1 contribution (each in us); larger = the
            channel matters less. Includes ``t1_purcell`` when applicable.
        tphi_channels_us: Per-channel pure-dephasing contribution, in us.
    """

    T1_us: float
    T2_us: float
    Tphi_us: float
    T1_intrinsic_us: float
    T1_purcell_us: float
    temperature_K: float
    t1_channels_us: dict[str, float]
    tphi_channels_us: dict[str, float]


def _build_qubit(quantization: QubitQuantization):
    """Build the scqubits qubit matching the element type (see module docstring)."""
    if quantization.element_type == "squid":
        return scq.TunableTransmon(
            EJmax=quantization.EjMax_GHz,
            EC=quantization.Ec_GHz,
            d=quantization.asymmetry_d,
            flux=quantization.flux,
            ng=0.0,
            ncut=_NCUT,
        )
    return scq.Transmon(
        EJ=quantization.Ej_GHz,
        EC=quantization.Ec_GHz,
        ng=0.0,
        ncut=_NCUT,
    )


def purcell_t1_us(g_GHz: float, delta_GHz: float, kappa_GHz: float) -> float:
    """Purcell-limited T1 through a lossy readout resonator, in microseconds.

    In the dispersive regime the qubit relaxes through its coupling to the
    resonator at rate ``Gamma_Purcell = kappa * (g/Delta)^2`` (Krantz et al.,
    "A Quantum Engineer's Guide to Superconducting Qubits", 2019). g, Delta and
    kappa are ordinary frequencies (GHz) here; the decay rate in 1/s is
    ``2*pi * kappa[Hz] * (g/Delta)^2`` and T1 = 1/Gamma.

    Returns ``inf`` when the qubit is uncoupled (g = 0). This is the physics
    reason a readout resonator needs a Purcell filter (out of MVP scope): a low
    kappa or small detuning shortens T1.
    """
    if g_GHz == 0.0 or delta_GHz == 0.0:
        return math.inf
    gamma_per_s = 2.0 * math.pi * (kappa_GHz * 1e9) * (g_GHz / delta_GHz) ** 2
    if gamma_per_s == 0.0:
        return math.inf
    return (1.0 / gamma_per_s) * 1e6  # seconds -> microseconds


def _parallel(a_us: float, b_us: float) -> float:
    """Combine two relaxation times in parallel (rates add): 1/T = 1/a + 1/b."""
    if math.isinf(a_us):
        return b_us
    if math.isinf(b_us):
        return a_us
    return 1.0 / (1.0 / a_us + 1.0 / b_us)


def compute_coherence(
    quantization: QubitQuantization,
    *,
    dispersive: DispersiveResult | None = None,
    temperature_K: float = STANDARD_TEMPERATURE_K,
) -> CoherenceResult:
    """Estimate T1, T2 and Tphi for the quantized qubit using scqubits defaults.

    Args:
        quantization: Result of
            :func:`core.solvers.quantum.quantization.quantize_circuit`.
        dispersive: Optional result of
            :func:`core.solvers.quantum.dispersive.compute_dispersive_shift`. When
            given, the Purcell-limited T1 through the resonator is computed and
            combined into the total T1/T2.
        temperature_K: Bath temperature, in kelvin (default 15 mK).

    Returns:
        The :class:`CoherenceResult`, all times in microseconds.
    """
    qubit = _build_qubit(quantization)
    opts = {"T": temperature_K}

    t1_intrinsic_ns = qubit.t1_effective(common_noise_options=opts)
    t2_scqubits_ns = qubit.t2_effective(common_noise_options=opts)

    # Per-channel breakdown over scqubits' EFFECTIVE channel set -- i.e. the
    # channels that actually feed t1_effective/t2_effective, NOT every supported
    # one. scqubits deliberately omits some supported channels (e.g.
    # t1_charge_impedance, whose default parameters give an unphysically short
    # ~0.2 ns time) from the effective estimate; iterating the effective set
    # keeps this breakdown consistent with the headline T1/T2 and avoids
    # reporting a misleading number.
    #
    # scqubits' t1_* methods take T as a direct kwarg, while tphi_* methods take
    # common_noise_options -- dispatch by prefix.
    t1_channels: dict[str, float] = {}
    tphi_channels: dict[str, float] = {}
    for channel in qubit.effective_noise_channels():
        method = getattr(qubit, channel)
        if channel.startswith("t1"):
            t1_channels[channel] = method(T=temperature_K) / 1e3
        elif channel.startswith("tphi"):
            tphi_channels[channel] = method(common_noise_options=opts) / 1e3

    t1_intrinsic_us = t1_intrinsic_ns / 1e3

    # Pure dephasing is independent of the T1 mechanism: derive it from
    # scqubits' T2 and its intrinsic T1, then recombine with the total T1.
    inv_tphi_ns = 1.0 / t2_scqubits_ns - 1.0 / (2.0 * t1_intrinsic_ns)
    tphi_us = (1.0 / inv_tphi_ns) / 1e3 if inv_tphi_ns > 0 else math.inf

    # Purcell relaxation through the resonator, if a coupling is known.
    t1_purcell_us = math.inf
    if dispersive is not None:
        t1_purcell_us = purcell_t1_us(
            dispersive.g_GHz, dispersive.Delta_GHz, dispersive.kappa_GHz
        )
        if math.isfinite(t1_purcell_us):
            t1_channels["t1_purcell"] = t1_purcell_us

    t1_total_us = _parallel(t1_intrinsic_us, t1_purcell_us)

    # T2 from the TOTAL T1 and the pure dephasing: 1/T2 = 1/(2 T1) + 1/Tphi.
    inv_t2 = 1.0 / (2.0 * t1_total_us) + (0.0 if math.isinf(tphi_us) else 1.0 / tphi_us)
    t2_total_us = 1.0 / inv_t2

    return CoherenceResult(
        T1_us=t1_total_us,
        T2_us=t2_total_us,
        Tphi_us=tphi_us,
        T1_intrinsic_us=t1_intrinsic_us,
        T1_purcell_us=t1_purcell_us,
        temperature_K=temperature_K,
        t1_channels_us=t1_channels,
        tphi_channels_us=tphi_channels,
    )
