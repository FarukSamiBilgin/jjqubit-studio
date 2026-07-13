"""Example: tune a flux-tunable (squid) transmon by sweeping external flux.

The whole point of a SQUID transmon is that its qubit frequency is tunable in
situ via an external magnetic flux. This sweeps the ``flux`` parameter of the
``squid`` element from 0 to half a flux quantum and tabulates how Ej, E01 and
the anharmonicity move -- the classic transmon "flux arc".

Run from the repository root::

    python examples/sweep_flux.py

Uses only the public API and the netlist data model; never imports the GUI.
"""

from __future__ import annotations

import copy
import pathlib
import sys
import warnings

EXAMPLES = pathlib.Path(__file__).resolve().parent
REPO_ROOT = EXAMPLES.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import jjqubit  # noqa: E402 - must follow the sys.path bootstrap above
from core.netlist.units import Quantity  # noqa: E402
from core.solvers.quantum.dispersive import DispersiveRegimeWarning  # noqa: E402

BASE_NETLIST = EXAMPLES / "tunable_transmon.json"


def _with_flux(netlist, squid_id: str, flux: float):
    """Return a copy of ``netlist`` with the squid's external flux set to ``flux``."""
    net = copy.deepcopy(netlist)
    squid = net.element_by_id(squid_id)
    if squid is None:
        raise ValueError(f"no element {squid_id!r} in netlist")
    squid.params["flux"] = Quantity(value=flux, unit="")
    return net


def main() -> None:
    base = jjqubit.load_netlist(str(BASE_NETLIST))

    squids = [el for el in base.elements if el.type == "squid"]
    if not squids:
        raise SystemExit("netlist has no squid to tune")
    squid_id = squids[0].id

    print(f"Sweeping external flux of {squid_id!r} in {BASE_NETLIST.name}\n")
    header = (
        f"{'Phi/Phi0':>9} {'Ej (GHz)':>9} {'Ej/Ec':>8} {'E01 (GHz)':>11} "
        f"{'anharm (MHz)':>13}"
    )
    print(header)
    print("-" * len(header))

    for flux in (0.0, 0.1, 0.2, 0.3, 0.4, 0.45):
        net = _with_flux(base, squid_id, flux)
        # Near half-flux Ej -> 0 (deep CPB), where the qubit crosses the
        # resonator and leaves the dispersive regime; silence that warning here.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DispersiveRegimeWarning)
            q = jjqubit.solve_quantum(net)
        print(
            f"{flux:>9.2f} {q.Ej_GHz:>9.3f} {q.Ej_over_Ec:>8.1f} "
            f"{q.E01_GHz:>11.4f} {q.anharmonicity_GHz * 1e3:>13.2f}"
        )


if __name__ == "__main__":
    main()
