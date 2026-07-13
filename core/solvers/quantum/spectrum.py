"""Transmon spectrum via scqubits (energy levels, E01, anharmonicity).

Per CLAUDE.md's "Yapmayacaklarimiz" #2, we do NOT reimplement the
Cooper-pair-box / transmon Hamiltonian ourselves -- ``scqubits.Transmon``
(a validated, published tool) diagonalizes
``H = 4*Ec*(n-ng)^2 - (Ej/2)*(|n><n+1| + h.c.)`` for us. This module is a
thin, unit-documented wrapper around it.

scqubits convention: all energies (``EJ``, ``EC``, eigenvalues, ``E01``,
``anharmonicity``) are quoted in GHz, i.e. as a FREQUENCY (energy / h, not
energy / hbar). This module follows the same convention throughout, matching
:mod:`core.solvers.quantum.quantization`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import scqubits as scq

# Default charge-basis cutoff for scqubits.Transmon: -ncut..+ncut, so the
# Hilbert space dimension is 2*ncut+1. Convergence of the transmon spectrum
# in the charge basis requires ncut to grow with sqrt(Ej/Ec) (the WKB
# localization width of the phase-basis wavefunction); 30 is the scqubits
# tutorial default and is already generous for Ej/Ec ~ O(1-100). We scale it
# up further for unusually deep-transmon inputs so the solver stays correct
# outside the bundled example's regime, not just tuned to it.
_MIN_NCUT = 30
_NCUT_SCALE = 6.0


def _adaptive_ncut(ej_over_ec: float) -> int:
    """Charge-basis cutoff, scaled to stay converged as Ej/Ec grows."""
    return max(_MIN_NCUT, math.ceil(_NCUT_SCALE * math.sqrt(max(ej_over_ec, 1.0))))


@dataclass(frozen=True)
class TransmonSpectrum:
    """The diagonalized transmon spectrum, in GHz.

    Args:
        Ej_GHz, Ec_GHz: The inputs this spectrum was computed from.
        ng: Offset charge used (dimensionless; 0.0 unless a netlist someday
            carries one -- MVP netlists do not expose ``ng``).
        energy_levels_GHz: Eigenenergies E_0 <= E_1 <= ... relative to the
            ground state (``E_0 = 0``), length ``n_levels``.
        E01_GHz: The qubit's fundamental transition frequency, E_1 - E_0.
        anharmonicity_GHz: (E_2 - E_1) - (E_1 - E_0). Negative for a transmon.
        n01: |<0|charge operator|1>|, the charge matrix element between the
            two lowest levels (dimensionless; needed for the coupling g).
        transmon: The underlying ``scqubits.Transmon`` instance (kept so
            :mod:`core.solvers.quantum.dispersive` can reuse it directly
            rather than rebuilding/re-diagonalizing).
    """

    Ej_GHz: float
    Ec_GHz: float
    ng: float
    energy_levels_GHz: np.ndarray
    E01_GHz: float
    anharmonicity_GHz: float
    n01: float
    transmon: scq.Transmon


def compute_transmon_spectrum(
    Ej_GHz: float, Ec_GHz: float, *, ng: float = 0.0, n_levels: int = 10
) -> TransmonSpectrum:
    """Diagonalize the transmon Hamiltonian for the given Ej, Ec (scqubits).

    Args:
        Ej_GHz: Josephson energy E_J / h, in GHz.
        Ec_GHz: Charging energy E_C / h, in GHz.
        ng: Offset charge (dimensionless), default 0.0 (charge-degeneracy
            point; the MVP netlist schema has no field for this).
        n_levels: Number of eigenlevels to return (truncated_dim in scqubits
            terms). Must be >= 3 to compute anharmonicity.

    Returns:
        The :class:`TransmonSpectrum`, all energies in GHz.

    Raises:
        ValueError: if ``n_levels < 3`` or ``Ej_GHz``/``Ec_GHz`` are not
            positive.
    """
    if Ej_GHz <= 0 or Ec_GHz <= 0:
        raise ValueError(f"Ej and Ec must be positive, got Ej={Ej_GHz}, Ec={Ec_GHz}")
    if n_levels < 3:
        raise ValueError(
            f"n_levels must be >= 3 to define anharmonicity, got {n_levels}"
        )

    ncut = _adaptive_ncut(Ej_GHz / Ec_GHz)
    transmon = scq.Transmon(
        EJ=Ej_GHz, EC=Ec_GHz, ng=ng, ncut=ncut, truncated_dim=n_levels
    )

    evals = transmon.eigenvals(evals_count=n_levels)
    energy_levels_GHz = evals - evals[0]  # report relative to the ground state

    n_matrix = transmon.n_operator(energy_esys=True)
    n01 = float(abs(n_matrix[0, 1]))

    return TransmonSpectrum(
        Ej_GHz=Ej_GHz,
        Ec_GHz=Ec_GHz,
        ng=ng,
        energy_levels_GHz=energy_levels_GHz,
        E01_GHz=float(transmon.E01()),
        anharmonicity_GHz=float(transmon.anharmonicity()),
        n01=n01,
        transmon=transmon,
    )
