# Scripting API (`jjqubit`)

`jjqubit` is the GUI-free entry point for driving the solver core from a script
or notebook, so parameter sweeps and batch runs do not need the schematic
editor. It is a thin, faithful layer over `core.solvers.*`: it reuses the exact
same code paths the CLIs and GUI use (no physics is reimplemented), never
imports PySide6, and defers the heavy scientific imports (scqubits / QuTiP)
into the solve functions, so `import jjqubit` itself stays cheap.

The public surface (`jjqubit.__all__`):

```python
import jjqubit

jjqubit.load_netlist        # load + validate a netlist JSON
jjqubit.solve_quantum       # single-qubit transmon + dispersive + coherence
jjqubit.solve_two_qubit     # two capacitively-coupled transmons
jjqubit.solve_classical     # RCSJ / I-V / phase dynamics / readout S21
jjqubit.QuantumSolution     # result of solve_quantum
jjqubit.TwoQubitSolution    # result of solve_two_qubit
jjqubit.ClassicalSolution   # result of solve_classical
```

## `load_netlist(path)`

```python
net = jjqubit.load_netlist("examples/transmon_readout.json")
```

Loads and validates a netlist JSON file (the frozen `core.netlist` format) and
returns a `core.netlist.Netlist`. Raises `core.netlist.NetlistError` on a
schema / unit / validation problem. Every `solve_*` function also accepts a path
directly, so calling `load_netlist` first is optional.

## `solve_quantum(netlist) -> QuantumSolution`

Quantizes a netlist and computes its transmon spectrum, dispersive shift, and
coherence estimates. `netlist` may be a loaded `Netlist` or a path.

```python
q = jjqubit.solve_quantum(net)

# Charging / Josephson energies (GHz) and their ratio:
print(q.Ej_GHz, q.Ec_GHz, q.Ej_over_Ec)
print(q.EjMax_GHz, q.flux, q.is_tunable)   # squid-aware accessors

# Spectrum:
print(q.E01_GHz, q.anharmonicity_GHz)      # GHz

# Dispersive coupling to the readout resonator:
print(q.g_MHz, q.chi_MHz, q.Delta_GHz)     # g and chi in MHz, Delta in GHz
print(q.g_over_Delta, q.dispersive_valid)  # perturbative-validity check

# Coherence estimates (scqubits-based), in microseconds:
print(q.T1_us, q.T2_us, q.Tphi_us, q.T1_purcell_us)

# A flat dict of headline scalars, handy for building tables:
q.summary()   # {"Ej_GHz", "Ec_GHz", "Ej_over_Ec", "E01_GHz",
              #  "anharmonicity_GHz", "g_MHz", "chi_MHz", "Delta_GHz"}

# Same HDF5 the CLI and GUI waveform viewer read:
q.write_hdf5("out_quantum.h5")
```

`QuantumSolution` also exposes the live underlying objects if you need more than
the convenience accessors: `q.quantization`, `q.spectrum`, `q.dispersive`,
`q.coherence`. Units are GHz unless an accessor's name says otherwise
(`_MHz`, `_us`).

Note: the accessor names are `Ej_over_Ec`, `E01_GHz`, `anharmonicity_GHz`,
`chi_MHz`, `T1_us` / `T2_us`, and `T1_purcell_us` (the Purcell-limited T1).

## `solve_two_qubit(netlist, *, evals_count=6) -> TwoQubitSolution`

Solves a two-capacitively-coupled-transmon netlist for its coupled spectrum.
See [Multi-qubit](multi-qubit.md) for the physics.

