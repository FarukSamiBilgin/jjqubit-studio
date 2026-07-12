"""HDF5 output for the classical solver.

Layout (documented here AND shared with waveform-ui and main -- this is a
solver-output convention, not part of the frozen netlist contract, so it is
agreed directly between the producing and consuming teammates, mirroring
``core/solvers/quantum/hdf5_io.py``'s style: scalar physics as group attrs
with unit-suffixed names, every dataset given an explicit ``unit`` attr)::

    / (root)
      attrs: format="jjqubit-classical-result", version="1.0",
             generated_by="core.solvers.classical", netlist_name=<str>

    /rcsj  (group, present iff the netlist has a current-biased junction --
            see core/solvers/classical/topology.py:extract_rcsj_topology)
      attrs: Ic_nA, Rn_total_ohm, C_total_fF, bias_current_nA,
             quality_factor (dimensionless, Rn*sqrt(2e*Ic/(hbar*C)); >1 is
             underdamped/hysteretic), plasma_frequency_GHz, junction_id,
             bias_node, ground_node, current_source_id,
             shunt_resistor_ids, capacitor_ids (comma-joined element ids
             contributing to R_total/C_total), inductor_ids (comma-joined;
             EMPTY unless the netlist wires an inductor to the bias node --
             see rcsj.py module docstring for why it is detected but not
             folded into the ODE)

      /rcsj/phase_dynamics  (task item 3: phase-dynamics output)
        dataset time_ns             float64[n], unit="ns"
        dataset phase_rad           float64[n], unit="rad"
        dataset voltage_uV          float64[n], unit="uV"
        attrs: bias_current_nA, dc_voltage_uV (settled average)

      /rcsj/iv_curve  (task item 2: I-V curve)
        dataset bias_current_up_nA, voltage_up_uV     (ascending sweep)
        dataset bias_current_down_nA, voltage_down_uV (descending sweep,
               shows retrapping-current hysteresis for an underdamped
               junction)
        all four datasets have a "unit" attr ("nA"/"uV")

    /readout  (group, present iff the netlist has a resonator capacitively
               coupled to a terminated transmission line -- see
               topology.py:extract_readout_topology)
      attrs: f0_GHz, Q_internal, kappa_int_MHz, kappa_ext_MHz,
             kappa_total_MHz, resonator_C_fF, resonator_L_nH (both ASSUMED,
             see s21.py module docstring), resonator_impedance_assumed_ohm,
             z0_ohm, termination_ohm, line_length_mm, eps_eff,
             coupling_capacitance_fF, resonator_id, active_node,
             transmission_line_id, termination_id

      dataset frequency_GHz   float64[n], unit="GHz"
      dataset s21_real        float64[n], unit=""
      dataset s21_imag        float64[n], unit=""
      dataset s21_mag_db      float64[n], unit="dB"      (20*log10|S21|)
      dataset s21_phase_deg   float64[n], unit="deg"     (convenience for waveform-ui)

    /assumptions  (group; always present, even if empty of specific notes)
      attrs: resonator_impedance_ohm (only if /readout present -- see
             s21.py), rcsj_inductor_note (only if /rcsj present AND the
             bias node has an inductor -- see rcsj.py)

At least one of ``/rcsj``/``/readout`` is present; a netlist lacking both
topologies is a :class:`~core.solvers.classical.topology.TopologyError`
raised upstream in ``cli.py`` before this module is reached.
"""
from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from .rcsj import plasma_frequency_rad_s
from .runner import ReadoutAnalysis, RCSJAnalysis
from .s21 import DEFAULT_RESONATOR_IMPEDANCE_OHM

FORMAT = "jjqubit-classical-result"
FORMAT_VERSION = "1.0"


