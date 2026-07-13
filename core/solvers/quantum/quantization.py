"""Circuit quantization: Ej, Ec and the qubit-resonator coupling capacitance.

Physical formulas used (SI units internally; results reported in GHz/fF, the
project convention -- see CLAUDE.md's unit rule):

* Josephson energy from the critical current (standard Josephson relation)::

      E_J = (Phi_0 / (2*pi)) * I_c = (hbar / (2e)) * I_c        [Joules]

  where ``Phi_0 = h / (2e)`` is the magnetic flux quantum. Reported in
  frequency units (``E_J / h``, GHz), matching the convention scqubits uses
  throughout (see docs/task.md, Gorev 3: "Ej ... Josephson iliskisi").

* Charging energy from the TOTAL capacitance seen at the junction's island
  node (junction self-capacitance + every shunt/coupling capacitor wired to
  that node -- derived from netlist topology via
  :func:`core.solvers.quantum.topology.extract_qubit_topology`, never
  hardcoded)::

      E_C = e ^ 2 / (2 * C_sigma)[Joules]

  Reported as ``E_C / h`` in GHz.

This module does NOT compute a capacitance matrix from geometry -- per
CLAUDE.md's "Yapmayacaklarimiz" #1, the capacitance matrix (or here, its
topological stand-in: capacitances already present as netlist parameters)
is an INPUT the solver only reads.

Sign/units convention is verified against the bundled
``examples/transmon_readout.json`` reference circuit: Ic=30nA, C_sigma=77fF
(Cj=2fF + Cs=70fF + Cg=5fF) gives Ej~=14.9GHz, Ec~=0.25GHz, Ej/Ec~=59 --
squarely in the textbook transmon regime (Koch et al., PRA 76, 042319
(2007), typically design for Ej/Ec of a few tens to ~100).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.netlist import Netlist
from scipy.constants import e as _ELEMENTARY_CHARGE
from scipy.constants import h as _PLANCK_H

from .topology import (
    CouplingTopology,
    QubitTopology,
    ResonatorTopology,
    extract_coupling_topology,
    extract_qubit_topology,
    extract_resonator_topology,
)

# Magnetic flux quantum Phi_0 = h / (2e), in Weber (V*s).
FLUX_QUANTUM = _PLANCK_H / (2.0 * _ELEMENTARY_CHARGE)


@dataclass(frozen=True)
class QubitQuantization:
    """Quantized transmon parameters extracted from a netlist, in GHz/fF/nA.

    Args:
        Ej_GHz: Josephson energy E_J / h, in GHz.
        Ec_GHz: Charging energy E_C / h, in GHz.
        Ic_nA: The junction's critical current, in nA (as given in the netlist).
        C_sigma_fF: Total capacitance at the qubit island node, in fF.
        Cg_fF: Total capacitance directly coupling the qubit island to the
            resonator's active node, in fF (0 if not directly coupled).
        junction_id: Id of the junction element quantized.
        island_node: Netlist node id of the qubit island.
        qubit_topology, resonator_topology, coupling_topology: The raw
            topology this quantization was derived from (kept for HDF5
            provenance/debugging).
    """

    Ej_GHz: float
    Ec_GHz: float
    Ic_nA: float
    C_sigma_fF: float
    Cg_fF: float
    junction_id: str
    island_node: str
    qubit_topology: QubitTopology
    resonator_topology: ResonatorTopology
    coupling_topology: CouplingTopology

    @property
    def Ej_over_Ec(self) -> float:
        """The Ej/Ec ratio (dimensionless). >>1 is the transmon regime."""
        return self.Ej_GHz / self.Ec_GHz


def _total_capacitance_si(netlist: Netlist, qubit: QubitTopology) -> float:
    """Sum, in Farad, the junction's Cj plus every capacitor on its island node."""
    total = qubit.junction.params["Cj"].to_si()
    for cap_id in qubit.capacitor_ids:
        cap = netlist.element_by_id(cap_id)
        assert cap is not None  # topology.py only returns ids that resolve
        total += cap.params["C"].to_si()
    return total


def _coupling_capacitance_si(netlist: Netlist, coupling: CouplingTopology) -> float:
    """Sum, in Farad, every capacitor directly bridging qubit island <-> resonator."""
    total = 0.0
    for cap_id in coupling.capacitor_ids:
        cap = netlist.element_by_id(cap_id)
        assert cap is not None
        total += cap.params["C"].to_si()
    return total


def quantize_circuit(netlist: Netlist) -> QubitQuantization:
    """Extract Ej, Ec and the qubit-resonator coupling capacitance from a netlist.

    Args:
        netlist: A validated :class:`~core.netlist.Netlist` containing exactly
            one ``junction`` and one ``resonator`` (MVP single-transmon
            topology; see :mod:`core.solvers.quantum.topology`).

    Returns:
        The :class:`QubitQuantization` result, all energies in GHz.

    Raises:
        core.solvers.quantum.topology.TopologyError: if the netlist does not
            have the expected single-junction / single-resonator topology.
    """
    qubit = extract_qubit_topology(netlist)
    resonator = extract_resonator_topology(netlist)
    coupling = extract_coupling_topology(netlist, qubit, resonator)

    Ic_si = qubit.junction.params["Ic"].to_si()  # Amperes
    Ej_si = (FLUX_QUANTUM / (2.0 * math.pi)) * Ic_si  # Joules
    Ej_GHz = Ej_si / _PLANCK_H / 1e9

    C_sigma_si = _total_capacitance_si(netlist, qubit)  # Farad
    Ec_si = _ELEMENTARY_CHARGE**2 / (2.0 * C_sigma_si)  # Joules
    Ec_GHz = Ec_si / _PLANCK_H / 1e9

    Cg_si = _coupling_capacitance_si(netlist, coupling)  # Farad

    return QubitQuantization(
        Ej_GHz=Ej_GHz,
        Ec_GHz=Ec_GHz,
        Ic_nA=Ic_si * 1e9,
        C_sigma_fF=C_sigma_si * 1e15,
        Cg_fF=Cg_si * 1e15,
        junction_id=qubit.junction.id,
        island_node=qubit.island_node,
        qubit_topology=qubit,
        resonator_topology=resonator,
        coupling_topology=coupling,
    )
