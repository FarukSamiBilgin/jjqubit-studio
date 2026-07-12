"""Entry point for ``python -m core.solvers.classical <netlist.json> <output.h5>``."""
from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