def _write_rcsj_group(f: h5py.File, rcsj: RCSJAnalysis) -> None:
    topo = rcsj.topology
    group = f.create_group("rcsj")
    group.attrs["Ic_nA"] = rcsj.critical_current_a * 1e9
    group.attrs["Rn_total_ohm"] = rcsj.resistance_ohm
    group.attrs["C_total_fF"] = rcsj.capacitance_f * 1e15
    group.attrs["bias_current_nA"] = rcsj.bias_current_a * 1e9

    omega_p = plasma_frequency_rad_s(rcsj.critical_current_a, rcsj.capacitance_f)
    # Stewart-McCumber damping quality factor Q = sqrt(beta_c) = omega_p * R * C
    # (beta_c = 2e*Ic*R^2*C/hbar is the McCumber parameter). Q >> 1 is
    # underdamped/hysteretic (retrapping current below Ic); Q << 1 overdamped.
    group.attrs["quality_factor"] = omega_p * rcsj.resistance_ohm * rcsj.capacitance_f
    group.attrs["plasma_frequency_GHz"] = omega_p / (2.0 * np.pi) / 1e9
    group.attrs["junction_id"] = topo.junction.id
    group.attrs["current_source_id"] = topo.current_source.id
    group.attrs["bias_node"] = topo.bias_node
    group.attrs["ground_node"] = topo.ground_node
    group.attrs["shunt_resistor_ids"] = ",".join(topo.shunt_resistor_ids)
    group.attrs["capacitor_ids"] = ",".join(topo.capacitor_ids)
    group.attrs["inductor_ids"] = ",".join(topo.inductor_ids)

    dynamics_group = group.create_group("phase_dynamics")
    dynamics = rcsj.phase_dynamics
    time_ds = dynamics_group.create_dataset("time_ns", data=dynamics.time_s * 1e9)
    time_ds.attrs["unit"] = "ns"
    phase_ds = dynamics_group.create_dataset("phase_rad", data=dynamics.phase_rad)
    phase_ds.attrs["unit"] = "rad"
    voltage_ds = dynamics_group.create_dataset("voltage_uV", data=dynamics.voltage_v * 1e6)
    voltage_ds.attrs["unit"] = "uV"
    dynamics_group.attrs["bias_current_nA"] = dynamics.bias_current_a * 1e9
    dynamics_group.attrs["dc_voltage_uV"] = dynamics.dc_voltage_v * 1e6

    iv_group = group.create_group("iv_curve")
    iv = rcsj.iv_curve
    for name, data, unit in (
        ("bias_current_up_nA", iv.bias_current_up_a * 1e9, "nA"),
        ("voltage_up_uV", iv.voltage_up_v * 1e6, "uV"),
        ("bias_current_down_nA", iv.bias_current_down_a * 1e9, "nA"),
        ("voltage_down_uV", iv.voltage_down_v * 1e6, "uV"),
    ):
        ds = iv_group.create_dataset(name, data=data)
        ds.attrs["unit"] = unit


