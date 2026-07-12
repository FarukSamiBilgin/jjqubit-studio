"""Tests for the standalone CLI (core.solvers.quantum.cli / __main__).

Confirms the solver runs headlessly from the command line against a real
netlist file, per docs/task.md Gorev 3 ("GUI'siz, komut satirindan
calisabilir olmali") and the Definition of Done ("CLI works standalone
against examples/transmon_readout.json").
"""
from __future__ import annotations

import subprocess
import sys

import h5py
import pytest

from core.solvers.quantum.cli import main


class TestCliInProcess:
    def test_runs_end_to_end_on_reference_example(self, tmp_path, examples_dir):
        netlist_path = examples_dir / "transmon_readout.json"
        out_path = tmp_path / "out.h5"
        exit_code = main([str(netlist_path), str(out_path)])
        assert exit_code == 0
        assert out_path.exists()
        with h5py.File(out_path, "r") as f:
            assert f.attrs["format"] == "jjqubit-quantum-result"
            assert f["qubit"].attrs["Ej_over_Ec"] > 1.0

    def test_missing_netlist_file_returns_nonzero_without_raising(self, tmp_path):
        exit_code = main([str(tmp_path / "does_not_exist.json"), str(tmp_path / "out.h5")])
        assert exit_code != 0
        assert not (tmp_path / "out.h5").exists()

    def test_unsupported_topology_returns_nonzero_without_raising(self, tmp_path, examples_dir):
        # rcsj_bias.json has a junction but no resonator: unsupported by
        # this MVP solver, and must fail cleanly (not raise/traceback).
        netlist_path = examples_dir / "rcsj_bias.json"
        out_path = tmp_path / "out.h5"
        exit_code = main([str(netlist_path), str(out_path)])
        assert exit_code != 0
        assert not out_path.exists()

    def test_creates_missing_output_directory(self, tmp_path, examples_dir):
        netlist_path = examples_dir / "transmon_readout.json"
        out_path = tmp_path / "nested" / "dir" / "out.h5"
        exit_code = main([str(netlist_path), str(out_path)])
        assert exit_code == 0
        assert out_path.exists()


class TestCliAsSubprocess:
    """One true end-to-end check: invoke exactly as documented in docs/task.md."""

    def test_python_dash_m_invocation(self, tmp_path, examples_dir):
        netlist_path = examples_dir / "transmon_readout.json"
        out_path = tmp_path / "subprocess_out.h5"
        result = subprocess.run(
            [sys.executable, "-m", "core.solvers.quantum", str(netlist_path), str(out_path)],
            cwd=examples_dir.parent,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        assert out_path.exists()
        assert "Ej" in result.stdout
        assert "chi" in result.stdout
