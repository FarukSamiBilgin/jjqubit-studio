"""Tests for the HDF5 result writer (core.solvers.quantum.hdf5_io).

Verifies the layout documented in hdf5_io.py's module docstring (and shared
with waveform-ui/main): group names, dataset shape/unit attrs, and that every
computed quantity round-trips into the file unchanged.
"""
from __future__ import annotations

import h5py
import pytest

from core.solvers.quantum.dispersive import compute_dispersive_shift
from core.solvers.quantum.hdf5_io import FORMAT, FORMAT_VERSION, write_hdf5
from core.solvers.quantum.quantization import quantize_circuit
from core.solvers.quantum.spectrum import compute_transmon_spectrum


@pytest.fixture
def written_file(tmp_path, transmon_netlist):
    quantization = quantize_circuit(transmon_netlist)
    spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
    dispersive = compute_dispersive_shift(quantization, spectrum)
    out_path = tmp_path / "result.h5"
    write_hdf5(
        out_path,
        netlist_name=transmon_netlist.name,
        quantization=quantization,
        spectrum=spectrum,
        dispersive=dispersive,
    )
    return out_path, quantization, spectrum, dispersive


class TestHdf5Layout:
    def test_root_attrs(self, written_file):
        path, _, _, _ = written_file
        with h5py.File(path, "r") as f:
            assert f.attrs["format"] == FORMAT
            assert f.attrs["version"] == FORMAT_VERSION
            assert f.attrs["generated_by"] == "core.solvers.quantum"
            assert f.attrs["netlist_name"] == "Transmon + readout resonator"

    def test_groups_present(self, written_file):
        path, _, _, _ = written_file
        with h5py.File(path, "r") as f:
            assert set(f.keys()) == {"qubit", "resonator", "coupling", "assumptions"}

    def test_qubit_group(self, written_file):
        path, quantization, spectrum, _ = written_file
        with h5py.File(path, "r") as f:
            qubit = f["qubit"]
            assert qubit.attrs["Ej_GHz"] == pytest.approx(quantization.Ej_GHz)
            assert qubit.attrs["Ec_GHz"] == pytest.approx(quantization.Ec_GHz)
            assert qubit.attrs["Ej_over_Ec"] == pytest.approx(quantization.Ej_over_Ec)
            assert qubit.attrs["E01_GHz"] == pytest.approx(spectrum.E01_GHz)
            assert qubit.attrs["anharmonicity_GHz"] == pytest.approx(spectrum.anharmonicity_GHz)
            assert qubit.attrs["junction_id"] == "J1"
            assert qubit.attrs["island_node"] == "q"

            levels_ds = qubit["energy_levels"]
            assert levels_ds.shape == spectrum.energy_levels_GHz.shape
            assert list(levels_ds[:]) == pytest.approx(list(spectrum.energy_levels_GHz))
            assert levels_ds.attrs["unit"] == "GHz"
            assert "description" in levels_ds.attrs

    def test_resonator_group(self, written_file):
        path, quantization, _, dispersive = written_file
        with h5py.File(path, "r") as f:
            resonator = f["resonator"]
            assert resonator.attrs["f0_GHz"] == pytest.approx(dispersive.f0_GHz)
            assert resonator.attrs["Q"] == pytest.approx(8000.0)
            assert resonator.attrs["kappa_GHz"] == pytest.approx(dispersive.kappa_GHz)
            assert resonator.attrs["resonator_id"] == "RES1"
            assert resonator.attrs["active_node"] == "r"

    def test_coupling_group(self, written_file):
        path, quantization, _, dispersive = written_file
        with h5py.File(path, "r") as f:
            coupling = f["coupling"]
            assert coupling.attrs["g_GHz"] == pytest.approx(dispersive.g_GHz)
            assert coupling.attrs["chi_GHz"] == pytest.approx(dispersive.chi_GHz)
            assert coupling.attrs["Delta_GHz"] == pytest.approx(dispersive.Delta_GHz)
            assert coupling.attrs["beta"] == pytest.approx(dispersive.beta)
            assert coupling.attrs["Cg_fF"] == pytest.approx(quantization.Cg_fF)

    def test_assumptions_group(self, written_file):
        path, _, _, dispersive = written_file
        with h5py.File(path, "r") as f:
            assumptions = f["assumptions"]
            assert assumptions.attrs["resonator_Z0_ohm"] == pytest.approx(
                dispersive.resonator_Z0_ohm
            )
            assert "note" in assumptions.attrs
            assert "f0 and Q" in assumptions.attrs["note"]

    def test_creates_parent_less_file_at_exact_path(self, tmp_path, transmon_netlist):
        quantization = quantize_circuit(transmon_netlist)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        dispersive = compute_dispersive_shift(quantization, spectrum)
        out_path = tmp_path / "nested_ok.h5"
        write_hdf5(
            out_path,
            netlist_name=transmon_netlist.name,
            quantization=quantization,
            spectrum=spectrum,
            dispersive=dispersive,
        )
        assert out_path.exists()
