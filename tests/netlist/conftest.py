"""Pytest bootstrap for the netlist tests.

Ensures the repository root is importable so ``import core.netlist`` works no
matter where pytest is invoked from. This lives inside ``tests/netlist/`` (this
module's owned scope) and touches nothing outside it.
"""
from __future__ import annotations

import pathlib
import sys

# tests/netlist/conftest.py -> parents[2] is the repository root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
