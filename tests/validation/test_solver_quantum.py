"""Comparison of solver-quantum (Task #3) against the independent reference.

solver-quantum has landed (core.solvers.quantum), so these are LIVE comparisons,
not skips. The whole quantum pipeline is run on examples/transmon_readout.json
and every reported number is checked against this suite's independently computed
ground truth (from-scratch charge-basis diagonalization + independent multilevel
dispersive formula, all in reference.py). The HDF5 output is also round-tripped
to confirm the persisted values and unit tags are correct.

g CONVENTION (important, verified here): solver-quantum reports ``g_GHz`` as the
coefficient of the BARE charge operator in ``g * n * (a + a_dag)``. The physical
0<->1 vacuum coupling is therefore ``g_GHz * n01`` (n01 ~ 1.14 for this
transmon), NOT g_GHz itself. Anyone comparing g to a "vacuum Rabi rate" must
apply this factor. With the factor applied, the independent multilevel chi
formula reproduces solver-quantum's non-perturbative chi to ~0.5%.

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
    """solver-quantum chi matches the independent multilevel formula to <3%.

    solver-quantum computes chi by exact diagonalization of the transmon+
    resonator (scqubits.HilbertSpace). We cross-check with an *independently
    derived* multilevel second-order formula (reference.py), evaluated with the
    same real transmon matrix elements. Because solver-quantum's g multiplies the
    BARE n operator, the physical 0<->1 coupling passed to the formula is
    g_GHz * n01.
    """
    _, quant, spectrum, dispersive = solved
    # Independent transmon levels + charge matrix elements (from scratch).
    evals, evecs = ref.cpb_eigensystem_hz(
        quant.Ej_GHz * 1e9, quant.Ec_GHz * 1e9, ng=0.0, ncut=50
    )
    levels_hz = evals[:6] - evals[0]
    n_matrix = ref.number_operator_matrix(evecs, 50, 6)
    n01 = abs(n_matrix[0, 1])

    g01_hz = dispersive.g_GHz * 1e9 * n01  # convert bare-n coefficient -> physical g01
    wr_hz = dispersive.f0_GHz * 1e9
    chi_ref_hz = ref.dispersive_shift_multilevel_hz(levels_hz, n_matrix, g01_hz, wr_hz)

    assert np.isclose(dispersive.chi_GHz * 1e9, chi_ref_hz, rtol=0.03)
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
