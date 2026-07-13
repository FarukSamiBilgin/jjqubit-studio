"""Physics validation for the two-coupled-transmon spectrum (Faz 2).

The hallmark of qubit-qubit coupling is an avoided crossing in the
single-excitation manifold as the two qubits tune through resonance. These
checks pin that behavior against its analytic form
``splitting = 2*sqrt((Delta/2)^2 + J^2)``:

- On resonance the splitting is minimal and equals exactly 2J.
- J is linear in the coupling coefficient g.
- With g = 0 the two qubits are independent: the splitting is just the bare
  detuning and J = 0.
- The resonant splitting is smaller than the detuned splitting (the avoided
  crossing repels).
"""

from __future__ import annotations

import pytest
from core.netlist.model import Connection, Element, Netlist
from core.netlist.units import Quantity
from core.solvers.quantum.multiqubit import (
    compute_two_transmon_spectrum,
    quantize_two_qubit_circuit,
    solve_two_qubit_netlist,
)
from core.solvers.quantum.topology import TopologyError

EC = 0.25


def _two_qubit_netlist(*, Ic1=30.0, Ic2=30.0, Cc_fF=4.0, Cs_fF=75.0):
    """Two junctions, each shunted to ground, bridged by a coupling capacitor."""
    return Netlist(
        name="two coupled transmons",
        nodes=["gnd", "q1", "q2"],
        elements=[
            Element(
                "J1",
                "junction",
                {
                    "Ic": Quantity(Ic1, "nA"),
                    "Cj": Quantity(2.0, "fF"),
                    "Rn": Quantity(10.0, "kohm"),
                },
            ),
            Element("Cs1", "capacitor", {"C": Quantity(Cs_fF, "fF")}),
            Element(
                "J2",
                "junction",
                {
                    "Ic": Quantity(Ic2, "nA"),
                    "Cj": Quantity(2.0, "fF"),
                    "Rn": Quantity(10.0, "kohm"),
                },
            ),
            Element("Cs2", "capacitor", {"C": Quantity(Cs_fF, "fF")}),
            Element("Cc", "capacitor", {"C": Quantity(Cc_fF, "fF")}),
            Element("G", "ground", {}),
        ],
        connections=[
            Connection("J1", 0, "q1"),
            Connection("J1", 1, "gnd"),
            Connection("Cs1", 0, "q1"),
            Connection("Cs1", 1, "gnd"),
            Connection("J2", 0, "q2"),
            Connection("J2", 1, "gnd"),
            Connection("Cs2", 0, "q2"),
            Connection("Cs2", 1, "gnd"),
            Connection("Cc", 0, "q1"),
            Connection("Cc", 1, "q2"),
            Connection("G", 0, "gnd"),
        ],
    )


class TestAvoidedCrossing:
    def test_on_resonance_splitting_is_twice_J(self):
        r = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02)
        assert r.detuning_GHz == pytest.approx(0.0, abs=1e-9)
        assert r.one_excitation_splitting_GHz == pytest.approx(2.0 * r.J_GHz, rel=1e-6)
        assert r.J_GHz > 0.0

    def test_resonant_splitting_is_smaller_than_detuned(self):
        resonant = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02)
        detuned = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=0.02)
        assert (
            resonant.one_excitation_splitting_GHz < detuned.one_excitation_splitting_GHz
        )


class TestExchangeCouplingScaling:
    def test_J_is_linear_in_g(self):
        j1 = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02).J_GHz
        j2 = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.04).J_GHz
        assert j2 == pytest.approx(2.0 * j1, rel=1e-3)

    def test_stronger_coupling_widens_the_resonant_gap(self):
        weak = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.01)
        strong = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.03)
        assert strong.J_GHz > weak.J_GHz


class TestDecoupledLimit:
    def test_zero_coupling_gives_zero_J_and_bare_detuning(self):
        r = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=0.0)
        assert r.J_GHz == pytest.approx(0.0, abs=1e-6)
        # With no coupling the two single-excitation levels are just the bare
        # qubit frequencies, so their gap is the bare detuning.
        assert r.one_excitation_splitting_GHz == pytest.approx(
            abs(r.detuning_GHz), rel=1e-4
        )

    def test_off_resonance_splitting_follows_the_analytic_hyperbola(self):
        # splitting = 2 sqrt((Delta/2)^2 + J^2); check J extracted at resonance
        # predicts the detuned splitting from the same g.
        j = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02).J_GHz
        detuned = compute_two_transmon_spectrum(15.0, EC, 14.0, EC, g_GHz=0.02)
        delta = detuned.detuning_GHz
        predicted = 2.0 * ((delta / 2.0) ** 2 + j**2) ** 0.5
        assert detuned.one_excitation_splitting_GHz == pytest.approx(
            predicted, rel=0.05
        )


class TestApiContract:
    def test_rejects_nonpositive_energies(self):
        with pytest.raises(ValueError):
            compute_two_transmon_spectrum(0.0, EC, 15.0, EC, g_GHz=0.02)

    def test_rejects_too_few_evals(self):
        with pytest.raises(ValueError):
            compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02, evals_count=2)

    def test_ground_level_is_zero(self):
        r = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02)
        assert r.coupled_levels_GHz[0] == pytest.approx(0.0, abs=1e-9)


