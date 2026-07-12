"""Tests for core.solvers.classical.hdf5_io: HDF5 result layout."""
from __future__ import annotations

import h5py
import pytest

from core.solvers.classical.hdf5_io import FORMAT, FORMAT_VERSION, write_hdf5
from core.solvers.classical.runner import run_readout_analysis, run_rcsj_analysis


class TestWriteHdf5:
    def test_rcsj_only(self, tmp_path, rcsj_netlist):
        rcsj = run_rcsj_analysis(rcsj_netlist)
        out_path = tmp_path / "rcsj.h5"
        write_hdf5(out_path, netlist_name=rcsj_netlist.name, rcsj=rcsj, readout=None)

        with h5py.File(out_path, "r") as f:
            assert f.attrs["format"] == FORMAT
            assert f.attrs["version"] == FORMAT_VERSION
            assert f.attrs["netlist_name"] == rcsj_netlist.name
            assert "rcsj" in f
            assert "readout" not in f
            assert f["rcsj"].attrs["Ic_nA"] == pytest.approx(20.0)
            assert f["rcsj"].attrs["inductor_ids"] == "L1"
            assert f["rcsj/phase_dynamics/voltage_uV"].attrs["unit"] == "uV"
            assert f["rcsj/iv_curve/bias_current_up_nA"].attrs["unit"] == "nA"
            assert "rcsj_inductor_note" in f["assumptions"].attrs

    def test_readout_only(self, tmp_path, transmon_netlist):
        readout = run_readout_analysis(transmon_netlist)
        out_path = tmp_path / "readout.h5"
        write_hdf5(out_path, netlist_name=transmon_netlist.name, rcsj=None, readout=readout)

        with h5py.File(out_path, "r") as f:
            assert "readout" in f
            assert "rcsj" not in f
            assert f["readout"].attrs["f0_GHz"] == pytest.approx(7.2)
            assert f["readout/frequency_GHz"].attrs["unit"] == "GHz"
            assert f["readout/s21_real"].shape == f["readout/s21_imag"].shape
            assert "resonator_impedance_ohm" in f["assumptions"].attrs

    def test_neither_raises(self, tmp_path):
        with pytest.raises(ValueError):
            write_hdf5(tmp_path / "empty.h5", netlist_name="x", rcsj=None, readout=None)

    def test_creates_readable_complex_s21_from_real_imag(self, tmp_path, transmon_netlist):
        readout = run_readout_analysis(transmon_netlist)
        out_path = tmp_path / "readout.h5"
        write_hdf5(out_path, netlist_name=transmon_netlist.name, rcsj=None, readout=readout)
        with h5py.File(out_path, "r") as f:
            real = f["readout/s21_real"][:]
            imag = f["readout/s21_imag"][:]
            mag_db = f["readout/s21_mag_db"][:]
            import numpy as np

            recomputed_db = 20.0 * np.log10(np.hypot(real, imag))
            assert np.allclose(recomputed_db, mag_db, atol=1e-9)
