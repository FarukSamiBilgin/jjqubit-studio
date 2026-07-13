"""HDF5 output for the quantum solver.

Layout (documented here AND shared with waveform-ui and main -- this is a
solver-output convention, not part of the frozen netlist contract, so it is
agreed directly between the producing and consuming teammates)::

    / (root)
      attrs: format="jjqubit-quantum-result", version="1.1",
             generated_by="core.solvers.quantum", netlist_name=<str>

    /provenance  (group)
      attrs: provenance_version, generated_by, created_at_utc, python_version,
             platform, netlist_sha256 (when known), lib_<name>=<version> for
             numpy/scipy/h5py/scqubits/qutip. See core/provenance.py.

    /qubit  (group)
      dataset: energy_levels          float64[n_levels], unit="GHz"
               -- eigenenergies E_0..E_{n-1} relative to the ground state
                  (E_0 = 0), for the energy-level diagram.
      attrs: Ej_GHz, Ec_GHz, Ej_over_Ec, E01_GHz, anharmonicity_GHz,
             Ic_nA, C_sigma_fF, junction_id, island_node, n01

    /resonator  (group)
      attrs: f0_GHz, Q, kappa_GHz, resonator_id, active_node

    /coupling  (group)
      attrs: g_GHz (the PHYSICAL 0<->1 vacuum Rabi coupling -- see
             g_GHz_description attr and core/solvers/quantum/dispersive.py
             for why this differs from the "bare" coefficient used
             internally), g_GHz_description, chi_GHz, Delta_GHz, beta, Cg_fF,
             g_over_Delta (|g/Delta| dispersive small parameter),
             dispersive_regime_valid (bool; False => chi is not a perturbative
             dispersive shift, see dispersive.py DISPERSIVE_VALIDITY_THRESHOLD)

    /assumptions  (group)
      attrs: resonator_Z0_ohm, note (free-text explanation, see dispersive.py)

Every physical dataset/attr name is suffixed with its unit (``_GHz``,
``_fF``, ``_nA``, ``_ohm``); dimensionless quantities have no suffix
(``Q``, ``beta``, ``Ej_over_Ec``, ``n01``). In addition, every DATASET (not
scalar attrs) carries an explicit ``unit`` attribute, matching the
``{"value":, "unit":}`` convention already used by ``core.netlist.Quantity``,
for generic consumers that read units off the dataset rather than parsing
its name.
"""

from __future__ import annotations

from pathlib import Path

import h5py
from core.provenance import write_provenance

from .dispersive import DispersiveResult
from .quantization import QubitQuantization
from .spectrum import TransmonSpectrum

FORMAT = "jjqubit-quantum-result"
# 1.0 -> 1.1: added the /provenance group (additive, backward compatible).
FORMAT_VERSION = "1.1"

# Libraries whose versions are worth recording for a quantum run.
_PROVENANCE_LIBS = ("numpy", "scipy", "h5py", "scqubits", "qutip")


def write_hdf5(
    path: str | Path,
    *,
    netlist_name: str,
    quantization: QubitQuantization,
    spectrum: TransmonSpectrum,
    dispersive: DispersiveResult,
    netlist_hash: str | None = None,
) -> None:
    """Write quantum-solver results to an HDF5 file (see module docstring for layout).

    Args:
        path: Output file path. Parent directory must already exist.
        netlist_name: The ``Netlist.name`` this result was computed from.
        quantization: Result of
            :func:`core.solvers.quantum.quantization.quantize_circuit`.
        spectrum: Result of
            :func:`core.solvers.quantum.spectrum.compute_transmon_spectrum`.
        dispersive: Result of
            :func:`core.solvers.quantum.dispersive.compute_dispersive_shift`.
        netlist_hash: Optional SHA-256 of the source netlist
            (:func:`core.provenance.netlist_sha256`), recorded in
            ``/provenance`` for reproducibility.
    """
    with h5py.File(path, "w") as f:
        f.attrs["format"] = FORMAT
        f.attrs["version"] = FORMAT_VERSION
        f.attrs["generated_by"] = "core.solvers.quantum"
        f.attrs["netlist_name"] = netlist_name

        write_provenance(
            f,
            generated_by="core.solvers.quantum",
            netlist_hash=netlist_hash,
            libraries=_PROVENANCE_LIBS,
        )

        qubit_group = f.create_group("qubit")
        levels = qubit_group.create_dataset(
            "energy_levels", data=spectrum.energy_levels_GHz
        )
        levels.attrs["unit"] = "GHz"
        levels.attrs["description"] = (
            "Transmon eigenenergies E_0..E_{n-1} relative to the ground state"
        )
        qubit_group.attrs["Ej_GHz"] = quantization.Ej_GHz
        qubit_group.attrs["Ec_GHz"] = quantization.Ec_GHz
        qubit_group.attrs["Ej_over_Ec"] = quantization.Ej_over_Ec
        qubit_group.attrs["E01_GHz"] = spectrum.E01_GHz
        qubit_group.attrs["anharmonicity_GHz"] = spectrum.anharmonicity_GHz
        qubit_group.attrs["Ic_nA"] = quantization.Ic_nA
        qubit_group.attrs["C_sigma_fF"] = quantization.C_sigma_fF
        qubit_group.attrs["junction_id"] = quantization.junction_id
        qubit_group.attrs["island_node"] = quantization.island_node
        qubit_group.attrs["n01"] = spectrum.n01

        resonator_group = f.create_group("resonator")
        resonator_group.attrs["f0_GHz"] = dispersive.f0_GHz
        resonator_group.attrs["Q"] = quantization.resonator_topology.resonator.params[
            "Q"
        ].to_si()
        resonator_group.attrs["kappa_GHz"] = dispersive.kappa_GHz
        resonator_group.attrs["resonator_id"] = (
            quantization.resonator_topology.resonator.id
        )
        resonator_group.attrs["active_node"] = (
            quantization.resonator_topology.active_node
        )

        coupling_group = f.create_group("coupling")
        coupling_group.attrs["g_GHz"] = dispersive.g_GHz
        coupling_group.attrs["g_GHz_description"] = (
            "Physical qubit-resonator vacuum Rabi coupling for the 0<->1 "
            "transition, g_01 = 2*e*beta*<0|n|1>*delta_V0/h (NOT the bare "
            "coefficient of the qubit charge operator used internally for "
            "the multi-level chi diagonalization -- see "
            "core/solvers/quantum/dispersive.py)."
        )
        coupling_group.attrs["chi_GHz"] = dispersive.chi_GHz
        coupling_group.attrs["Delta_GHz"] = dispersive.Delta_GHz
        coupling_group.attrs["beta"] = dispersive.beta
        coupling_group.attrs["Cg_fF"] = quantization.Cg_fF
        coupling_group.attrs["g_over_Delta"] = dispersive.g_over_Delta
        coupling_group.attrs["dispersive_regime_valid"] = (
            dispersive.dispersive_regime_valid
        )

        assumptions_group = f.create_group("assumptions")
        assumptions_group.attrs["resonator_Z0_ohm"] = dispersive.resonator_Z0_ohm
        assumptions_group.attrs["note"] = (
            "resonator element only specifies f0 and Q (no impedance/capacitance); "
            "Z0 assumed for the zero-point voltage used in the g calculation "
            "(standard on-chip CPW design impedance, matches transmission_line.Z0 "
            "in the bundled examples). See core/solvers/quantum/dispersive.py."
        )
