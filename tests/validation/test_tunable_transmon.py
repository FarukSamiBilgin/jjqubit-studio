"""Physics validation for the flux-tunable (squid) transmon.

CLAUDE.md's physics rule: every solver path must be checked against a known
reference, not just for internal consistency. The squid path computes an
effective Josephson energy Ej(flux) = EjMax * sqrt(cos^2(pi f) + d^2 sin^2(pi f))
and feeds it to the existing (validated) fixed-transmon spectrum. Here we
cross-check that pipeline, end to end, against scqubits' own
``TunableTransmon`` -- an independent implementation of exactly this physics
(Koch et al., PRA 76, 042319 (2007), eq. 2.16). If our netlist -> quantization
-> spectrum pipeline and scqubits.TunableTransmon disagree, one is wrong.

Also checks the analytic flux-tuning limits directly: f=0 gives EjMax, a
symmetric SQUID is fully suppressed at f=0.5, and an asymmetric one bottoms out
at |d|*EjMax.
"""

from __future__ import annotations

import math

import pytest
import scqubits as scq
from core.netlist.model import Connection, Element, Netlist
from core.netlist.units import Quantity
from core.solvers.quantum.quantization import (
    flux_tunable_ej_factor,
    quantize_circuit,
)
from core.solvers.quantum.spectrum import compute_transmon_spectrum


def _squid_netlist(*, flux: float = 0.0, d: float = 0.0, ic_max_nA: float = 30.0):
    """A minimal squid + resonator netlist (mirrors the transmon test circuit)."""
    params = {
        "Ic_max": Quantity(ic_max_nA, "nA"),
        "Cj": Quantity(2.0, "fF"),
        "Rn": Quantity(10.0, "kohm"),
    }
    if flux:
        params["flux"] = Quantity(flux, "")
    if d:
        params["d"] = Quantity(d, "")
    return Netlist(
        name="squid + resonator",
        nodes=["gnd", "q", "r"],
        elements=[
            Element("SQ", "squid", params),
            Element("Cs", "capacitor", {"C": Quantity(70.0, "fF")}),
            Element("Cg", "capacitor", {"C": Quantity(5.0, "fF")}),
            Element(
                "R1",
                "resonator",
                {"f0": Quantity(7.2, "GHz"), "Q": Quantity(8000.0, "")},
            ),
            Element("G", "ground", {}),
        ],
        connections=[
            Connection("SQ", 0, "q"),
            Connection("SQ", 1, "gnd"),
            Connection("Cs", 0, "q"),
            Connection("Cs", 1, "gnd"),
            Connection("Cg", 0, "q"),
            Connection("Cg", 1, "r"),
            Connection("R1", 0, "r"),
            Connection("R1", 1, "gnd"),
            Connection("G", 0, "gnd"),
        ],
    )


class TestFluxTuningFactor:
    def test_zero_flux_is_maximum(self):
        assert flux_tunable_ej_factor(0.0, 0.0) == pytest.approx(1.0)
        assert flux_tunable_ej_factor(0.0, 0.3) == pytest.approx(1.0)

    def test_symmetric_squid_fully_suppressed_at_half_flux(self):
        assert flux_tunable_ej_factor(0.5, 0.0) == pytest.approx(0.0, abs=1e-12)

    def test_asymmetric_squid_bottoms_out_at_abs_d(self):
        assert flux_tunable_ej_factor(0.5, 0.2) == pytest.approx(0.2)

    def test_quarter_flux_is_cos_pi_over_4(self):
        assert flux_tunable_ej_factor(0.25, 0.0) == pytest.approx(math.cos(math.pi / 4))


class TestAgainstScqubitsTunableTransmon:
    """Our netlist->spectrum pipeline must match scqubits.TunableTransmon."""

    @pytest.mark.parametrize("flux", [0.0, 0.15, 0.3, 0.45])
    @pytest.mark.parametrize("d", [0.0, 0.1])
    def test_e01_and_anharmonicity_match(self, flux, d):
        quantization = quantize_circuit(_squid_netlist(flux=flux, d=d))
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)

        # scqubits' own tunable transmon with the SAME EjMax/Ec/d/flux.
        tunable = scq.TunableTransmon(
            EJmax=quantization.EjMax_GHz,
            EC=quantization.Ec_GHz,
            d=d,
            flux=flux,
            ng=0.0,
            ncut=40,
        )
        evals = tunable.eigenvals(evals_count=3)
        e01_ref = evals[1] - evals[0]
        anharm_ref = (evals[2] - evals[1]) - (evals[1] - evals[0])

        assert spectrum.E01_GHz == pytest.approx(e01_ref, rel=1e-4)
        assert spectrum.anharmonicity_GHz == pytest.approx(anharm_ref, rel=1e-3)


class TestSquidReducesToJunction:
    def test_zero_flux_squid_matches_fixed_junction(self):
        # A squid at flux=0 with Ic_max == a junction's Ic must give the same Ej.
        from core.solvers.quantum.quantization import _ej_ghz_from_ic

        quantization = quantize_circuit(_squid_netlist(flux=0.0, ic_max_nA=30.0))
        assert quantization.element_type == "squid"
        assert quantization.Ej_GHz == pytest.approx(_ej_ghz_from_ic(30e-9))
        assert quantization.Ej_GHz == pytest.approx(quantization.EjMax_GHz)

    def test_symmetric_squid_at_half_flux_kills_ej(self):
        quantization = quantize_circuit(_squid_netlist(flux=0.5, d=0.0))
        assert quantization.Ej_GHz == pytest.approx(0.0, abs=1e-9)
        # Ej/Ec -> 0 is the deep charge-qubit (CPB) limit, not a transmon.
        assert quantization.Ej_over_Ec == pytest.approx(0.0, abs=1e-6)

    def test_flux_dependence_is_periodic_and_even(self):
        # Ej(f) = Ej(-f) = Ej(1-f): even about integer and half-integer flux.
        q_plus = quantize_circuit(_squid_netlist(flux=0.2))
        q_minus = quantize_circuit(_squid_netlist(flux=-0.2))
        q_wrap = quantize_circuit(_squid_netlist(flux=0.8))  # 1 - 0.2
        assert q_plus.Ej_GHz == pytest.approx(q_minus.Ej_GHz)
        assert q_plus.Ej_GHz == pytest.approx(q_wrap.Ej_GHz)
