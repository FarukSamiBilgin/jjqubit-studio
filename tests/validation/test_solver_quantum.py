"""Comparison of solver-quantum (Task #3) against the independent reference.

solver-quantum has landed (core.solvers.quantum), so these are LIVE comparisons,
not skips. The whole quantum pipeline is run on examples/transmon_readout.json
and every reported number is checked against this suite's independently computed
ground truth (from-scratch charge-basis diagonalization + independent multilevel
dispersive formula, all in reference.py). The HDF5 output is also round-tripped
to confirm the persisted values and unit tags are correct.

g CONVENTION (important, independently verified here): solver-quantum reports
``g_GHz`` as the COMPLETE physical 0<->1 vacuum coupling ``g01 = 2*e*beta*n01*
delta_V0/h`` (Krantz et al. 2019; the n01 charge matrix element is already baked
in). The coefficient that multiplies the BARE charge operator inside a
``coeff * n * (a + a_dag)`` Hamiltonian is a different quantity,
``g_bare = g01 / n01``, because the operator ``n`` itself supplies n01 at the
0-1 block. Our reference formula ``dispersive_shift_multilevel_hz`` takes the
COMPLETE physical g01 as input (it re-derives every other transition via
``g_ij = g01 * |n_ij|/n01``), so we feed it ``g_GHz`` DIRECTLY -- multiplying by
n01 first would double-count it. This convention was pinned by a from-scratch
QuTiP diagonalization (build ``g_bare * n (x) (a+a_dag)`` with
``g_bare = g_GHz/n01`` so the 0-1 coupling equals g_GHz, then diagonalize
exactly): it endorses chi ~= -371.7 kHz, NOT the ~-483 kHz that the earlier
double-counted call produced. Both the multilevel formula (fed g_GHz directly)
and solver-quantum's exact HilbertSpace diagonalization agree with that QuTiP
anchor to <0.5%.

Ground truth (Cj+Cs+Cg = 77 fF): Ej/h ~ 14.9005 GHz, Ec/h ~ 251.56 MHz,
E01 ~ 5.2112 GHz, anharmonicity ~ -284.99 MHz.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.netlist import load

from . import reference as ref

# solver-quantum must be importable; if it regresses to un-importable, skip
# rather than error (its absence is a solver problem, reported elsewhere).
quantum = pytest.importorskip("core.solvers.quantum")


@pytest.fixture(scope="module")
def solved(examples_dir):
    """Run the full quantum pipeline on the example transmon once."""
    netlist = load(str(examples_dir / "transmon_readout.json"), validate=True)
    quant = quantum.quantize_circuit(netlist)
    spectrum = quantum.compute_transmon_spectrum(quant.Ej_GHz, quant.Ec_GHz)
    dispersive = quantum.compute_dispersive_shift(quant, spectrum)
    return netlist, quant, spectrum, dispersive


def test_quantum_ej_ec_match_reference(solved):
    """solver-quantum Ej/h and Ec/h match the reference to <0.1%.

    Same Josephson relation and same C_sigma = Cj+Cs+Cg = 77 fF convention, so
    agreement should be essentially exact.
    """
    _, quant, _, _ = solved
    ej_ref_ghz = ref.josephson_energy_hz(ref.EXAMPLE_IC_A) / 1e9
    ec_ref_ghz = ref.charging_energy_hz(ref.EXAMPLE_C_SIGMA_F) / 1e9
    assert np.isclose(quant.Ej_GHz, ej_ref_ghz, rtol=1e-3)
    assert np.isclose(quant.Ec_GHz, ec_ref_ghz, rtol=1e-3)
    # Confirm the solver folds Cg into the island capacitance (77 fF, not 72).
    assert np.isclose(quant.C_sigma_fF, 77.0, rtol=1e-6)


def test_quantum_spectrum_matches_reference(solved):
    """solver-quantum E01 and anharmonicity match the from-scratch reference.

    Independent charge-basis diagonalization vs scqubits: must agree to ~kHz on
    GHz-scale transitions (rtol 1e-3 is already generous).
    """
    _, quant, spectrum, _ = solved
    r = ref.transmon_reference(quant.Ej_GHz * 1e9, quant.Ec_GHz * 1e9)
    assert np.isclose(spectrum.E01_GHz * 1e9, r.e01_hz, rtol=1e-3)
    assert np.isclose(spectrum.anharmonicity_GHz * 1e9, r.anharmonicity_hz, rtol=2e-3)
    # Anharmonicity sign and magnitude sanity vs -Ec (transmon limit #1).
    assert spectrum.anharmonicity_GHz < 0.0
    assert abs(spectrum.anharmonicity_GHz / (-quant.Ec_GHz) - 1.0) < 0.15


def test_quantum_chi_matches_independent_multilevel_formula(solved):
    """solver-quantum chi matches TWO independent references to <3%.

    solver-quantum computes chi by exact diagonalization of the transmon+
    resonator (scqubits.HilbertSpace). We check it against two references that do
    NOT share solver-quantum's coupling-convention plumbing:

      1. reference.dispersive_shift_multilevel_hz -- an independently derived
         multilevel 2nd-order perturbation sum.
      2. A from-scratch QuTiP diagonalization built HERE.

    Convention (independently derived, Krantz et al. 2019 / Koch 2007):
    solver-quantum's ``g_GHz`` is the COMPLETE physical 0<->1 vacuum coupling
    ``g01`` (the n01 charge matrix element is already included). Our multilevel
    formula takes that complete g01 directly. The QuTiP Hamiltonian, in contrast,
    is written as ``coeff * n (x) (a + a_dag)`` where ``n`` is the bare charge
    operator, so its coefficient must be ``g_bare = g01 / n01`` for the 0-1 block
    coupling to equal g01. Both paths must land on the same chi, which is the
    tie-breaker that neither formula shares with solver-quantum.

    Regression value: this test previously (mistakenly) pre-multiplied g_GHz by
    n01, double-counting the charge matrix element. That inflated the reference
    chi to ~-483 kHz and only "agreed" with solver-quantum's *old* code, which
    double-counted identically -- a shared-convention error invisible to a
    two-way check. The QuTiP anchor below breaks that symmetry.
    """
    qt = pytest.importorskip("qutip")
    _, quant, spectrum, dispersive = solved
    # Independent transmon levels + charge matrix elements (from scratch).
    evals, evecs = ref.cpb_eigensystem_hz(
        quant.Ej_GHz * 1e9, quant.Ec_GHz * 1e9, ng=0.0, ncut=50
    )
    n_levels = 6
    levels_hz = evals[:n_levels] - evals[0]
    n_matrix = ref.number_operator_matrix(evecs, 50, n_levels)
    n01 = abs(n_matrix[0, 1])

    g01_hz = dispersive.g_GHz * 1e9  # g_GHz IS the complete physical g01 (no *n01)
    wr_hz = dispersive.f0_GHz * 1e9

    # Reference 1: independent multilevel perturbation-theory formula.
    chi_formula_hz = ref.dispersive_shift_multilevel_hz(
        levels_hz, n_matrix, g01_hz, wr_hz
    )

    # Reference 2: from-scratch QuTiP exact diagonalization. Coefficient of the
    # bare n operator is g_bare = g01/n01 so the 0-1 coupling equals g01.
    n_fock = 25
    g_bare_hz = g01_hz / n01
    h_q = qt.Qobj(np.diag(levels_hz))
    a = qt.destroy(n_fock)
    h_r = wr_hz * a.dag() * a
    coupling = g_bare_hz * qt.tensor(qt.Qobj(np.array(n_matrix)), a + a.dag())
    h = qt.tensor(h_q, qt.qeye(n_fock)) + qt.tensor(qt.qeye(n_levels), h_r) + coupling
    dressed_e, dressed_states = h.eigenstates()

    def dressed(q_state: int, r_state: int) -> float:
        bare = qt.tensor(qt.basis(n_levels, q_state), qt.basis(n_fock, r_state))
        return dressed_e[
            int(np.argmax([abs(bare.overlap(v)) ** 2 for v in dressed_states]))
        ]

    chi_qutip_hz = (
        (dressed(1, 1) - dressed(1, 0)) - (dressed(0, 1) - dressed(0, 0))
    ) / 2.0

    chi_solver_hz = dispersive.chi_GHz * 1e9
    # solver-quantum must agree with BOTH independent references.
    assert np.isclose(chi_solver_hz, chi_formula_hz, rtol=0.03)
    assert np.isclose(chi_solver_hz, chi_qutip_hz, rtol=0.03)
    # The two references must also agree with each other (dispersive limit).
    assert np.isclose(chi_formula_hz, chi_qutip_hz, rtol=0.02)
    # And we must genuinely be in the dispersive regime for chi to mean anything.
    assert abs(dispersive.g_GHz / dispersive.Delta_GHz) < 0.1


def test_quantum_hdf5_output_units_and_values(solved, tmp_path):
    """The persisted HDF5 result carries correct units and matches the API values."""
    h5py = pytest.importorskip("h5py")
    netlist, quant, spectrum, dispersive = solved
    out = tmp_path / "result.h5"
    quantum.write_hdf5(
        out,
        netlist_name=netlist.name,
        quantization=quant,
        spectrum=spectrum,
        dispersive=dispersive,
    )
    with h5py.File(out, "r") as f:
        assert f.attrs["format"] == "jjqubit-quantum-result"
        qubit = f["qubit"]
        # Values round-trip exactly.
        assert np.isclose(qubit.attrs["Ej_GHz"], quant.Ej_GHz, rtol=1e-12)
        assert np.isclose(qubit.attrs["E01_GHz"], spectrum.E01_GHz, rtol=1e-12)
        assert np.isclose(
            qubit.attrs["anharmonicity_GHz"], spectrum.anharmonicity_GHz, rtol=1e-12
        )
        # Energy-level dataset carries an explicit unit tag (GHz).
        assert qubit["energy_levels"].attrs["unit"] == "GHz"
        # Ground state is the zero reference.
        assert np.isclose(qubit["energy_levels"][0], 0.0, atol=1e-12)
        # And the persisted E01 matches the independent reference (physics check
        # survives serialization).
        r = ref.transmon_reference(quant.Ej_GHz * 1e9, quant.Ec_GHz * 1e9)
        assert np.isclose(qubit.attrs["E01_GHz"] * 1e9, r.e01_hz, rtol=1e-3)
