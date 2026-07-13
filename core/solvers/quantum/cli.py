"""Headless CLI for the quantum solver.

Usage::

    python -m core.solvers.quantum <netlist.json> <output.h5>

No PySide6 / GUI import anywhere in this module (project-wide rule) -- this
must run standalone from the command line, per docs/task.md Gorev 3.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.netlist import NetlistError, load
from core.provenance import netlist_sha256

from .coherence import compute_coherence
from .dispersive import compute_dispersive_shift
from .hdf5_io import write_hdf5
from .quantization import quantize_circuit
from .spectrum import compute_transmon_spectrum
from .topology import TopologyError


def run(netlist_path: str, output_path: str) -> int:
    """Run the quantum solver end-to-end: load, quantize, diagonalize, write.

    Args:
        netlist_path: Path to a netlist JSON file (frozen ``core.netlist``
            format).
        output_path: Path to write the HDF5 result file to (see
            :mod:`core.solvers.quantum.hdf5_io` for the layout).

    Returns:
        Process exit code: 0 on success, 1 on a recognized netlist/topology
        error (message printed to stderr), 2 for an unexpected error.
    """
    try:
        netlist = load(netlist_path, validate=True)
    except (NetlistError, OSError) as exc:
        # core.netlist.load() raises OSError subclasses (e.g. FileNotFoundError)
        # directly for filesystem problems, and NetlistError subclasses for
        # schema/unit/validation problems; both are "bad input", not a solver
        # bug, so both should exit cleanly rather than propagate a traceback.
        print(f"error: failed to load netlist {netlist_path!r}: {exc}", file=sys.stderr)
        return 1

    try:
        quantization = quantize_circuit(netlist)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        dispersive = compute_dispersive_shift(quantization, spectrum)
        coherence = compute_coherence(quantization, dispersive=dispersive)
    except TopologyError as exc:
        print(f"error: unsupported netlist topology: {exc}", file=sys.stderr)
        return 1

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    write_hdf5(
        output_path,
        netlist_name=netlist.name,
        quantization=quantization,
        spectrum=spectrum,
        dispersive=dispersive,
        coherence=coherence,
        netlist_hash=netlist_sha256(netlist),
    )

    print(f"Quantum solver: {netlist.name!r} -> {output_path}")
    print(
        f"  Ej = {quantization.Ej_GHz:.4f} GHz, Ec = {quantization.Ec_GHz:.4f} GHz, "
        f"Ej/Ec = {quantization.Ej_over_Ec:.2f}"
    )
    print(
        f"  E01 = {spectrum.E01_GHz:.4f} GHz, anharmonicity = {spectrum.anharmonicity_GHz:.4f} GHz"
    )
    print(
        f"  g = {dispersive.g_GHz * 1e3:.4f} MHz, chi = {dispersive.chi_GHz * 1e3:.4f} MHz, "
        f"Delta = {dispersive.Delta_GHz:.4f} GHz"
    )
    print(
        f"  T1 = {coherence.T1_us:.2f} us, T2 = {coherence.T2_us:.2f} us "
        f"(at {coherence.temperature_K * 1e3:.0f} mK)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Argument-parsing entry point; see module docstring for usage."""
    parser = argparse.ArgumentParser(
        prog="python -m core.solvers.quantum",
        description="Quantize a JJQubit netlist and compute its transmon + dispersive spectrum.",
    )
    parser.add_argument("netlist", help="Path to a netlist JSON file.")
    parser.add_argument("output", help="Path to write the HDF5 result file to.")
    args = parser.parse_args(argv)
    return run(args.netlist, args.output)


if __name__ == "__main__":
    sys.exit(main())
