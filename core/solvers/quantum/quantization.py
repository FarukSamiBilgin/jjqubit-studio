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


def _ej_ghz_from_ic(ic_a: float) -> float:
    """Josephson energy E_J/h in GHz from a critical current in amperes."""
    ej_si = (FLUX_QUANTUM / (2.0 * math.pi)) * ic_a  # Joules
    return ej_si / _PLANCK_H / 1e9


def flux_tunable_ej_factor(flux: float, asymmetry_d: float) -> float:
    """SQUID flux-tuning factor Ej(flux)/EjMax (dimensionless).

    ``Ej(f)/EjMax = sqrt(cos^2(pi f) + d^2 sin^2(pi f))`` with ``f = Phi/Phi0``
    and asymmetry ``d = (I2 - I1)/(I2 + I1)`` (Koch et al., PRA 76, 042319
    (2007), eq. 2.16; the standard asymmetric-SQUID tuning used by
    scqubits.TunableTransmon). f=0 gives 1 (max Ej); a symmetric SQUID (d=0)
    is fully suppressed to 0 at f=0.5, while asymmetry sets a nonzero minimum
    ``|d|``.
    """
    c = math.cos(math.pi * flux)
    s = math.sin(math.pi * flux)
    return math.sqrt(c * c + asymmetry_d * asymmetry_d * s * s)


def _optional_dimensionless(qubit_topology_element, name: str) -> float:
    """Value of an optional dimensionless param, defaulting to 0.0 if absent."""
    q = qubit_topology_element.params.get(name)
    return 0.0 if q is None else q.to_si()


@dataclass(frozen=True)
class JosephsonParams:
    """The Josephson energy of a single junction/squid element, in GHz.

    ``Ej_GHz`` is the effective value (flux-tuned for a squid); ``EjMax_GHz``,
    ``flux`` and ``asymmetry_d`` describe the tuning (trivial for a junction).
    """

    Ej_GHz: float
    EjMax_GHz: float
    flux: float
    asymmetry_d: float
    Ic_nA: float
    element_type: str


def element_josephson_params(element) -> JosephsonParams:
    """Compute the (effective) Josephson energy of a junction or squid element.

    Shared by the single- and multi-qubit quantization paths.
    """
    if element.type == "squid":
        ic_max_si = element.params["Ic_max"].to_si()  # Amperes
        flux = _optional_dimensionless(element, "flux")
        asymmetry_d = _optional_dimensionless(element, "d")
        ej_max = _ej_ghz_from_ic(ic_max_si)
        return JosephsonParams(
            Ej_GHz=ej_max * flux_tunable_ej_factor(flux, asymmetry_d),
            EjMax_GHz=ej_max,
            flux=flux,
            asymmetry_d=asymmetry_d,
            Ic_nA=ic_max_si * 1e9,
            element_type="squid",
        )
    ic_si = element.params["Ic"].to_si()  # Amperes
    ej = _ej_ghz_from_ic(ic_si)
    return JosephsonParams(
        Ej_GHz=ej,
        EjMax_GHz=ej,
        flux=0.0,
        asymmetry_d=0.0,
        Ic_nA=ic_si * 1e9,
        element_type="junction",
    )


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
        junction_id: Id of the junction/squid element quantized.
        island_node: Netlist node id of the qubit island.
        qubit_topology, resonator_topology, coupling_topology: The raw
            topology this quantization was derived from (kept for HDF5
            provenance/debugging).
        element_type: ``"junction"`` (fixed) or ``"squid"`` (flux-tunable).
        EjMax_GHz: The maximum (zero-flux) Josephson energy, in GHz. Equals
            ``Ej_GHz`` for a fixed junction; for a squid it is the flux=0 value
            and ``Ej_GHz`` is the effective value at the applied ``flux``.
        flux: External flux threading the SQUID loop, in units of Phi0
            (0.0 for a fixed junction).
        asymmetry_d: SQUID junction asymmetry d (0.0 for a fixed junction or a
            symmetric squid).
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
    element_type: str = "junction"
    EjMax_GHz: float = 0.0
    flux: float = 0.0
    asymmetry_d: float = 0.0

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

    element = qubit.junction
    # Effective Ej (flux-tuned for a squid). At a fixed flux the spectrum is
    # that of a plain transmon with Ej = Ej_eff, so the pipeline is unchanged.
    jp = element_josephson_params(element)
    Ej_GHz = jp.Ej_GHz
    EjMax_GHz = jp.EjMax_GHz
    flux = jp.flux
    asymmetry_d = jp.asymmetry_d
    Ic_nA = jp.Ic_nA

    C_sigma_si = _total_capacitance_si(netlist, qubit)  # Farad
    Ec_si = _ELEMENTARY_CHARGE**2 / (2.0 * C_sigma_si)  # Joules
    Ec_GHz = Ec_si / _PLANCK_H / 1e9

    Cg_si = _coupling_capacitance_si(netlist, coupling)  # Farad

    return QubitQuantization(
        Ej_GHz=Ej_GHz,
        Ec_GHz=Ec_GHz,
        Ic_nA=Ic_nA,
        C_sigma_fF=C_sigma_si * 1e15,
        Cg_fF=Cg_si * 1e15,
        junction_id=element.id,
        island_node=qubit.island_node,
        qubit_topology=qubit,
        resonator_topology=resonator,
        coupling_topology=coupling,
        element_type=element.type,
        EjMax_GHz=EjMax_GHz,
        flux=flux,
        asymmetry_d=asymmetry_d,
    )
