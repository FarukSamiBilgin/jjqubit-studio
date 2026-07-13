"""Implementation of the scriptable API (see :mod:`jjqubit`).

Each ``solve_*`` function mirrors the corresponding ``core.solvers.*`` CLI's
``run()`` exactly -- same load, same analysis calls -- but returns the live
result objects instead of an exit code, and defers writing HDF5 to an optional
method. All heavy imports are local so ``import jjqubit`` stays GUI- and
scqubits-free until a solver is actually run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.netlist import Netlist, load

if TYPE_CHECKING:  # avoid importing the heavy solver modules at import time
    from core.solvers.classical.runner import RCSJAnalysis, ReadoutAnalysis
    from core.solvers.quantum.coherence import CoherenceResult
    from core.solvers.quantum.dispersive import DispersiveResult
    from core.solvers.quantum.multiqubit import (
        TwoQubitQuantization,
        TwoTransmonResult,
    )
    from core.solvers.quantum.quantization import QubitQuantization
    from core.solvers.quantum.spectrum import TransmonSpectrum

# A netlist argument may be an already-loaded Netlist or a path to a JSON file.
NetlistLike = Netlist | str | Path


def load_netlist(path: str | Path) -> Netlist:
    """Load and validate a netlist JSON file (frozen ``core.netlist`` format).

    Args:
        path: Path to a netlist JSON file.

    Returns:
        The validated :class:`core.netlist.Netlist`.

    Raises:
        core.netlist.NetlistError: on a schema/unit/validation problem.
        OSError: if the file cannot be read.
    """
    return load(str(path), validate=True)


def _as_netlist(netlist: NetlistLike) -> Netlist:
    """Accept a Netlist or a path and return a validated Netlist."""
    if isinstance(netlist, Netlist):
        return netlist
    return load_netlist(netlist)


@dataclass
class QuantumSolution:
    """Result of :func:`solve_quantum`.

    Bundles the live objects the quantum solver produces -- the circuit
    quantization, the transmon spectrum, and the dispersive shift -- so callers
    get the full, unmodified physics output plus convenience accessors. Units
    are as named on each field (GHz unless a property says otherwise).
    """

    netlist: Netlist
    quantization: QubitQuantization
    spectrum: TransmonSpectrum
    dispersive: DispersiveResult
    coherence: CoherenceResult

    # --- convenience passthroughs (no recomputation, just plain accessors) ---
    @property
    def Ej_GHz(self) -> float:
        return self.quantization.Ej_GHz

    @property
    def Ec_GHz(self) -> float:
        return self.quantization.Ec_GHz

    @property
    def Ej_over_Ec(self) -> float:
        return self.quantization.Ej_over_Ec

    @property
    def EjMax_GHz(self) -> float:
        """Max (zero-flux) Josephson energy; equals Ej_GHz for a fixed junction."""
        return self.quantization.EjMax_GHz

    @property
    def flux(self) -> float:
        """External flux Phi/Phi0 (0 for a fixed junction)."""
        return self.quantization.flux

    @property
    def is_tunable(self) -> bool:
        """Whether the qubit element is a flux-tunable squid."""
        return self.quantization.element_type == "squid"

    @property
    def E01_GHz(self) -> float:
        return self.spectrum.E01_GHz

    @property
    def anharmonicity_GHz(self) -> float:
        return self.spectrum.anharmonicity_GHz

    @property
    def g_MHz(self) -> float:
        """Qubit-resonator coupling g, in MHz."""
        return self.dispersive.g_GHz * 1e3

    @property
    def chi_MHz(self) -> float:
        """Dispersive shift chi, in MHz."""
        return self.dispersive.chi_GHz * 1e3

    @property
    def Delta_GHz(self) -> float:
        """Qubit-resonator detuning Delta, in GHz."""
        return self.dispersive.Delta_GHz

    @property
    def T1_us(self) -> float:
        """Estimated relaxation time T1, in microseconds."""
        return self.coherence.T1_us

    @property
    def T2_us(self) -> float:
        """Estimated Ramsey coherence time T2, in microseconds."""
        return self.coherence.T2_us

    @property
    def Tphi_us(self) -> float:
        """Estimated pure dephasing time Tphi, in microseconds (inf if none)."""
        return self.coherence.Tphi_us

    @property
    def T1_purcell_us(self) -> float:
        """Purcell-limited T1 through the resonator, in us (inf if uncoupled)."""
        return self.coherence.T1_purcell_us

    @property
    def g_over_Delta(self) -> float:
        """Dispersive small parameter |g/Delta| (must be << 1 for validity)."""
        return self.dispersive.g_over_Delta

    @property
    def dispersive_valid(self) -> bool:
        """Whether chi may be read as a perturbative dispersive shift."""
        return self.dispersive.dispersive_regime_valid

    def summary(self) -> dict[str, float]:
        """A flat dict of the headline scalars, handy for sweeps/DataFrames."""
        return {
            "Ej_GHz": self.Ej_GHz,
            "Ec_GHz": self.Ec_GHz,
            "Ej_over_Ec": self.Ej_over_Ec,
            "E01_GHz": self.E01_GHz,
            "anharmonicity_GHz": self.anharmonicity_GHz,
            "g_MHz": self.g_MHz,
            "chi_MHz": self.chi_MHz,
            "Delta_GHz": self.Delta_GHz,
        }

    def write_hdf5(self, path: str | Path) -> None:
        """Write the result in the same HDF5 layout the CLI and GUI use."""
        from core.provenance import netlist_sha256
        from core.solvers.quantum.hdf5_io import write_hdf5

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        write_hdf5(
            str(path),
            netlist_name=self.netlist.name,
            quantization=self.quantization,
            spectrum=self.spectrum,
            dispersive=self.dispersive,
            coherence=self.coherence,
            netlist_hash=netlist_sha256(self.netlist),
        )


@dataclass
class ClassicalSolution:
    """Result of :func:`solve_classical`.

    ``rcsj`` is present when the netlist has an RCSJ bias topology
    (junction + current source); ``readout`` is present when it has a
    resonator + transmission-line readout topology. A netlist may yield one or
    both; :func:`solve_classical` raises if it yields neither.
    """

    netlist: Netlist
    rcsj: RCSJAnalysis | None
    readout: ReadoutAnalysis | None

    def write_hdf5(self, path: str | Path) -> None:
        """Write the result in the same HDF5 layout the CLI and GUI use."""
        from core.provenance import netlist_sha256
        from core.solvers.classical.hdf5_io import write_hdf5

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        write_hdf5(
            str(path),
            netlist_name=self.netlist.name,
            rcsj=self.rcsj,
            readout=self.readout,
            netlist_hash=netlist_sha256(self.netlist),
        )


def solve_quantum(netlist: NetlistLike) -> QuantumSolution:
    """Quantize a netlist and compute its transmon + dispersive spectrum.

    Mirrors ``core.solvers.quantum.cli.run`` but returns the live result
    objects (see :class:`QuantumSolution`) instead of writing a file. Call
    :meth:`QuantumSolution.write_hdf5` if you want the HDF5 the GUI reads.

    Args:
        netlist: A loaded :class:`core.netlist.Netlist`, or a path to a
            netlist JSON file.

    Returns:
        A :class:`QuantumSolution`.

    Raises:
        core.solvers.quantum.topology.TopologyError: if the netlist topology is
            not one the quantum solver supports.
        core.netlist.NetlistError / OSError: if a path is given and it cannot
            be loaded or validated.
    """
    from core.solvers.quantum.coherence import compute_coherence
    from core.solvers.quantum.dispersive import compute_dispersive_shift
    from core.solvers.quantum.quantization import quantize_circuit
    from core.solvers.quantum.spectrum import compute_transmon_spectrum

    net = _as_netlist(netlist)
    quantization = quantize_circuit(net)
    spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
    dispersive = compute_dispersive_shift(quantization, spectrum)
    coherence = compute_coherence(quantization, dispersive=dispersive)
    return QuantumSolution(
        netlist=net,
        quantization=quantization,
        spectrum=spectrum,
        dispersive=dispersive,
        coherence=coherence,
    )


@dataclass
class TwoQubitSolution:
    """Result of :func:`solve_two_qubit` for two capacitively-coupled qubits.

    Bundles the netlist, the two-qubit quantization (Ej/Ec per qubit, coupling)
    and the coupled spectrum, with convenience accessors and HDF5 output. See
    :mod:`core.solvers.quantum.multiqubit`.
    """

    netlist: Netlist
    quantization: TwoQubitQuantization
    result: TwoTransmonResult

    @property
    def omega1_GHz(self) -> float:
        return self.result.omega1_GHz

    @property
    def omega2_GHz(self) -> float:
        return self.result.omega2_GHz

    @property
    def detuning_GHz(self) -> float:
        return self.result.detuning_GHz

    @property
    def J_GHz(self) -> float:
        """Exchange coupling J, in GHz."""
        return self.result.J_GHz

    @property
    def J_MHz(self) -> float:
        """Exchange coupling J, in MHz."""
        return self.result.J_GHz * 1e3

    @property
    def one_excitation_splitting_GHz(self) -> float:
        return self.result.one_excitation_splitting_GHz

    @property
    def zz_MHz(self) -> float:
        """Static ZZ interaction, in MHz (NaN at exact resonance)."""
        return self.result.zz_MHz

    @property
    def iswap_gate_time_ns(self) -> float:
        """Resonant iSWAP gate time 1/(4J), in ns (inf if uncoupled)."""
        return self.result.iswap_gate_time_ns

    @property
    def anharmonicity1_MHz(self) -> float:
        """Qubit 1 anharmonicity, in MHz."""
        return self.result.anharmonicity1_MHz

    @property
    def anharmonicity2_MHz(self) -> float:
        """Qubit 2 anharmonicity, in MHz."""
        return self.result.anharmonicity2_MHz

    @property
    def g_MHz(self) -> float:
        """Charge-charge coupling coefficient g, in MHz."""
        return self.quantization.g_GHz * 1e3

    @property
    def Cc_fF(self) -> float:
        """Coupling capacitance, in fF."""
        return self.quantization.Cc_fF

    def write_hdf5(self, path: str | Path) -> None:
        """Write the two-qubit result in its HDF5 layout (with provenance)."""
        from core.provenance import netlist_sha256
        from core.solvers.quantum.multiqubit import write_two_qubit_hdf5

        write_two_qubit_hdf5(
            str(path),
            netlist_name=self.netlist.name,
            quantization=self.quantization,
            result=self.result,
            netlist_hash=netlist_sha256(self.netlist),
        )


def solve_two_qubit(netlist: NetlistLike, *, evals_count: int = 6) -> TwoQubitSolution:
    """Solve a two-capacitively-coupled-transmon netlist for its coupled spectrum.

    Quantizes the two qubits and their coupling capacitor and diagonalizes the
    joint system (see :mod:`core.solvers.quantum.multiqubit`).

    Args:
        netlist: A loaded :class:`core.netlist.Netlist`, or a path to a netlist
            JSON file, describing two Josephson qubits bridged by a coupling
            capacitor.
        evals_count: Number of joint eigenvalues to return.

    Returns:
        A :class:`TwoQubitSolution` (bare frequencies, single-excitation
        splitting, exchange coupling J, static ZZ, and the coupled levels).

    Raises:
        core.solvers.quantum.topology.TopologyError: if the netlist is not a
            valid two-qubit coupled topology.
    """
    from core.solvers.quantum.multiqubit import (
        compute_two_transmon_spectrum,
        quantize_two_qubit_circuit,
    )

    net = _as_netlist(netlist)
    quantization = quantize_two_qubit_circuit(net)
    result = compute_two_transmon_spectrum(
        quantization.Ej1_GHz,
        quantization.Ec1_GHz,
        quantization.Ej2_GHz,
        quantization.Ec2_GHz,
        quantization.g_GHz,
        evals_count=evals_count,
    )
    return TwoQubitSolution(netlist=net, quantization=quantization, result=result)


def solve_classical(netlist: NetlistLike) -> ClassicalSolution:
    """Run the classical RCSJ / I-V / phase-dynamics / readout-S21 analysis.

    Mirrors ``core.solvers.classical.cli.run``: whichever of the RCSJ-bias and
    readout topologies the netlist contains is computed; a netlist with neither
    is an error.

    Args:
        netlist: A loaded :class:`core.netlist.Netlist`, or a path to a
            netlist JSON file.

    Returns:
        A :class:`ClassicalSolution` with ``rcsj`` and/or ``readout`` populated.

    Raises:
        ValueError: if the netlist has neither an RCSJ-bias nor a readout
            topology this solver supports.
        core.netlist.NetlistError / OSError: if a path is given and it cannot
            be loaded or validated.
    """
    from core.solvers.classical.runner import (
        run_rcsj_analysis,
        run_readout_analysis,
    )
    from core.solvers.classical.topology import TopologyError

    net = _as_netlist(netlist)

    rcsj: Any = None
    readout: Any = None
    rcsj_error: TopologyError | None = None
    readout_error: TopologyError | None = None

    try:
        rcsj = run_rcsj_analysis(net)
    except TopologyError as exc:
        rcsj_error = exc

    try:
        readout = run_readout_analysis(net)
    except TopologyError as exc:
        readout_error = exc

    if rcsj is None and readout is None:
        raise ValueError(
            f"netlist {net.name!r} has neither an RCSJ bias topology nor a "
            f"readout topology this solver supports:\n"
            f"  RCSJ: {rcsj_error}\n"
            f"  readout: {readout_error}"
        )

    return ClassicalSolution(netlist=net, rcsj=rcsj, readout=readout)
