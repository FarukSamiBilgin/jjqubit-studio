"""Run provenance for solver result files (GUI-free, stdlib only).

Every HDF5 result should record *how* it was produced so a file is
self-describing and reproducible: which solver and library versions ran, on
which Python, when, and against exactly which netlist. This module centralizes
that so the quantum and classical writers emit an identical ``/provenance``
group, and consumers have one place to read it.

No PySide6 import (core-wide rule). Kept deliberately dependency-light: only
the stdlib plus ``h5py`` (already a runtime dependency) at write time.
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from importlib import metadata
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import h5py
    from core.netlist import Netlist

# The provenance-group schema version. Bump on a breaking change to the group's
# attribute layout (additions are non-breaking and don't need a bump).
PROVENANCE_VERSION = "1.0"

# The name under which the provenance group is written in every result file.
PROVENANCE_GROUP = "provenance"


def netlist_sha256(netlist: Netlist) -> str:
    """Return a stable SHA-256 hex digest of a netlist's canonical content.

    Hashes the canonical JSON of :func:`core.netlist.to_dict` with sorted keys,
    so two netlists that serialize identically (the round-trip is lossless)
    hash identically, independent of dict ordering or file formatting.
    """
    from core.netlist import to_dict

    canonical = json.dumps(
        to_dict(netlist), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _package_version(name: str) -> str:
    """Best-effort installed version of a distribution, or ``"unknown"``."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


def collect_provenance(
    *,
    generated_by: str,
    netlist_hash: str | None = None,
    libraries: tuple[str, ...] = (),
    extra: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the provenance attribute mapping (see :func:`write_provenance`).

    Args:
        generated_by: Dotted module path of the producing solver, e.g.
            ``"core.solvers.quantum"``.
        netlist_hash: SHA-256 of the source netlist (see :func:`netlist_sha256`),
            or ``None`` if unavailable.
        libraries: Distribution names whose versions to record (e.g.
            ``("numpy", "scipy", "scqubits", "qutip", "h5py")``).
        extra: Optional additional string attrs to record. Higher layers (the
            app or the jjqubit API) use this to inject their own version without
            core taking an upward dependency on them.

    Returns:
        A flat ``str -> str`` mapping suitable for writing as HDF5 attrs.
    """
    attrs: dict[str, Any] = {
        "provenance_version": PROVENANCE_VERSION,
        "generated_by": generated_by,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }
    if netlist_hash is not None:
        attrs["netlist_sha256"] = netlist_hash
    for lib in libraries:
        attrs[f"lib_{lib}"] = _package_version(lib)
    if extra:
        attrs.update(extra)
    return attrs


def write_provenance(
    parent: h5py.Group | h5py.File,
    *,
    generated_by: str,
    netlist_hash: str | None = None,
    libraries: tuple[str, ...] = (),
    extra: dict[str, str] | None = None,
) -> None:
    """Create a ``/provenance`` group under ``parent`` and fill its attrs.

    See :func:`collect_provenance` for the argument meanings.
    """
    group = parent.create_group(PROVENANCE_GROUP)
    for key, value in collect_provenance(
        generated_by=generated_by,
        netlist_hash=netlist_hash,
        libraries=libraries,
        extra=extra,
    ).items():
        group.attrs[key] = value


def read_provenance(parent: h5py.Group | h5py.File) -> dict[str, Any]:
    """Read the ``/provenance`` group's attrs back as a plain dict.

    Returns an empty dict if the file predates provenance (no such group), so
    callers can treat provenance as optional/forward-compatible.
    """
    if PROVENANCE_GROUP not in parent:
        return {}
    group = parent[PROVENANCE_GROUP]
    out: dict[str, Any] = {}
    for key, value in group.attrs.items():
        out[key] = value.decode() if isinstance(value, bytes) else value
    return out
