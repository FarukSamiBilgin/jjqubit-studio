"""Every netlist in examples/ must load, validate, and round-trip losslessly."""
from __future__ import annotations

import pathlib

import pytest

from core.netlist import dumps, load, loads

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.json"))


def test_examples_directory_is_not_empty():
    assert EXAMPLE_FILES, f"no example netlists found in {EXAMPLES_DIR}"


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_loads_and_validates(path):
    nl = load(path, validate=True)  # raises ValidationError if invalid
    assert nl.elements
    assert nl.connections


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_round_trips(path):
    nl = load(path)
    assert loads(dumps(nl)) == nl


def test_a_transmon_plus_resonator_example_exists():
    """The task requires at least one transmon + readout-resonator netlist."""
    found = False
    for path in EXAMPLE_FILES:
        nl = load(path, validate=True)
        types = {el.type for el in nl.elements}
        if {"junction", "capacitor", "resonator"} <= types:
            found = True
            break
    assert found, "expected an example with junction + capacitor + resonator"
