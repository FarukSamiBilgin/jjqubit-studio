"""Tests for ``MainWindow``: the app shell tying canvas, project I/O, and run
orchestration together (Task #6).

File dialogs and message boxes are modal in real use, so tests monkeypatch
``QFileDialog``/``QMessageBox`` static methods to return canned answers
instead of driving actual dialog widgets -- a standard headless-Qt-testing
pattern (also keeps these tests fast and deterministic).
"""
from __future__ import annotations

import pathlib

from PySide6.QtWidgets import QFileDialog, QMessageBox

from core.netlist import load

from gui.app import APP_NAME, MainWindow, load_project

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"


def _load_transmon_onto(window: MainWindow) -> None:
    netlist = load(str(EXAMPLES_DIR / "transmon_readout.json"), validate=True)
    window._load_netlist_onto_canvas(netlist)


# -- construction -----------------------------------------------------------------


def test_main_window_constructs_with_expected_widgets(qapp):
    window = MainWindow()
    assert window.windowTitle().startswith(APP_NAME)
    assert window.schematic is not None
    assert window.results_panel is not None
    assert window.run_action.isEnabled()
    assert window.progress_bar.isVisible() is False
    assert window.current_path is None
    assert window._dirty is False


def test_loading_a_netlist_marks_project_dirty(qapp):
    window = MainWindow()
    assert window._dirty is False
    _load_transmon_onto(window)
    assert window._dirty is True
    assert window.windowTitle().endswith("*")


# -- save / open round trip -------------------------------------------------------


def test_save_as_then_reopen_round_trip(qapp, tmp_path, monkeypatch):
    window = MainWindow()
    _load_transmon_onto(window)

    save_path = tmp_path / "myproj.jjq"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(save_path), ""))
    )
    ok = window.save_project_as()

    assert ok is True
    assert window.current_path == str(save_path)
    assert window._dirty is False
    assert save_path.exists()

    window2 = MainWindow()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(save_path), ""))
    )
    window2.open_project()

    assert window2.current_path == str(save_path)
    assert window2._dirty is False
    assert set(window2.schematic.scene.element_items) == set(window.schematic.scene.element_items)


def test_save_project_current_reuses_existing_path(qapp, tmp_path, monkeypatch):
    window = MainWindow()
    _load_transmon_onto(window)
    save_path = tmp_path / "proj.jjq"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(save_path), ""))
    )
    assert window.save_project_as() is True

    # Edit through the property panel (the real user-facing edit path, not a
    # direct model mutation) then Save (not Save As) should write back to the
    # same path without prompting again.
    window.schematic.properties.show_element("J1")
    window.schematic.properties._value_boxes["Ic"].setValue(22.0)
    assert window._dirty is True

    def _fail_if_called(*a, **k):
        raise AssertionError("Save should not re-prompt for a path")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_fail_if_called))
    assert window.save_project_current() is True
    assert window._dirty is False

    reloaded = load_project(save_path, validate=True)
    assert reloaded.netlist.element_by_id("J1").params["Ic"].value == 22.0


# -- new project (with unsaved-changes prompt) ------------------------------------


def test_new_project_discards_after_confirmation(qapp, monkeypatch):
    window = MainWindow()
    _load_transmon_onto(window)
    assert window._dirty is True

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Discard)
    )
    window.new_project()

    assert window.current_path is None
    assert window._dirty is False
    assert window.schematic.scene.model.elements == {}


def test_new_project_cancelled_keeps_state(qapp, monkeypatch):
    window = MainWindow()
    _load_transmon_onto(window)

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Cancel)
    )
    window.new_project()

    # Cancelled: the dirty circuit should still be there.
    assert window._dirty is True
    assert len(window.schematic.scene.model.elements) > 0


# -- run orchestration -------------------------------------------------------------


def test_run_solver_blocked_on_invalid_netlist(qapp, monkeypatch):
    window = MainWindow()
    window.schematic.scene.model.add_element("capacitor", element_id="C1")  # unwired: invalid

    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **k: warnings.append(text) or QMessageBox.Ok),
    )

    window.run_solver()

    assert window._worker is None
    assert len(warnings) == 1


def test_run_solver_success_populates_results_panel(qapp):
    window = MainWindow()
    _load_transmon_onto(window)
    window.solver_combo.setCurrentText("quantum")

    window.run_solver()
    assert window._worker is not None
    assert window._worker.wait(30_000)
    for _ in range(5):
        qapp.processEvents()

    assert window.project.last_run is not None
    assert window.project.last_run.status == "success"
    assert window.project.last_run.solver == "quantum"
    assert pathlib.Path(window.project.last_run.output_path).exists()
    assert "Result ready" in window.results_panel._label.text()


def test_run_solver_failure_recorded_in_last_run(qapp, monkeypatch):
    from gui import app as app_module

    window = MainWindow()
    _load_transmon_onto(window)

    def raising_runner(netlist_path, output_path, report):
        raise RuntimeError("synthetic solver failure")

    monkeypatch.setitem(app_module.SOLVER_RUNNERS, "quantum", raising_runner)
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))

    window.run_solver()
    assert window._worker is not None
    assert window._worker.wait(30_000)
    for _ in range(5):
        qapp.processEvents()

    assert window.project.last_run is not None
    assert window.project.last_run.status == "error"
    assert "synthetic solver failure" in window.project.last_run.message