```python
r = jjqubit.solve_two_qubit("examples/two_transmon.json")

print(r.omega1_GHz, r.omega2_GHz, r.detuning_GHz)   # bare frequencies, GHz
print(r.J_GHz, r.J_MHz)                             # exchange coupling J
print(r.one_excitation_splitting_GHz)               # = 2J at resonance
print(r.zz_MHz)                                     # static ZZ (NaN at resonance)
print(r.iswap_gate_time_ns)                         # 1/(4J), inf if uncoupled
print(r.anharmonicity1_MHz, r.anharmonicity2_MHz)
print(r.g_MHz, r.Cc_fF)                             # charge coupling, coupling cap

r.write_hdf5("out_2q.h5")
```

## `solve_classical(netlist) -> ClassicalSolution`

Runs the classical RCSJ / I-V / phase-dynamics / readout-S21 analysis. Whichever
of the RCSJ-bias and readout topologies the netlist contains is computed; a
netlist with neither raises `ValueError`.

```python
c = jjqubit.solve_classical("examples/rcsj_bias.json")

if c.rcsj is not None:
    print(c.rcsj.phase_dynamics.dc_voltage_v)   # 0 for I < Ic
    print(c.rcsj.iv_curve)                       # hysteretic current sweep

if c.readout is not None:
    print(c.readout.s21_curve)                   # readout transmission S21

c.write_hdf5("out_classical.h5")
```

`c.rcsj` is present when the netlist has an RCSJ bias topology (junction +
current source); `c.readout` is present when it has a resonator +
transmission-line readout topology. A netlist may yield one or both.

## `write_hdf5(path)`

Every solution object has a `write_hdf5(path)` method that writes the result in
the exact HDF5 layout the CLI and GUI use, including a `/provenance` group (the
SHA-256 of the source netlist plus solver and library versions). Parent
directories are created as needed.

## Sweep examples

`examples/` ships three sweep scripts, each built entirely on this public API
(they never import the GUI). Run them from the repository root:

```powershell
python examples\sweep_transmon.py   # sweep junction Ic; E01 / anharmonicity / chi vs Ej/Ec
python examples\sweep_flux.py       # tune a squid transmon across the flux arc
python examples\sweep_coupling.py   # two coupled qubits: trace the avoided crossing
```

### `sweep_transmon.py`

Loads `examples/transmon_readout.json`, finds the single junction, scales its
`Ic` across `(0.5, 0.75, 1.0, 1.5, 2.0, 3.0)`, runs `solve_quantum` for each,
and tabulates `Ej/Ec`, `E01_GHz`, `anharmonicity_GHz`, `chi_MHz`, `|g/Delta|`,
and the `dispersive_valid` flag. As `Ic` grows, E01 sweeps up through the
resonator and eventually leaves the dispersive regime; the script silences the
solver's `DispersiveRegimeWarning` and reports validity as a column instead.
Parameters are edited by copying the netlist and replacing the junction's `Ic`
`Quantity`:

```python
from core.netlist.units import Quantity
ic = junction.params["Ic"]
junction.params["Ic"] = Quantity(value=ic.value * factor, unit=ic.unit)
```

### `sweep_flux.py`

Loads `examples/tunable_transmon.json`, finds the `squid`, and sweeps its
external `flux` (Phi/Phi0) over `(0.0, 0.1, 0.2, 0.3, 0.4, 0.45)`, tabulating
`Ej_GHz`, `Ej/Ec`, `E01_GHz`, and the anharmonicity — the classic transmon
flux arc. The flux is set with a dimensionless `Quantity`:

```python
squid.params["flux"] = Quantity(value=flux, unit="")
```

### `sweep_coupling.py`

Loads `examples/two_transmon.json` and detunes qubit 2 across qubit 1 by
scaling the `J2` junction's `Ic` over `(0.85, 0.92, 0.96, 1.0, 1.04, 1.08,
1.15)`, calling `solve_two_qubit` for each and tabulating the bare frequencies,
detuning, single-excitation splitting, `J`, and `ZZ`. The splitting is minimal
at resonance, where it equals `2J` (the avoided crossing); `ZZ` is `NaN` at
exact resonance, which the script prints as `n/a (res)`.