def _write_readout_group(f: h5py.File, readout: ReadoutAnalysis) -> None:
    topo = readout.topology
    curve = readout.s21_curve
    group = f.create_group("readout")
    group.attrs["f0_GHz"] = curve.f0_hz / 1e9
    group.attrs["Q_internal"] = curve.q_internal
    group.attrs["kappa_int_MHz"] = curve.kappa_int_hz / 1e6
    group.attrs["kappa_ext_MHz"] = curve.kappa_ext_hz / 1e6
    group.attrs["kappa_total_MHz"] = curve.kappa_total_hz / 1e6
    group.attrs["resonator_C_fF"] = curve.resonator_c_f * 1e15
    group.attrs["resonator_L_nH"] = curve.resonator_l_f * 1e9
    group.attrs["resonator_impedance_assumed_ohm"] = curve.resonator_impedance_ohm
    group.attrs["z0_ohm"] = curve.z0_ohm
    group.attrs["termination_ohm"] = curve.termination_ohm
    group.attrs["line_length_mm"] = curve.line_length_m * 1e3
    group.attrs["eps_eff"] = curve.eps_eff
    group.attrs["coupling_capacitance_fF"] = curve.coupling_capacitance_f * 1e15
    group.attrs["resonator_id"] = topo.resonator.id
    group.attrs["active_node"] = topo.active_node
    group.attrs["transmission_line_id"] = topo.transmission_line.id
    group.attrs["termination_id"] = topo.termination.id

    freq_ds = group.create_dataset("frequency_GHz", data=curve.frequency_hz / 1e9)
    freq_ds.attrs["unit"] = "GHz"
    real_ds = group.create_dataset("s21_real", data=curve.s21.real)
    real_ds.attrs["unit"] = ""
    imag_ds = group.create_dataset("s21_imag", data=curve.s21.imag)
    imag_ds.attrs["unit"] = ""
    mag_db_ds = group.create_dataset("s21_mag_db", data=20.0 * np.log10(np.abs(curve.s21)))
    mag_db_ds.attrs["unit"] = "dB"
    phase_ds = group.create_dataset("s21_phase_deg", data=np.degrees(np.angle(curve.s21)))
    phase_ds.attrs["unit"] = "deg"


def write_hdf5(
    path: str | Path,
    *,
    netlist_name: str,
    rcsj: RCSJAnalysis | None = None,
    readout: ReadoutAnalysis | None = None,
) -> None:
    """Write classical-solver results to an HDF5 file (see module docstring for layout).

    Args:
        path: Output file path. Parent directory must already exist.
        netlist_name: The ``Netlist.name`` this result was computed from.
        rcsj: Result of :func:`core.solvers.classical.runner.run_rcsj_analysis`,
            or ``None`` if the netlist had no RCSJ bias topology.
        readout: Result of
            :func:`core.solvers.classical.runner.run_readout_analysis`, or
            ``None`` if the netlist had no readout topology.

    Raises:
        ValueError: if both ``rcsj`` and ``readout`` are ``None`` (nothing to write).
    """
    if rcsj is None and readout is None:
        raise ValueError("write_hdf5: nothing to write (both rcsj and readout are None)")

    with h5py.File(path, "w") as f:
        f.attrs["format"] = FORMAT
        f.attrs["version"] = FORMAT_VERSION
        f.attrs["generated_by"] = "core.solvers.classical"
        f.attrs["netlist_name"] = netlist_name

        if rcsj is not None:
            _write_rcsj_group(f, rcsj)
        if readout is not None:
            _write_readout_group(f, readout)

        assumptions_group = f.create_group("assumptions")
        if readout is not None:
            assumptions_group.attrs["resonator_impedance_ohm"] = DEFAULT_RESONATOR_IMPEDANCE_OHM
            assumptions_group.attrs["resonator_impedance_note"] = (
                "resonator element only specifies f0 and Q (no impedance/capacitance); "
                f"Z_r = {DEFAULT_RESONATOR_IMPEDANCE_OHM} ohm assumed to derive its lumped "
                "L/C for the feedline coupling rate kappa_ext (same assumption and value "
                "already used by core/solvers/quantum/dispersive.py). See "
                "core/solvers/classical/s21.py module docstring."
            )
        if rcsj is not None and rcsj.topology.inductor_ids:
            assumptions_group.attrs["rcsj_inductor_note"] = (
                f"inductor(s) {','.join(rcsj.topology.inductor_ids)} are wired to the RCSJ "
                "bias node but are NOT included in the phase ODE: this solver implements the "
                "literal R-C-shunted-junction model docs/task.md names for Gorev 2, not an "
                "inductively-shunted (RCLSJ/rf-SQUID-like) variant, which would qualitatively "
                "change the I<Ic zero-voltage limit (a shunt inductor confines the phase for "
                "ANY bias, per a parabolic potential term, making that limit trivial). See "
                "core/solvers/classical/rcsj.py module docstring; flagged to main."
            )