class TestTwoQubitNetlistQuantization:
    def test_decoupled_limit_recovers_single_qubit_ec_and_zero_g(self):
        # Cc -> 0: g -> 0, and each Ec matches an isolated island (Cj + Cs).
        from scipy.constants import e, h

        q = quantize_two_qubit_circuit(_two_qubit_netlist(Cc_fF=1e-6))
        c_island_f = (2.0 + 75.0) * 1e-15
        ec_single = e**2 / (2.0 * c_island_f) / h / 1e9
        assert q.Ec1_GHz == pytest.approx(ec_single, rel=1e-4)
        assert q.Ec2_GHz == pytest.approx(ec_single, rel=1e-4)
        assert q.g_GHz == pytest.approx(0.0, abs=1e-4)

    def test_coupling_g_matches_capacitance_matrix_formula(self):
        # g = 4 e^2 (C^-1)_12 / h, with C = [[C1+Cc,-Cc],[-Cc,C2+Cc]].
        import numpy as np
        from scipy.constants import e, h

        q = quantize_two_qubit_circuit(_two_qubit_netlist(Cc_fF=4.0))
        c_island = (2.0 + 75.0) * 1e-15
        cc = 4.0e-15
        cmat = np.array([[c_island + cc, -cc], [-cc, c_island + cc]])
        expected_g = 4.0 * e**2 * np.linalg.inv(cmat)[0, 1] / h / 1e9
        assert q.g_GHz == pytest.approx(expected_g, rel=1e-9)
        assert q.Cc_fF == pytest.approx(4.0, rel=1e-9)

    def test_identical_qubits_have_equal_energies(self):
        q = quantize_two_qubit_circuit(_two_qubit_netlist(Ic1=30.0, Ic2=30.0))
        assert q.Ej1_GHz == pytest.approx(q.Ej2_GHz)
        assert q.Ec1_GHz == pytest.approx(q.Ec2_GHz)

    def test_resonant_pair_shows_avoided_crossing_from_netlist(self):
        r = solve_two_qubit_netlist(_two_qubit_netlist(Ic1=30.0, Ic2=30.0))
        assert r.detuning_GHz == pytest.approx(0.0, abs=1e-6)
        assert r.one_excitation_splitting_GHz == pytest.approx(2.0 * r.J_GHz, rel=1e-6)
        assert r.J_GHz > 0.0


class TestTwoQubitTopologyErrors:
    def test_single_qubit_rejected(self):
        net = _two_qubit_netlist()
        # Drop J2 and its wiring -> only one Josephson element.
        net.elements = [el for el in net.elements if el.id != "J2"]
        net.connections = [c for c in net.connections if c.element != "J2"]
        with pytest.raises(TopologyError, match="exactly 2 Josephson"):
            quantize_two_qubit_circuit(net)

    def test_uncoupled_pair_rejected(self):
        net = _two_qubit_netlist()
        # Remove the coupling capacitor.
        net.elements = [el for el in net.elements if el.id != "Cc"]
        net.connections = [c for c in net.connections if c.element != "Cc"]
        with pytest.raises(TopologyError, match="bridges the two qubit islands"):
            quantize_two_qubit_circuit(net)


class TestStaticZZ:
    def test_detuned_pair_has_finite_zz(self):
        import math

        r = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=0.05)
        assert math.isfinite(r.zz_MHz)
        assert r.zz_MHz != 0.0

    def test_resonant_identical_pair_zz_is_nan(self):
        import math

        # At exact resonance the |10>/|01> product states are fully hybridized;
        # ZZ is not individually resolvable and is reported as NaN.
        r = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.05)
        assert math.isnan(r.zz_MHz)

    def test_zz_vanishes_in_the_decoupled_limit(self):
        r = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=1e-6)
        assert r.zz_MHz == pytest.approx(0.0, abs=1e-3)

    def test_zz_grows_with_coupling(self):
        weak = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=0.03)
        strong = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=0.06)
        assert abs(strong.zz_MHz) > abs(weak.zz_MHz)


class TestTwoQubitHdf5RoundTrip:
    def test_solution_writes_and_reader_loads(self, tmp_path):
        import jjqubit
        from gui.waveform.hdf5_reader import (
            detect_result_kind,
            load_two_qubit_result,
        )

        sol = jjqubit.solve_two_qubit(_two_qubit_netlist(Ic1=30.0, Ic2=26.0))
        out = tmp_path / "tq.h5"
        sol.write_hdf5(out)
        assert detect_result_kind(out) == "two_qubit"
        r = load_two_qubit_result(out)
        assert r.J_GHz == pytest.approx(sol.J_GHz, rel=1e-9)
        assert r.g_GHz == pytest.approx(sol.quantization.g_GHz, rel=1e-9)
        assert r.zz_MHz == pytest.approx(sol.zz_MHz, rel=1e-6)
        assert len(r.coupled_levels_GHz) == 6


class TestGateMetrics:
    def test_iswap_time_is_one_over_four_J(self):
        r = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02)
        assert r.iswap_gate_time_ns == pytest.approx(1.0 / (4.0 * r.J_GHz), rel=1e-9)

    def test_iswap_time_shrinks_with_stronger_coupling(self):
        weak = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.01)
        strong = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.03)
        assert strong.iswap_gate_time_ns < weak.iswap_gate_time_ns

    def test_uncoupled_iswap_time_is_infinite(self):
        import math

        r = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=0.0)
        assert math.isinf(r.iswap_gate_time_ns)

    def test_anharmonicities_are_negative_and_near_minus_ec(self):
        r = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02)
        # transmon anharmonicity is negative and of order -Ec (= -250 MHz here).
        assert r.anharmonicity1_MHz < 0.0
        assert r.anharmonicity2_MHz < 0.0
        assert -400.0 < r.anharmonicity1_MHz < -150.0
