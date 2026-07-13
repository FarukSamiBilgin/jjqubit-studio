"""Example: sweep one qubit through the other and trace the avoided crossing.

The defining experiment for two coupled qubits: detune qubit 2 across qubit 1's
frequency (here by scaling its junction critical current) and watch the
single-excitation splitting. Far from resonance the splitting is just the bare
detuning; at resonance it bottoms out at 2J -- the avoided crossing.

Run from the repository root::

    python examples/sweep_coupling.py

Uses only the public API and the netlist data model; never imports the GUI.
"""

from __future__ import annotations

import copy
import pathlib
import sys

EXAMPLES = pathlib.Path(__file__).resolve().parent
REPO_ROOT = EXAMPLES.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import jjqubit  # noqa: E402 - must follow the sys.path bootstrap above
from core.netlist.units import Quantity  # noqa: E402

BASE_NETLIST = EXAMPLES / "two_transmon.json"


def _with_scaled_ic(netlist, junction_id: str, factor: float):
    """Return a copy of ``netlist`` with one junction's Ic scaled by ``factor``."""
    net = copy.deepcopy(netlist)
    junction = net.element_by_id(junction_id)
    if junction is None:
        raise ValueError(f"no element {junction_id!r} in netlist")
    ic = junction.params["Ic"]
    junction.params["Ic"] = Quantity(value=ic.value * factor, unit=ic.unit)
    return net


def main() -> None:
    base = jjqubit.load_netlist(str(BASE_NETLIST))

    print(f"Tuning qubit 2 (J2) through qubit 1 in {BASE_NETLIST.name}\n")
    header = (
        f"{'J2 Ic x':>8} {'w1 (GHz)':>9} {'w2 (GHz)':>9} "
        f"{'detuning (MHz)':>15} {'splitting (MHz)':>16} {'J (MHz)':>9}"
    )
    print(header)
    print("-" * len(header))

    for factor in (0.85, 0.92, 0.96, 1.0, 1.04, 1.08, 1.15):
        net = _with_scaled_ic(base, "J2", factor)
        r = jjqubit.solve_two_qubit(net)
        print(
            f"{factor:>8.2f} {r.omega1_GHz:>9.4f} {r.omega2_GHz:>9.4f} "
            f"{r.detuning_GHz * 1e3:>15.1f} "
            f"{r.one_excitation_splitting_GHz * 1e3:>16.1f} {r.J_GHz * 1e3:>9.2f}"
        )

    print(
        "\nThe splitting is minimal at resonance (detuning ~ 0), where it "
        "equals 2J -- the avoided crossing."
    )


if __name__ == "__main__":
    main()
