"""Tests for the ``.jjq`` project file format: netlist + metadata envelope.

Covers the acceptance criterion "project can be saved and reopened", built
directly against the frozen ``core.netlist`` contract -- no Qt/GUI required.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from core.netlist import ValidationError, load
from gui.app import (
    APP_VERSION,
    PROJECT_FORMAT,
    LastRunInfo,
    ProjectError,
    ProjectState,
    load_project,
    project_from_dict,
    project_to_dict,
    save_project,
)

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"


def _valid_netlist():
    return load(str(EXAMPLES_DIR / "transmon_readout.json"), validate=True)


# -- round trip ---------------------------------------------------------------


def test_round_trip_valid_netlist(tmp_path):
    netlist = _valid_netlist()
    state = ProjectState(netlist=netlist)

    path = tmp_path / "project.jjq"
    save_project(state, path, validate=True)
    assert path.exists()

    loaded = load_project(path, validate=True)
    assert loaded.app_version == APP_VERSION
    assert loaded.last_run is None
    # Netlist content survives the round trip byte-for-byte (as a dict).
    from core.netlist import to_dict

    assert to_dict(loaded.netlist) == to_dict(netlist)


def test_last_run_metadata_round_trips(tmp_path):
    netlist = _valid_netlist()
    last_run = LastRunInfo(
        solver="quantum",
        output_path="C:/tmp/result.h5",
        status="success",
        message="Run completed.",
        timestamp="2026-07-12T10:00:00+00:00",
    )
    state = ProjectState(netlist=netlist, last_run=last_run)

    path = tmp_path / "project.jjq"
    save_project(state, path, validate=True)
    loaded = load_project(path)

    assert loaded.last_run is not None
    assert loaded.last_run.solver == "quantum"
    assert loaded.last_run.output_path == "C:/tmp/result.h5"
    assert loaded.last_run.status == "success"
    assert loaded.last_run.message == "Run completed."
    assert loaded.last_run.timestamp == "2026-07-12T10:00:00+00:00"


def test_saved_file_embeds_frozen_netlist_schema(tmp_path):
    """The embedded 'netlist' object is exactly core.netlist's own format."""
    netlist = _valid_netlist()
    state = ProjectState(netlist=netlist)
    path = tmp_path / "project.jjq"
    save_project(state, path, validate=True)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == PROJECT_FORMAT
    assert data["netlist"]["format"] == "jjqubit-netlist"
    assert data["netlist"]["name"] == netlist.name


# -- validation behavior --------------------------------------------------------


def test_save_without_validate_allows_invalid_netlist(tmp_path):
    from core.netlist import Element, Netlist, Quantity

    invalid = Netlist(
        name="floating",
        nodes=["n1"],
        elements=[
            Element(id="C1", type="capacitor", params={"C": Quantity(1.0, "fF")})
        ],
        connections=[],  # terminals unwired: invalid, but not schema-broken
    )
    state = ProjectState(netlist=invalid)
    path = tmp_path / "wip.jjq"

    save_project(state, path)  # validate=False by default
    assert path.exists()

    # Loading without validation succeeds; with validation, it raises.
    loaded = load_project(path)
    assert loaded.netlist.name == "floating"
    with pytest.raises(ValidationError):
        load_project(path, validate=True)


def test_save_with_validate_raises_and_does_not_write(tmp_path):
    from core.netlist import Element, Netlist, Quantity

    invalid = Netlist(
        name="floating",
        elements=[
            Element(id="C1", type="capacitor", params={"C": Quantity(1.0, "fF")})
        ],
    )
    state = ProjectState(netlist=invalid)
    path = tmp_path / "should_not_exist.jjq"

    with pytest.raises(ValidationError):
        save_project(state, path, validate=True)
    assert not path.exists()


# -- malformed envelope errors --------------------------------------------------


def test_load_project_rejects_wrong_format(tmp_path):
    path = tmp_path / "bad.jjq"
    path.write_text(
        json.dumps({"format": "something-else", "netlist": {}}), encoding="utf-8"
    )
    with pytest.raises(ProjectError):
        load_project(path)


def test_load_project_rejects_missing_netlist(tmp_path):
    path = tmp_path / "bad.jjq"
    path.write_text(json.dumps({"format": PROJECT_FORMAT}), encoding="utf-8")
    with pytest.raises(ProjectError):
        load_project(path)


def test_load_project_rejects_invalid_json(tmp_path):
    path = tmp_path / "bad.jjq"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ProjectError):
        load_project(path)


def test_project_from_dict_rejects_non_dict():
    with pytest.raises(ProjectError):
        project_from_dict(["not", "a", "dict"])


def test_last_run_from_dict_rejects_non_dict():
    with pytest.raises(ProjectError):
        LastRunInfo.from_dict("nope")


def test_project_to_dict_matches_expected_envelope():
    netlist = _valid_netlist()
    state = ProjectState(netlist=netlist)
    data = project_to_dict(state)
    assert set(data) == {"format", "version", "app_version", "netlist", "last_run"}
    assert data["format"] == PROJECT_FORMAT
    assert data["last_run"] is None
