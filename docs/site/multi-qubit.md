# Multi-qubit

The first multi-qubit capability (Faz 2) is two **capacitively-coupled
transmons**. It composes two `scqubits.Transmon` objects into a joint Hilbert
space with a charge-charge interaction and diagonalizes it, using the same
`scqubits.HilbertSpace` machinery the dispersive solver already uses — no new
dependency, no physics reimplemented.

The implementation is `core.solvers.quantum.multiqubit`; the scriptable entry
point is `jjqubit.solve_two_qubit` (see [Scripting API](scripting.md)).

## The joint spectrum and the avoided crossing

Two coupled qubits form the single-excitation manifold `{|10>, |01>}`, which
becomes an avoided crossing as the qubits are tuned through resonance. The
one-excitation eigenvalues are

```
E_pm = (w1 + w2)/2  +/-  sqrt( (Delta/2)^2 + J^2 ),   Delta = w1 - w2
```

so their splitting is `2*sqrt((Delta/2)^2 + J^2)` — minimal (equal to `2J`)
exactly on resonance. The solver inverts this relation to report the exchange
coupling `J` from the measured single-excitation splitting and the bare
detuning.

`examples/sweep_coupling.py` traces exactly this: detune qubit 2 across qubit 1
and watch the splitting bottom out at `2J`. Far from resonance the splitting is
just the bare detuning.

## What the solver reports

`compute_two_transmon_spectrum` returns a `TwoTransmonResult` (surfaced by
`jjqubit.TwoQubitSolution`):

- **`omega1_GHz`, `omega2_GHz`** — the two bare (uncoupled) 0<->1 frequencies.
- **`detuning_GHz`** — `omega1 - omega2`.
- **`J_GHz`** (also `J_MHz`) — the exchange coupling, always `>= 0`, extracted
  from the single-excitation avoided crossing.
- **`one_excitation_splitting_GHz`** — the gap between the two lowest excited
  joint levels; minimal (`= 2J`) on resonance.
- **`zz_MHz`** — the static ZZ interaction `E11 - E10 - E01 + E00`: the
  always-on frequency shift of one qubit conditioned on the other, and the
  dominant coherent error in fixed-coupling multi-qubit chips. It is `NaN` at
  exact resonance, where the bare `|10>` / `|01>` product states are fully
  hybridized and cannot be individually labeled.
- **`iswap_gate_time_ns`** — the time for a full resonant iSWAP, `1/(4J)` in ns
  (`inf` when the qubits are uncoupled). The population swaps between `|10>` and
  `|01>` at frequency `2J`, so a full swap takes `1/(4J)`.
- **`anharmonicity1_MHz`, `anharmonicity2_MHz`** — per-qubit anharmonicities
  `(E12 - E01)`, negative for a transmon.
- **`coupled_levels_GHz`** — the low-lying joint eigenenergies relative to the
  joint ground state.

The static ZZ is computed from the dressed-state lookup, identifying the joint
levels adiabatically connected to the bare products `|00>, |10>, |01>, |11>`.
At exact resonance that lookup cannot assign `|10>` versus `|01>`, so ZZ is
reported as `NaN` there.

## From coupling capacitance to the charge coupling g

The diagonalization itself is parameterized by the charge-coupling coefficient
`g` of the interaction `H_int = g * n1 * n2`, **not** by a coupling capacitance
directly. Mapping a netlist coupling capacitor to `g` is a separate,
separately validated step, `quantize_two_qubit_circuit`.

Given the two island-to-ground capacitances `C1`, `C2` and the island-to-island
coupling capacitance `Cc`, the Maxwell capacitance matrix is

```
C = [[C1 + Cc,   -Cc  ],
     [  -Cc,   C2 + Cc]]
```

Its inverse gives the charging-energy matrix. On the diagonal,
`Ec_i = e^2 (C^-1)_ii / 2` (so each `Ec` already includes the coupler's small
renormalization of its island); off-diagonal, the coupling is
`g = 4 e^2 (C^-1)_12` (the coefficient of `n1 n2`). This is a capacitance-matrix
*inversion* of netlist inputs, not a geometry solve — consistent with the
project's scope decision that the capacitance matrix is an input, not an output.

`quantize_two_qubit_circuit` returns a `TwoQubitQuantization` with `Ej1_GHz`,
`Ec1_GHz`, `Ej2_GHz`, `Ec2_GHz`, `g_GHz`, `Cc_fF`, and the raw two-qubit
topology. `jjqubit.solve_two_qubit` chains this with the diagonalization and
also exposes `g_MHz` and `Cc_fF` on the result.

## HDF5 output

Two-qubit runs write a distinct HDF5 format (`jjqubit-two-qubit-result`,
version `1.0`) via `write_two_qubit_hdf5` / `TwoQubitSolution.write_hdf5`.
Layout:

```
/ (root)     attrs: format, version, generated_by, netlist_name
/provenance                (solver + library versions, netlist hash)
/qubits      attrs: Ej1_GHz, Ec1_GHz, Ej2_GHz, Ec2_GHz, g_GHz, Cc_fF
/coupled     attrs: omega1_GHz, omega2_GHz, detuning_GHz, J_GHz,
                    one_excitation_splitting_GHz, zz_MHz,
                    anharmonicity1_MHz, anharmonicity2_MHz, iswap_gate_time_ns
             dataset: coupled_levels_GHz (float64[n], unit="GHz")
```

The netlist for this lives at `examples/two_transmon.json`: two transmons, each
with a shunt capacitor, bridged by a coupling capacitor. From the command line
the quantum solver auto-detects the two-Josephson-element topology and runs this
coupled path:

```powershell
python -m core.solvers.quantum examples\two_transmon.json out_2q.h5
```
