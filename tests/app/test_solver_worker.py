"""Tests for the ``SolverWorker`` QThread scaffolding (Task #6).

Two layers are covered:

1. The threading mechanism itself is generic -- exercised with a fake runner
   registered on the fly, independent of any real solver.
2. Both real backends registered in ``SOLVER_RUNNERS`` ("quantum" from Task
   #3, "classical" from Task #2) are run end to end against their real
   packages. Both shell out to their CLI (``python -m core.solvers.<name>``)
   rather than importing scqubits/QuTiP in-process -- see
   ``_make_cli_solver_runner``'s docstring in ``gui/app.py`` for why (a
   QThread + in-process scqubits call crashed with a Windows access
   violation during development of this module).

Cross-thread Qt signals use queued connections, which only get dispatched
when the receiving thread's event loop runs; ``worker.wait()`` blocks until
the background ``run()`` returns, then ``qapp.processEvents()`` drains the
queued signal emissions into the plain Python lists these tests inspect.
"""

from __future__ import annotations

import pathlib

import h5py
from core.netlist import dump
from gui.app import SOLVER_RUNNERS, SolverWorker

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"


def _drain(qapp, worker, timeout_ms: int = 30_000) -> None:
    assert worker.wait(timeout_ms), "worker did not finish in time"
    for _ in range(5):
        qapp.processEvents()


# -- generic threading mechanism (fake runner) -----------------------------------


def test_worker_dispatches_to_registered_runner_and_reports_progress(
    qapp, tmp_path, monkeypatch
):
    calls: list[tuple[int, str]] = []

    def fake_runner(netlist_path, output_path, report):
        report(0, "starting")
        report(50, "halfway")
        pathlib.Path(output_path).write_text("done", encoding="utf-8")
        report(100, "done")

    monkeypatch.setitem(SOLVER_RUNNERS, "fake", fake_runner)

    out_path = tmp_path / "out.txt"
    worker = SolverWorker("fake", "unused.json", str(out_path))
    worker.progress.connect(lambda p, m: calls.append((p, m)))
    succeeded: list[str] = []
    failed: list[str] = []
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(failed.append)

    worker.start()
    _drain(qapp, worker)

    assert failed == []
    assert succeeded == [str(out_path)]
    assert calls[0] == (0, "starting")
    assert calls[-1] == (100, "done")
    assert out_path.read_text(encoding="utf-8") == "done"


def test_worker_reports_runner_exception_as_failure(qapp, monkeypatch):
    def raising_runner(netlist_path, output_path, report):
        raise ValueError("boom")

    monkeypatch.setitem(SOLVER_RUNNERS, "fake-raising", raising_runner)

    worker = SolverWorker("fake-raising", "unused.json", "unused.h5")
    succeeded: list[str] = []
    failed: list[str] = []
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(failed.append)

    worker.start()
    _drain(qapp, worker)

    assert succeeded == []
    assert len(failed) == 1
    assert "boom" in failed[0]


def test_worker_unregistered_solver_fails_cleanly(qapp):
    worker = SolverWorker("no-such-solver", "unused.json", "unused.h5")
    succeeded: list[str] = []
    failed: list[str] = []
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(failed.append)

    worker.start()
    _drain(qapp, worker)

    assert succeeded == []
    assert len(failed) == 1
    assert "no-such-solver" in failed[0]


# -- real "quantum" backend integration (Task #3) --------------------------------


def test_quantum_runner_is_registered():
    assert "quantum" in SOLVER_RUNNERS


def test_quantum_runner_end_to_end_succeeds(qapp, tmp_path):
    out_path = tmp_path / "result.h5"
    worker = SolverWorker(
        "quantum", str(EXAMPLES_DIR / "transmon_readout.json"), str(out_path)
    )
    progress: list[tuple[int, str]] = []
    succeeded: list[str] = []
    failed: list[str] = []
    worker.progress.connect(lambda p, m: progress.append((p, m)))
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(failed.append)

    worker.start()
    _drain(qapp, worker)

    assert failed == []
    assert succeeded == [str(out_path)]
    assert progress[0][0] == 5
    assert progress[-1][0] == 100
    assert out_path.exists()

    with h5py.File(out_path, "r") as f:
        assert f.attrs["format"] == "jjqubit-quantum-result"
        assert "qubit" in f
        assert "resonator" in f
        assert "coupling" in f


def test_quantum_runner_reports_invalid_netlist_as_failure(qapp, tmp_path):
    from core.netlist import Element, Netlist, Quantity

    invalid = Netlist(
        name="floating",
        elements=[
            Element(id="C1", type="capacitor", params={"C": Quantity(1.0, "fF")})
        ],
    )
    netlist_path = tmp_path / "invalid.json"
    dump(invalid, netlist_path, validate=False)

    worker = SolverWorker("quantum", str(netlist_path), str(tmp_path / "out.h5"))
    succeeded: list[str] = []
    failed: list[str] = []
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(failed.append)

    worker.start()
    _drain(qapp, worker)

    assert succeeded == []
    assert len(failed) == 1
    assert "quantum solver failed" in failed[0].lower()


# -- real "classical" backend integration (Task #2) ------------------------------


def test_classical_runner_is_registered():
    assert "classical" in SOLVER_RUNNERS


def test_classical_runner_end_to_end_succeeds(qapp, tmp_path):
    out_path = tmp_path / "result.h5"
    worker = SolverWorker(
        "classical", str(EXAMPLES_DIR / "rcsj_bias.json"), str(out_path)
    )
    succeeded: list[str] = []
    failed: list[str] = []
    worker.succeeded.connect(succeeded.append)
    worker.failed.connect(failed.append)

    worker.start()
    _drain(qapp, worker)

    assert failed == []
    assert succeeded == [str(out_path)]
    assert out_path.exists()

    with h5py.File(out_path, "r") as f:
        assert f.attrs["generated_by"] == "core.solvers.classical"
        assert "rcsj" in f
