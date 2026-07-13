"""Example: a transmon parameter sweep driven entirely from the scriptable API.

Demonstrates the point of ``jjqubit`` as a library (no GUI): load a netlist,
vary one element parameter across a range, run the quantum solver for each, and
tabulate the result. Here we sweep the junction critical current ``Ic`` (which
sets the Josephson energy Ej) and watch E01 and the anharmonicity track Ej/Ec.

Run from the repository root::

    python examples/sweep_transmon.py

This uses only the public API (``jjqubit.load_netlist`` / ``solve_quantum``)
and the netlist data model; it never imports the GUI.
"""

from __future__ import annotations

import copy
import pathlib
import sys

# Running `python examples/sweep_transmon.py` puts examples/ (not the repo
# root) on sys.path, so make the repo root importable before importing jjqubit.
EXAMPLES = pathlib.Path(__file__).resolve().parent
REPO_ROOT = EXAMPLES.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import jjqubit  # noqa: E402 - must follow the sys.path bootstrap above
from core.netlist.units import Quantity  # noqa: E402

BASE_NETLIST = EXAMPLES / "transmon_readout.json"


def _with_scaled_ic(netlist, junction_id: str, factor: float):
    """Return a copy of ``netlist`` with the junction's Ic scaled by ``factor``."""
    net = copy.deepcopy(netlist)
    junction = net.element_by_id(junction_id)
    if junction is None:
        raise ValueError(f"no element {junction_id!r} in netlist")
    ic = junction.params["Ic"]
    junction.params["Ic"] = Quantity(value=ic.value * factor, unit=ic.unit)
    return net


def main() -> None:
    base = jjqubit.load_netlist(str(BASE_NETLIST))

    # Find the (single) junction to sweep.
    junctions = [el for el in base.elements if el.type == "junction"]
    if not junctions:
        raise SystemExit("netlist has no junction to sweep")
    junction_id = junctions[0].id

    print(f"Sweeping junction {junction_id!r} Ic in {BASE_NETLIST.name}\n")
    header = f"{'Ic x':>6} {'Ej/Ec':>8} {'E01 (GHz)':>11} {'anharm (MHz)':>13} {'chi (MHz)':>10}"
    print(header)
    print("-" * len(header))

    for factor in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
        net = _with_scaled_ic(base, junction_id, factor)
        q = jjqubit.solve_quantum(net)
        print(
            f"{factor:>6.2f} {q.Ej_over_Ec:>8.2f} {q.E01_GHz:>11.4f} "
            f"{q.anharmonicity_GHz * 1e3:>13.2f} {q.chi_MHz:>10.4f}"
        )


if __name__ == "__main__":
    main()
