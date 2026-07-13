"""Headless CLI for the classical solver.

Usage::

    python -m core.solvers.classical <netlist.json> <output.h5>

No PySide6 / GUI import anywhere in this module (project-wide rule) -- this
must run standalone from the command line, per docs/task.md Gorev 2 ("GUI'siz,
komut satirindan calisabilir olmali").

The netlist may describe an RCSJ bias circuit (junction + current_source,
e.g. ``examples/rcsj_bias.json``), a readout circuit (resonator +
transmission_line + termination, e.g. ``examples/transmon_readout.json``), or
both; whichever topology is present is computed, and only a netlist with
NEITHER is an error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.netlist import NetlistError, load
from core.provenance import netlist_sha256

from .hdf5_io import write_hdf5
from .runner import (
    RCSJAnalysis,
    ReadoutAnalysis,
    run_rcsj_analysis,
    run_readout_analysis,
)
from .topology import TopologyError


def run(netlist_path: str, output_path: str) -> int:
    """Run the classical solver end-to-end: load, analyze, write.

    Args:
        netlist_path: Path to a netlist JSON file (frozen ``core.netlist``
            format).
        output_path: Path to write the HDF5 result file to (see
            :mod:`core.solvers.classical.hdf5_io` for the layout).

    Returns:
        Process exit code: 0 on success, 1 on a recognized netlist/topology
        error (message printed to stderr), 2 for an unexpected error.
    """
    try:
        netlist = load(netlist_path, validate=True)
    except (NetlistError, OSError) as exc:
        print(f"error: failed to load netlist {netlist_path!r}: {exc}", file=sys.stderr)
        return 1

    rcsj: RCSJAnalysis | None = None
    readout: ReadoutAnalysis | None = None
    rcsj_error: TopologyError | None = None
    readout_error: TopologyError | None = None

    try:
        rcsj = run_rcsj_analysis(netlist)
    except TopologyError as exc:
        rcsj_error = exc

    try:
        readout = run_readout_analysis(netlist)
    except TopologyError as exc:
        readout_error = exc

    if rcsj is None and readout is None:
        print(
            f"error: netlist {netlist_path!r} has neither an RCSJ bias topology "
            f"nor a readout topology this solver supports:\n"
            f"  RCSJ: {rcsj_error}\n"
            f"  readout: {readout_error}",
            file=sys.stderr,
        )
        return 1

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    write_hdf5(
        output_path,
        netlist_name=netlist.name,
        rcsj=rcsj,
        readout=readout,
        netlist_hash=netlist_sha256(netlist),
    )

    print(f"Classical solver: {netlist.name!r} -> {output_path}")
    if rcsj is not None:
        print(
            f"  RCSJ: Ic={rcsj.critical_current_a * 1e9:.3f} nA, "
            f"R={rcsj.resistance_ohm:.1f} ohm, C={rcsj.capacitance_f * 1e15:.3f} fF, "
            f"bias={rcsj.bias_current_a * 1e9:.3f} nA, "
            f"V_dc={rcsj.phase_dynamics.dc_voltage_v * 1e6:.4f} uV"
        )
    else:
        print(f"  RCSJ: not computed ({rcsj_error})")
    if readout is not None:
        c = readout.s21_curve
        print(
            f"  Readout: f0={c.f0_hz / 1e9:.4f} GHz, Q_int={c.q_internal:.0f}, "
            f"kappa_ext={c.kappa_ext_hz / 1e6:.4f} MHz, kappa_total={c.kappa_total_hz / 1e6:.4f} MHz"
        )
    else:
        print(f"  Readout: not computed ({readout_error})")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Argument-parsing entry point; see module docstring for usage."""
    parser = argparse.ArgumentParser(
        prog="python -m core.solvers.classical",
        description=(
            "Run the classical RCSJ / I-V / phase-dynamics / readout-S21 analysis "
            "on a JJQubit netlist."
        ),
    )
    parser.add_argument("netlist", help="Path to a netlist JSON file.")
    parser.add_argument("output", help="Path to write the HDF5 result file to.")
    args = parser.parse_args(argv)
    return run(args.netlist, args.output)


if __name__ == "__main__":
    sys.exit(main())
