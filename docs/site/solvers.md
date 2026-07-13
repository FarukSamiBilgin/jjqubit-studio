# Solvers

JJQubit Studio has two solver families under `core/`. Both consume a validated
netlist, never import any GUI code, and can be driven from the command line or
the [Scripting API](scripting.md). Each writes a self-describing HDF5 result
(with a `/provenance` group) that the waveform viewer reads.

```powershell
python -m core.solvers.quantum   examples\transmon_readout.json out_quantum.h5
python -m core.solvers.classical examples\rcsj_bias.json         out_classical.h5
```

## Quantum solver

The quantum solver quantizes a transmon circuit and computes its spectrum,
its dispersive coupling to a readout resonator, and coherence estimates. It is
a thin layer over **scqubits / QuTiP** (validated tools), not a
reimplementation of the physics.

The pipeline, as chained by `jjqubit.solve_quantum`:

1. **Quantization** (`core.solvers.quantum.quantization.quantize_circuit`).
   From the netlist's junction and capacitances it produces `Ej`, `Ec`, and
   `Ej/Ec`. The capacitance matrix is a netlist *input* (a matrix inversion of
   given capacitances), not a geometry solve.
2. **Spectrum** (`compute_transmon_spectrum(Ej_GHz, Ec_GHz)`). Energy levels,
   the 0<->1 transition `E01`, and the anharmonicity (approximately `-Ec` in the
   transmon limit `Ej/Ec >> 1`, one of the analytic-limit validation checks).
3. **Dispersive shift** (`compute_dispersive_shift`). The qubit-resonator
   coupling `g`, the detuning `Delta`, and the dispersive shift `chi`, plus a
   validity flag `dispersive_regime_valid` and the small parameter `|g/Delta|`.
4. **Coherence** (`compute_coherence`). scqubits-based T1 / T2 / Tphi estimates,
   including the Purcell-limited T1 through the resonator.

The returned scalars and their units are surfaced by
`jjqubit.QuantumSolution` — see [Scripting API](scripting.md) for the full list
(`Ej_over_Ec`, `E01_GHz`, `anharmonicity_GHz`, `chi_MHz`, `g_MHz`, `Delta_GHz`,
`T1_us`, `T2_us`, `Tphi_us`, `T1_purcell_us`).

For a two-Josephson-element netlist the solver runs the coupled two-transmon
path instead — see [Multi-qubit](multi-qubit.md).

## Classical solver

The classical solver runs the RCSJ (resistively and capacitively shunted
junction) model and the readout analysis. Which analyses run depends on the
netlist topology (a netlist may yield one or both):

- **RCSJ bias** (junction + current source). Produces:
  - `phase_dynamics` — the time-domain phase trace at the bias current,
    including the DC voltage (`dc_voltage_v`). For `I < Ic` this DC voltage is
    zero, one of the analytic-limit validation checks.
  - `iv_curve` — the hysteretic current-sweep I-V result.
- **Readout** (resonator + transmission line). Produces:
  - `s21_curve` — the transmission S21 curve of the readout circuit.

These are exposed as `jjqubit.ClassicalSolution.rcsj` and `.readout`; see
[Scripting API](scripting.md) for the field paths (for example
`c.rcsj.phase_dynamics.dc_voltage_v`).

## Validation

Every solver has analytic-limit validation tests under `tests/validation/`
(transmon anharmonicity approximately `-Ec`; Cooper-pair-box limit as
`Ej/Ec -> 0`; zero DC voltage below `Ic`; the dispersive shift converging to its
known analytic form; the two-transmon avoided crossing). Numeric results are
always reported with explicit units (GHz, MHz, fF, nA, ...); a passing test does
not by itself make a number correct, so these limit checks are what establish
correctness.
