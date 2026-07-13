"""Tests for run provenance (core.provenance) and its integration.

Covers the stable netlist hash, the provenance attribute set, the HDF5
round-trip, that both solver result files carry a /provenance group, and that
the waveform reader refuses a file from a newer major format version.
"""

from __future__ import annotations

import copy

import h5py
import pytest
from conftest import EXAMPLES_DIR
from core.netlist import load
from core.netlist.units import Quantity
from core.provenance import (
    PROVENANCE_GROUP,
    collect_provenance,
    netlist_sha256,
    read_provenance,
    write_provenance,
)

TRANSMON = str(EXAMPLES_DIR / "transmon_readout.json")
RCSJ = str(EXAMPLES_DIR / "rcsj_bias.json")


class TestNetlistHash:
    def test_is_64_hex_chars(self):
        digest = netlist_sha256(load(TRANSMON, validate=True))
        assert len(digest) == 64
        int(digest, 16)  # parses as hex

    def test_is_stable_across_loads(self):
        a = netlist_sha256(load(TRANSMON, validate=True))
        b = netlist_sha256(load(TRANSMON, validate=True))
        assert a == b

    def test_changes_when_a_parameter_changes(self):
        net = load(TRANSMON, validate=True)
        before = netlist_sha256(net)
        junction = next(el for el in net.elements if el.type == "junction")
        ic = junction.params["Ic"]
        mutated = copy.deepcopy(net)
        mut_junction = next(el for el in mutated.elements if el.type == "junction")
        mut_junction.params["Ic"] = Quantity(value=ic.value * 1.001, unit=ic.unit)
        assert netlist_sha256(mutated) != before


class TestCollectProvenance:
    def test_has_core_keys(self):
        attrs = collect_provenance(generated_by="core.solvers.quantum")
        for key in (
            "provenance_version",
            "generated_by",
            "created_at_utc",
            "python_version",
            "platform",
        ):
            assert key in attrs
        assert attrs["generated_by"] == "core.solvers.quantum"

    def test_records_library_versions(self):
        attrs = collect_provenance(
            generated_by="x", libraries=("numpy", "definitely-not-installed-xyz")
        )
        assert attrs["lib_numpy"] != "unknown"
        assert attrs["lib_definitely-not-installed-xyz"] == "unknown"

    def test_extra_is_merged(self):
        attrs = collect_provenance(generated_by="x", extra={"app_version": "9.9"})
        assert attrs["app_version"] == "9.9"


class TestHdf5RoundTrip:
    def test_write_then_read(self, tmp_path):
        out = tmp_path / "p.h5"
        with h5py.File(out, "w") as f:
            write_provenance(
                f,
                generated_by="core.solvers.quantum",
                netlist_hash="deadbeef",
                libraries=("numpy",),
            )
        prov = read_provenance_file(out)
        assert prov["generated_by"] == "core.solvers.quantum"
        assert prov["netlist_sha256"] == "deadbeef"
        assert prov["lib_numpy"] != "unknown"

    def test_read_missing_group_returns_empty(self, tmp_path):
        out = tmp_path / "empty.h5"
        with h5py.File(out, "w") as f:
            f.attrs["format"] = "whatever"
        assert read_provenance_file(out) == {}


def read_provenance_file(path):
    """Helper: open a file and read its provenance group."""
    with h5py.File(path, "r") as f:
        return read_provenance(f)


class TestSolverIntegration:
    def test_quantum_result_carries_provenance(self, tmp_path):
        import jjqubit
        from core.solvers.quantum.hdf5_io import FORMAT_VERSION

        out = tmp_path / "q.h5"
        jjqubit.solve_quantum(TRANSMON).write_hdf5(out)
        with h5py.File(out, "r") as f:
            assert f.attrs["version"] == FORMAT_VERSION
            assert PROVENANCE_GROUP in f
            prov = read_provenance(f)
        assert prov["generated_by"] == "core.solvers.quantum"
        assert len(prov["netlist_sha256"]) == 64
        assert prov["lib_scqubits"] != "unknown"

    def test_classical_result_carries_provenance(self, tmp_path):
        import jjqubit
        from core.solvers.classical.hdf5_io import FORMAT_VERSION

        out = tmp_path / "c.h5"
        jjqubit.solve_classical(RCSJ).write_hdf5(out)
        with h5py.File(out, "r") as f:
            assert f.attrs["version"] == FORMAT_VERSION
            assert PROVENANCE_GROUP in f
            prov = read_provenance(f)
        assert prov["generated_by"] == "core.solvers.classical"
        assert len(prov["netlist_sha256"]) == 64


class TestReaderVersionGate:
    def test_refuses_newer_major_version(self, tmp_path):
        from gui.waveform.hdf5_reader import load_quantum_result

        bad = tmp_path / "future.h5"
        with h5py.File(bad, "w") as f:
            f.attrs["format"] = "jjqubit-quantum-result"
            f.attrs["version"] = "2.0"
            f.attrs["netlist_name"] = "x"
            f.create_group("qubit")
        with pytest.raises(ValueError, match="newer than this viewer"):
            load_quantum_result(bad)

    def test_accepts_missing_version(self, tmp_path):
        # A pre-versioning file (no version attr) must not be rejected outright;
        # it will fail later on missing groups, not on the version gate.
        from gui.waveform.hdf5_reader import _check_version

        legacy = tmp_path / "legacy.h5"
        with h5py.File(legacy, "w") as f:
            f.attrs["format"] = "jjqubit-quantum-result"
        with h5py.File(legacy, "r") as f:
            _check_version(f, legacy)  # must not raise
