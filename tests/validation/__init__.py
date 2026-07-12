"""Continuous physics-validation suite for JJQubit Studio (Task #7).

A passing test does NOT mean the physics is correct. Every numerical solver in
this project is checked here against known analytic limits and independently
computed reference values (Koch et al., PRA 76, 042319 (2007); a from-scratch
charge-basis diagonalization; a direct QuTiP diagonalization). Numbers always
carry explicit units (GHz, fF, nA, ...) because unit confusion is the single
most common bug source in superconducting-circuit design.
"""
