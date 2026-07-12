"""Tests for the standalone CLI (core.solvers.classical.cli / __main__).

Confirms the solver runs headlessly from the command line against both
bundled example netlists, per docs/task.md Gorev 2 ("GUI'siz, komut
satirindan calisabilir olmali") and the Definition of Done.
"""
from __future__ import annotations

import subprocess
import sys

import h5py
import pytest

from core.solvers.classical.cli import main


class TestCliInProcess:
    def test_runs_end_to_end_on_rcsj_example(self, tmp_path, examples_dir):
        netlist_path = examples_dir / "rcsj_bias.json"
        out_path = tmp_path / "rcsj_out.h5"
        exit_code = main([str(netlist_path), str(out_path)])
        assert exit_code == 0
        assert out_path.exists()
        with h5py.File(out_path, "r") as f:
            assert f.attrs["format"] == "jjqubit-classical-result"
            assert "rcsj" in f
            assert "readout" not in f

    def test_runs_end_to_end_on_readout_example(self, tmp_path, examples_dir):
        netlist_path = examples_dir / "transmon_readout.json"
        out_path = tmp_path / "readout_out.h5"
        exit_code = main([str(netlist_path), str(out_path)])
        assert exit_code == 0
        assert out_path.exists()
        with h5py.File(out_path, "r") as f:
            assert "readout" in f
            assert "rcsj" not in f
            assert f["readout"].attrs["f0_GHz"] == pytest.approx(7.2)

    def test_missing_netlist_file_returns_nonzero_without_raising(self, tmp_path):
        exit_code = main([str(tmp_path / "does_not_exist.json"), str(tmp_path / "out.h5")])
        assert exit_code != 0
        assert not (tmp_path / "out.h5").exists()

    def test_creates_missing_output_directory(self, tmp_path, examples_dir):
        netlist_path = examples_dir / "rcsj_bias.json"
        out_path = tmp_path / "nested" / "dir" / "out.h5"
        exit_code = main([str(netlist_path), str(out_path)])
        assert exit_code == 0
        assert out_path.exists()


class TestCliAsSubprocess:
    """One true end-to-end check: invoke exactly as documented in docs/task.md."""

    def test_python_dash_m_invocation_rcsj(self, tmp_path, examples_dir):
        netlist_path = examples_dir / "rcsj_bias.json"
        out_path = tmp_path / "subprocess_rcsj.h5"
        result = subprocess.run(
            [sys.executable, "-m", "core.solvers.classical", str(netlist_path), str(out_path)],
            cwd=examples_dir.parent,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert out_path.exists()
        assert "RCSJ" in result.stdout

    def test_python_dash_m_invocation_readout(self, tmp_path, examples_dir):
        netlist_path = examples_dir / "transmon_readout.json"
        out_path = tmp_path / "subprocess_readout.h5"
        result = subprocess.run(
            [sys.executable, "-m", "core.solvers.classical", str(netlist_path), str(out_path)],
            cwd=examples_dir.parent,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert out_path.exists()
        assert "Readout" in result.stdout
