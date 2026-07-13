"""Physics validation for the T1/T2 coherence estimates.

The coherence layer wraps scqubits' noise API; these checks guard the physical
sanity of what we report rather than re-deriving scqubits' noise integrals:

- The Ramsey bound T2 <= 2*T1 must always hold.
- A flux-tunable (squid) qubit must be at a dephasing SWEET SPOT at flux = 0
  (first-order flux-insensitive: T2 there is much longer than just off it), the
  single most important design fact about tunable transmons.
- A fixed junction has no flux-noise channel; a squid does.
- Times are physically plausible (tens of microseconds for this transmon), not
  off by a unit-conversion factor of 1000 (the classic ns/us trap).
"""

from __future__ import annotations

import copy
import math
import pathlib

import pytest
from core.netlist import load
from core.netlist.units import Quantity
from core.solvers.quantum.coherence import compute_coherence, purcell_t1_us
from core.solvers.quantum.dispersive import compute_dispersive_shift
from core.solvers.quantum.quantization import quantize_circuit
from core.solvers.quantum.spectrum import compute_transmon_spectrum

# tests/validation/test_coherence.py -> parents[2] is the repo root.
_EXAMPLES = pathlib.Path(__file__).resolve().parents[2] / "examples"
TRANSMON = str(_EXAMPLES / "transmon_readout.json")
TUNABLE = str(_EXAMPLES / "tunable_transmon.json")


def _coherence_at_flux(flux: float):
    net = load(TUNABLE, validate=True)
    net = copy.deepcopy(net)
    squid = next(el for el in net.elements if el.type == "squid")
    squid.params["flux"] = Quantity(value=flux, unit="")
    return compute_coherence(quantize_circuit(net))


class TestFixedTransmon:
    def test_t2_within_ramsey_bound(self):
        c = compute_coherence(quantize_circuit(load(TRANSMON, validate=True)))
        assert c.T2_us <= 2.0 * c.T1_us + 1e-6

    def test_times_are_microsecond_scale_not_ns_mislabeled(self):
        # A good transmon is tens of us here; a ns/us slip would make this ~0.03.
        c = compute_coherence(quantize_circuit(load(TRANSMON, validate=True)))
        assert 1.0 < c.T1_us < 1000.0
        assert 1.0 < c.T2_us < 2000.0

    def test_fixed_junction_has_no_flux_dephasing_channel(self):
        c = compute_coherence(quantize_circuit(load(TRANSMON, validate=True)))
        assert "tphi_1_over_f_flux" not in c.tphi_channels_us


class TestTunableSweetSpot:
    def test_t2_within_ramsey_bound_at_several_fluxes(self):
        for flux in (0.0, 0.1, 0.25, 0.4):
            c = _coherence_at_flux(flux)
            assert c.T2_us <= 2.0 * c.T1_us + 1e-6

    def test_flux_zero_is_a_dephasing_sweet_spot(self):
        # The defining property of a tunable transmon: at flux=0 the qubit is
        # first-order insensitive to flux noise, so T2 is dramatically longer
        # than a little off the sweet spot.
        c_sweet = _coherence_at_flux(0.0)
        c_off = _coherence_at_flux(0.25)
        assert c_sweet.T2_us > 5.0 * c_off.T2_us

    def test_squid_has_a_flux_dephasing_channel_off_sweet_spot(self):
        c = _coherence_at_flux(0.25)
        assert "tphi_1_over_f_flux" in c.tphi_channels_us
        # And it is the (or a) limiting dephasing channel off the sweet spot.
        assert c.tphi_channels_us["tphi_1_over_f_flux"] < 100.0  # us, i.e. short

    def test_sweet_spot_flux_dephasing_is_negligible(self):
        # At flux=0 the 1/f flux dephasing time diverges (first-order zero).
        c = _coherence_at_flux(0.0)
        flux_tphi = c.tphi_channels_us.get("tphi_1_over_f_flux", float("inf"))
        assert flux_tphi > 1e4  # essentially infinite compared to other channels


class TestPurcellT1:
    def test_formula_scales_as_delta_over_g_squared_and_inverse_kappa(self):
        # Gamma ~ kappa (g/Delta)^2, so T1 ~ (Delta/g)^2 / kappa.
        base = purcell_t1_us(g_GHz=0.05, delta_GHz=1.0, kappa_GHz=1e-3)
        # Double the detuning -> 4x longer T1.
        assert purcell_t1_us(0.05, 2.0, 1e-3) == pytest.approx(4.0 * base, rel=1e-9)
        # Double kappa -> half the T1.
        assert purcell_t1_us(0.05, 1.0, 2e-3) == pytest.approx(base / 2.0, rel=1e-9)

    def test_uncoupled_qubit_has_infinite_purcell_t1(self):
        assert purcell_t1_us(g_GHz=0.0, delta_GHz=1.0, kappa_GHz=1e-3) == float("inf")

    def test_purcell_shortens_total_t1_below_intrinsic(self):
        net = load(TRANSMON, validate=True)
        quantization = quantize_circuit(net)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        dispersive = compute_dispersive_shift(quantization, spectrum)

        without = compute_coherence(quantization)
        with_purcell = compute_coherence(quantization, dispersive=dispersive)

        assert math.isinf(without.T1_purcell_us)
        assert math.isfinite(with_purcell.T1_purcell_us)
        # Total T1 with Purcell is below the intrinsic-only T1 (an added loss).
        assert with_purcell.T1_us < with_purcell.T1_intrinsic_us
        assert with_purcell.T1_intrinsic_us == pytest.approx(without.T1_us, rel=1e-9)
        # And still a physical Ramsey bound.
        assert with_purcell.T2_us <= 2.0 * with_purcell.T1_us + 1e-6
