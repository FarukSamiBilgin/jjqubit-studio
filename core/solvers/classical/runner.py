"""Bridges netlist topology (topology.py) to the physics modules (rcsj.py, s21.py).

This is the layer that turns netlist ``Quantity`` parameters into the SI
floats the physics functions expect, and packages their outputs together
with the topology/provenance the HDF5 writer needs. Kept separate from
``cli.py`` so the analysis can be exercised directly in tests without going
through the command line.
"""
from __future__ import annotations

import numpy as np

from core.netlist import Netlist

from .rcsj import IVCurveResult, PhaseDynamicsResult, integrate_phase_dynamics, sweep_iv_curve
from .s21 import S21Curve, compute_s21_curve
from .topology import (
    RCSJTopology,
    ReadoutTopology,
    extract_rcsj_topology,
    extract_readout_topology,
)


class RCSJAnalysis:
    """RCSJ bias-circuit results: effective parameters, phase trace, I-V curve.

    Args:
        topology: The extracted :class:`~core.solvers.classical.topology.RCSJTopology`.
        critical_current_a: Junction ``Ic``, in amperes.
        resistance_ohm: Total shunt resistance ``R_total``, in ohms (junction
            ``Rn`` in parallel with any separate shunt resistor elements).
        capacitance_f: Total shunt capacitance ``C_total``, in farads
            (junction ``Cj`` plus every capacitor at the bias node).
        bias_current_a: The netlist's own ``current_source`` value, in amperes.
        phase_dynamics: Time-domain trace at ``bias_current_a`` (task item 3).
        iv_curve: Hysteretic current-sweep result (task item 2).
    """

    def __init__(
        self,
        topology: RCSJTopology,
        critical_current_a: float,
        resistance_ohm: float,
        capacitance_f: float,
        bias_current_a: float,
        phase_dynamics: PhaseDynamicsResult,
        iv_curve: IVCurveResult,
    ) -> None:
        self.topology = topology
        self.critical_current_a = critical_current_a
        self.resistance_ohm = resistance_ohm
        self.capacitance_f = capacitance_f
        self.bias_current_a = bias_current_a
        self.phase_dynamics = phase_dynamics
        self.iv_curve = iv_curve


def _total_shunt_resistance_si(netlist: Netlist, topo: RCSJTopology) -> float:
    """Parallel-combine the junction's Rn with any separate resistor(s) at the bias node."""
    conductance = 1.0 / topo.junction.params["Rn"].to_si()
    for r_id in topo.shunt_resistor_ids:
        el = netlist.element_by_id(r_id)
        assert el is not None
        conductance += 1.0 / el.params["R"].to_si()
    return 1.0 / conductance


def _total_shunt_capacitance_si(netlist: Netlist, topo: RCSJTopology) -> float:
    """Sum the junction's Cj plus every capacitor at the bias node, in farads."""
    total = topo.junction.params["Cj"].to_si()
    for c_id in topo.capacitor_ids:
        el = netlist.element_by_id(c_id)
        assert el is not None
        total += el.params["C"].to_si()
    return total


def run_rcsj_analysis(
    netlist: Netlist,
    *,
    n_sweep_points: int = 25,
    sweep_max_factor: float = 2.0,
) -> RCSJAnalysis:
    """Run the full RCSJ bias-circuit analysis for a netlist.

    Args:
        netlist: A validated :class:`~core.netlist.Netlist`.
        n_sweep_points: Number of bias-current samples in the I-V sweep
            (per branch; the sweep runs up then down).
        sweep_max_factor: The I-V sweep spans
            ``[0, sweep_max_factor * max(Ic, bias_current)]``, so it always
            covers both the critical current and the netlist's own bias
            point.

    Returns:
        The :class:`RCSJAnalysis`.

    Raises:
        core.solvers.classical.topology.TopologyError: if the netlist does
            not have the expected current-biased single-junction topology.
    """
    topo = extract_rcsj_topology(netlist)

    ic_a = topo.junction.params["Ic"].to_si()
    r_ohm = _total_shunt_resistance_si(netlist, topo)
    c_f = _total_shunt_capacitance_si(netlist, topo)
    bias_current_a = topo.current_source.params["I"].to_si()

    phase_dynamics = integrate_phase_dynamics(ic_a, r_ohm, c_f, bias_current_a)

    sweep_max_a = sweep_max_factor * max(ic_a, abs(bias_current_a))
    bias_currents_a = np.linspace(0.0, sweep_max_a, n_sweep_points)
    iv_curve = sweep_iv_curve(ic_a, r_ohm, c_f, bias_currents_a)

    return RCSJAnalysis(
        topology=topo,
        critical_current_a=ic_a,
        resistance_ohm=r_ohm,
        capacitance_f=c_f,
        bias_current_a=bias_current_a,
        phase_dynamics=phase_dynamics,
        iv_curve=iv_curve,
    )


class ReadoutAnalysis:
    """Readout-circuit results: S21 curve and the topology it was derived from.

    Args:
        topology: The extracted :class:`~core.solvers.classical.topology.ReadoutTopology`.
        s21_curve: The computed :class:`~core.solvers.classical.s21.S21Curve`.
    """

    def __init__(self, topology: ReadoutTopology, s21_curve: S21Curve) -> None:
        self.topology = topology
        self.s21_curve = s21_curve


def _total_coupling_capacitance_si(netlist: Netlist, topo: ReadoutTopology) -> float:
    total = 0.0
    for c_id in topo.coupling_capacitor_ids:
        el = netlist.element_by_id(c_id)
        assert el is not None
        total += el.params["C"].to_si()
    return total


def run_readout_analysis(netlist: Netlist) -> ReadoutAnalysis:
    """Run the full readout (S21) analysis for a netlist.

    Args:
        netlist: A validated :class:`~core.netlist.Netlist`.

    Returns:
        The :class:`ReadoutAnalysis`.

    Raises:
        core.solvers.classical.topology.TopologyError: if the netlist does
            not have the expected resonator/feedline/termination topology.
    """
    topo = extract_readout_topology(netlist)

    f0_hz = topo.resonator.params["f0"].to_si()
    q_internal = topo.resonator.params["Q"].to_si()
    ck_f = _total_coupling_capacitance_si(netlist, topo)
    z0_ohm = topo.transmission_line.params["Z0"].to_si()
    length_m = topo.transmission_line.params["length"].to_si()
    eps_eff = topo.transmission_line.params["eps_eff"].to_si()
    termination_ohm = topo.termination.params["R"].to_si()

    s21_curve = compute_s21_curve(
        f0_hz=f0_hz,
        q_internal=q_internal,
        coupling_capacitance_f=ck_f,
        z0_ohm=z0_ohm,
        line_length_m=length_m,
        eps_eff=eps_eff,
        termination_ohm=termination_ohm,
    )

    return ReadoutAnalysis(topology=topo, s21_curve=s21_curve)
