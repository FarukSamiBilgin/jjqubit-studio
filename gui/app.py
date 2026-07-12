"""Main application window for JJQubit Studio (Task #6): app shell + integration.

This module owns the top-level desktop app that ties the other teammates'
pieces together, per the netlist contract in ``docs/task.md`` / ``CLAUDE.md``::

    Schematic canvas [GUI]  -->  netlist (JSON) [CONTRACT]  -->  solver [CORE]
                                                                     |
                                                                     v
    Waveform viewer [GUI]   <--  HDF5 result   <-----------------------

Responsibilities:

* The main window: menu, toolbar, embedded :class:`~gui.schematic.SchematicEditor`
  canvas, and a results panel (a placeholder until ``waveform-ui``/Task #5
  lands -- see :class:`_ResultPlaceholder`).
* ``.jjq`` project files: netlist JSON (via :mod:`core.netlist`) plus a small
  metadata envelope (app version, last-run info). See :func:`save_project`,
  :func:`load_project`.
* Worker-thread scaffolding (:class:`SolverWorker`) so a long solver run never
  freezes the GUI thread. Solvers are registered in :data:`SOLVER_RUNNERS`;
  only ``"quantum"`` (Task #3) is wired in today, ``"classical"`` (Task #2)
  is added the same way once it reports done.

This module does no physics of its own: it only calls into ``core.netlist``
and ``core.solvers.*`` and displays what comes back, per the GUI/core split
in ``CLAUDE.md``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.netlist import (
    Netlist,
    NetlistError,
    ValidationError,
    dump,
    from_dict,
    to_dict,
)
from gui.schematic import SchematicEditor

__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "PROJECT_FORMAT",
    "PROJECT_SCHEMA_VERSION",
    "ProjectError",
    "LastRunInfo",
    "ProjectState",
    "project_to_dict",
    "project_from_dict",
    "save_project",
    "load_project",
    "SolverWorker",
    "SOLVER_RUNNERS",
    "MainWindow",
    "main",
]

APP_NAME = "JJQubit Studio"
APP_VERSION = "0.1.0"

# The ".jjq" project file envelope (distinct from the frozen netlist schema
# version, which is carried unchanged inside the embedded "netlist" object).
PROJECT_FORMAT = "jjqubit-project"
PROJECT_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# .jjq project file: netlist + metadata
# ---------------------------------------------------------------------------


class ProjectError(Exception):
    """Raised when a ``.jjq`` file's top-level envelope is malformed.

    Problems inside the embedded netlist itself raise
    :class:`core.netlist.NetlistError` (or a subclass) instead, so callers can
    reuse the same netlist-error handling the schematic editor already has.
    """


@dataclass
class LastRunInfo:
    """Metadata about the most recent solver run recorded in a project.

    Args:
        solver: Name of the solver backend that produced (or attempted) the
            result, e.g. ``"quantum"`` or ``"classical"``.
        output_path: Path to the HDF5 result file. Recorded even on failure
            (as the path that was *attempted*) for traceability; may not
            exist on disk.
        status: ``"success"`` or ``"error"``.
        message: Human-readable detail: a short success summary, or the error
            text shown to the user.
        timestamp: ISO-8601 UTC timestamp of when the run finished.
    """

    solver: str
    output_path: str
    status: str
    message: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-ready dict."""
        return {
            "solver": self.solver,
            "output_path": self.output_path,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "LastRunInfo":
        """Build a :class:`LastRunInfo` from a mapping.

        Raises:
            ProjectError: if ``data`` is not an object.
        """
        if not isinstance(data, dict):
            raise ProjectError(
                f"'last_run' must be an object, got {type(data).__name__}"
            )
        return cls(
            solver=str(data.get("solver", "")),
            output_path=str(data.get("output_path", "")),
            status=str(data.get("status", "")),
            message=str(data.get("message", "")),
            timestamp=str(data.get("timestamp", "")),
        )


@dataclass
class ProjectState:
    """In-memory state of a ``.jjq`` project: the circuit plus run metadata.

    Args:
        netlist: The circuit, in the frozen :mod:`core.netlist` contract.
        app_version: App version string the project was last saved with.
        last_run: Metadata about the most recent solver run, if any.
    """

    netlist: Netlist
    app_version: str = APP_VERSION
    last_run: Optional[LastRunInfo] = None


def project_to_dict(state: ProjectState) -> dict[str, Any]:
    """Serialize a :class:`ProjectState` to a plain JSON-ready dict.

    The embedded netlist is serialized with :func:`core.netlist.to_dict`, so
    the frozen netlist schema (``format``/``version`` fields, element/param
    layout) is preserved unchanged inside the ``"netlist"`` key.
    """
    return {
        "format": PROJECT_FORMAT,
        "version": PROJECT_SCHEMA_VERSION,
        "app_version": state.app_version,
        "netlist": to_dict(state.netlist),
        "last_run": state.last_run.to_dict() if state.last_run is not None else None,
    }


def project_from_dict(data: Any) -> ProjectState:
    """Build a :class:`ProjectState` from a ``.jjq``-shaped dict.

    Raises:
        ProjectError: if the top-level ``.jjq`` envelope is malformed (wrong
            / missing ``format``, missing ``netlist``).
        core.netlist.NetlistError: if the embedded netlist itself is
            malformed (propagated from :func:`core.netlist.from_dict`).
    """
    if not isinstance(data, dict):
        raise ProjectError(f"project file must be an object, got {type(data).__name__}")
    fmt = data.get("format")
    if fmt != PROJECT_FORMAT:
        raise ProjectError(
            f"unexpected project format {fmt!r} (expected {PROJECT_FORMAT!r})"
        )
    netlist_data = data.get("netlist")
    if netlist_data is None:
        raise ProjectError("project file is missing 'netlist'")
    netlist = from_dict(netlist_data)
    last_run_data = data.get("last_run")
    last_run = LastRunInfo.from_dict(last_run_data) if last_run_data is not None else None
    return ProjectState(
        netlist=netlist,
        app_version=str(data.get("app_version", "")),
        last_run=last_run,
    )


def save_project(state: ProjectState, path: str | Path, *, validate: bool = False) -> None:
    """Write ``state`` to ``path`` as a ``.jjq`` project file (UTF-8 JSON).

    Args:
        state: The project state to serialize.
        path: Destination file path (any extension; ``.jjq`` by convention).
        validate: If ``True``, validate the embedded netlist before writing
            and raise on failure. Default ``False`` so a work-in-progress
            circuit (e.g. mid-edit, not yet fully wired) can always be saved
            -- mirrors :meth:`gui.schematic.SchematicEditor.save_netlist_file`.

    Raises:
        core.netlist.ValidationError: if ``validate`` is ``True`` and the
            netlist is invalid.
    """
    if validate:
        state.netlist.validate()
    text = json.dumps(project_to_dict(state), indent=2, ensure_ascii=False)
    Path(path).write_text(text + "\n", encoding="utf-8")


def load_project(path: str | Path, *, validate: bool = False) -> ProjectState:
    """Read a ``.jjq`` project file from ``path``.

    Args:
        path: Source file path.
        validate: If ``True``, validate the embedded netlist after loading.

    Raises:
        ProjectError: if the top-level ``.jjq`` envelope is malformed, or the
            file does not contain valid JSON.
        core.netlist.NetlistError: if the embedded netlist is malformed, or
            (when ``validate=True``) semantically invalid.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectError(f"invalid JSON in project file: {exc}") from exc
    state = project_from_dict(data)
    if validate:
        state.netlist.validate()
    return state


# ---------------------------------------------------------------------------
# Worker-thread scaffolding: run a solver without freezing the GUI
# ---------------------------------------------------------------------------

#: A progress callback a solver runner calls with (0-100 percent, short message).
ProgressCallback = Callable[[int, str], None]

#: A solver runner: (netlist_path, output_path, progress_callback) -> None.
#: Must raise on failure (caught and shown to the user by SolverWorker.run);
#: must not touch any Qt object (it runs on a background thread).
SolverRunner = Callable[[str, str, ProgressCallback], None]


# Repository root, used to run solver CLIs as subprocesses with a known cwd.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_quantum_solver(netlist_path: str, output_path: str, report: ProgressCallback) -> None:
    """Run the quantum solver (Task #3) end to end via its CLI, as a subprocess.

    Runs ``python -m core.solvers.quantum <netlist_path> <output_path>`` (see
    :mod:`core.solvers.quantum.cli`) in a separate OS process rather than
    importing scqubits/QuTiP in-process on this worker thread. This is
    deliberate, not a stylistic choice: calling scqubits' sparse-eigensolver
    path directly from a ``QThread`` was found to crash the whole app with a
    Windows access violation (native BLAS/LAPACK code is not safe to run on
    an arbitrary non-main OS thread inside the GUI process). Running it as a
    subprocess isolates that native numerics from the GUI process entirely --
    if the solver crashes, only the subprocess dies and the GUI can still
    report a clean error.

    Raises:
        RuntimeError: if the subprocess exits with a non-zero code (message
            includes its stderr/stdout) or does not produce the expected
            output file.
    """
    report(5, "Launching quantum solver subprocess...")
    proc = subprocess.run(
        [sys.executable, "-m", "core.solvers.quantum", str(netlist_path), str(output_path)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )
    report(90, "Quantum solver finished, checking result...")
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
        raise RuntimeError(f"Quantum solver failed: {detail}")
    if not Path(output_path).exists():
        raise RuntimeError(
            "Quantum solver reported success but did not produce an output file."
        )
    report(100, "Done.")


# Registry of available solver backends, keyed by the name shown in the "Run"
# solver selector / recorded in LastRunInfo.solver. solver-classical (Task #2)
# is added the same way once it reports done via `main` -- nothing else in
# this module needs to change.
SOLVER_RUNNERS: dict[str, SolverRunner] = {
    "quantum": _run_quantum_solver,
}


class SolverWorker(QThread):
    """Runs one solver backend on a background thread so the GUI never blocks.

    Deliberately generic: it dispatches to :data:`SOLVER_RUNNERS` by name
    rather than hardcoding solver-specific logic, so wiring in
    solver-classical later is a one-line registry addition, not a change to
    this class or to :class:`MainWindow`'s threading logic.

    Signals:
        progress(int, str): percent complete (0-100) and a short status
            message, forwarded from the runner as it works.
        succeeded(str): the solver finished; carries the output HDF5 path.
        failed(str): the solver could not complete; carries a message that is
            safe to show directly to the user (not a raw traceback).
    """

    progress = Signal(int, str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        solver_name: str,
        netlist_path: str,
        output_path: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.solver_name = solver_name
        self.netlist_path = netlist_path
        self.output_path = output_path

    def run(self) -> None:  # noqa: D102 - QThread.run() override
        runner = SOLVER_RUNNERS.get(self.solver_name)
        if runner is None:
            self.failed.emit(
                f"Solver {self.solver_name!r} is not wired up yet."
            )
            return

        def report(percent: int, message: str) -> None:
            self.progress.emit(percent, message)

        try:
            runner(self.netlist_path, self.output_path, report)
        except ValidationError as exc:
            joined = "\n".join(f"- {e}" for e in exc.errors)
            self.failed.emit(f"Netlist is invalid:\n{joined}")
        except NetlistError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - last resort: never crash silently
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.succeeded.emit(self.output_path)


def _utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class _ResultPlaceholder(QWidget):
    """Stand-in for the waveform viewer (Task #5) until it is embeddable.

    Shows where the HDF5 result path lands after a successful run. Replace
    :meth:`show_result` (and the widget itself, in
    :meth:`MainWindow._build_ui`) with the real
    ``gui.waveform`` viewer once waveform-ui reports done -- everything else
    in :class:`MainWindow` talks to this panel only through
    :meth:`show_result`, so the swap is localized to those two spots.
    """

    def __init__(self) -> None:
        super().__init__()
        self._label = QLabel(
            "No result yet.\n\nBuild a circuit, click Run, and the HDF5 "
            "result path will be shown here.\n\n"
            "(Waveform viewer panel is a placeholder pending Task #5.)"
        )
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)

    def show_result(self, output_path: str) -> None:
        """Report that a solver run finished and produced ``output_path``."""
        self._label.setText(
            f"Result ready:\n{output_path}\n\n"
            "(Waveform viewer panel is a placeholder pending Task #5 -- "
            "once embedded, it will load and plot this HDF5 file directly.)"
        )


class MainWindow(QMainWindow):
    """JJQubit Studio's main window: menu, toolbar, canvas, and run orchestration.

    Embeds :class:`~gui.schematic.SchematicEditor` as the schematic canvas and
    a placeholder results panel (see :class:`_ResultPlaceholder`) side by
    side. "Run" builds a netlist from the canvas, validates it, and runs the
    selected solver on a background thread (:class:`SolverWorker`) so the GUI
    stays responsive.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)

        self.project = ProjectState(netlist=Netlist(name="Untitled"))
        self.current_path: Optional[str] = None
        self._dirty = False
        self._worker: Optional[SolverWorker] = None

        self.schematic = SchematicEditor()
        self.results_panel = _ResultPlaceholder()
        # Two distinct edit paths need to mark the project dirty: structural
        # changes (add/remove/wire/load an element) go through
        # SchematicScene.model_changed, but parameter edits made through the
        # property panel go directly to CanvasModel.set_param and are only
        # observable via PropertyPanel.param_changed -- see
        # gui/schematic/property_panel.py's docstring. Both must be wired up
        # for "unsaved changes" tracking to be accurate.
        self.schematic.scene.model_changed.connect(self._mark_dirty)
        self.schematic.properties.param_changed.connect(lambda *_args: self._mark_dirty())

        self._build_ui()
        self._update_title()

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        splitter = QSplitter()
        splitter.addWidget(self.schematic)
        splitter.addWidget(self.results_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self._build_menu()
        self._build_toolbar()

        status_bar = QStatusBar()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(240)
        status_bar.addPermanentWidget(self.progress_bar)
        self.setStatusBar(status_bar)
        status_bar.showMessage("Ready.")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        new_action = QAction("&New Project", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Project...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_project)
        file_menu.addAction(open_action)

        save_action = QAction("&Save Project", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project_current)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save Project &As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        run_menu = self.menuBar().addMenu("&Run")
        self.run_action = QAction("&Run Solver", self)
        self.run_action.setShortcut("F5")
        self.run_action.triggered.connect(self.run_solver)
        run_menu.addAction(self.run_action)

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self.run_action)
        toolbar.addWidget(QLabel(" Solver: "))

        self.solver_combo = QComboBox()
        # Both entries are listed even though only "quantum" is wired up yet
        # (SOLVER_RUNNERS): picking "classical" fails cleanly through the same
        # SolverWorker path once solver-classical is registered.
        self.solver_combo.addItems(["quantum", "classical"])
        toolbar.addWidget(self.solver_combo)

    def _load_netlist_onto_canvas(self, netlist: Netlist) -> None:
        """Replace the canvas contents with ``netlist``.

        ``SchematicScene.load_netlist`` rebuilds a fresh ``CanvasModel``, so
        ``PropertyPanel`` (constructed once against the *original* model) must
        be re-pointed at the new one too -- mirrors what
        ``SchematicEditor.load_netlist_file`` does for the file-based path;
        ``.jjq`` projects carry the netlist in-memory instead of on disk, so
        this method exists to do the same two steps for that path.
        """
        self.schematic.scene.load_netlist(netlist)
        self.schematic.properties.model = self.schematic.scene.model
        self.schematic.properties.clear()

    # -- title / dirty tracking ----------------------------------------------

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._update_title()

    def _update_title(self) -> None:
        name = Path(self.current_path).name if self.current_path else "Untitled"
        star = "*" if self._dirty else ""
        self.setWindowTitle(f"{APP_NAME} - {name}{star}")

    def _confirm_discard_changes(self) -> bool:
        """Ask the user to save/discard/cancel if there are unsaved changes.

        Returns:
            True if the caller may proceed (nothing to lose, changes were
            saved, or the user chose to discard); False if the action should
            be aborted (user cancelled, or the save failed/was cancelled).
        """
        if not self._dirty:
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved changes",
            "The current project has unsaved changes. Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if choice == QMessageBox.Cancel:
            return False
        if choice == QMessageBox.Discard:
            return True
        return self.save_project_current()

    # -- File menu actions ----------------------------------------------------

    def new_project(self) -> None:
        """Discard the current circuit and start a fresh, empty project."""
        if not self._confirm_discard_changes():
            return
        self.project = ProjectState(netlist=Netlist(name="Untitled"))
        self._load_netlist_onto_canvas(self.project.netlist)
        self.current_path = None
        self._dirty = False
        self._update_title()
        self.statusBar().showMessage("New project.")

    def open_project(self) -> None:
        """Prompt for a ``.jjq`` file and load it onto the canvas."""
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "JJQubit Project (*.jjq);;All Files (*)"
        )
        if not path:
            return
        try:
            state = load_project(path)
        except (ProjectError, NetlistError) as exc:
            self._show_project_error("Failed to open project", exc)
            return
        self.project = state
        self._load_netlist_onto_canvas(state.netlist)
        self.current_path = path
        self._dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Opened {path}")

    def save_project_current(self) -> bool:
        """Save to the current path, prompting for one if there isn't one yet.

        Returns:
            True if the project was saved, False if the user cancelled (or a
            save-as dialog was cancelled).
        """
        if self.current_path is None:
            return self.save_project_as()
        return self._save_to(self.current_path)

    def save_project_as(self) -> bool:
        """Prompt for a destination path and save the project there."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", "", "JJQubit Project (*.jjq);;All Files (*)"
        )
        if not path:
            return False
        return self._save_to(path)

    def _save_to(self, path: str) -> bool:
        self.project.netlist = self.schematic.scene.model.to_netlist()
        self.project.app_version = APP_VERSION
        errors = self.schematic.scene.model.collect_errors()
        validate = not errors
        if errors:
            joined = "\n".join(f"- {e}" for e in errors)
            choice = QMessageBox.warning(
                self,
                "Netlist has validation errors",
                f"The current circuit does not validate:\n\n{joined}\n\n"
                "Save anyway (unvalidated)?",
                QMessageBox.Save | QMessageBox.Cancel,
            )
            if choice != QMessageBox.Save:
                return False
        try:
            save_project(self.project, path, validate=validate)
        except NetlistError as exc:
            self._show_project_error("Failed to save project", exc)
            return False
        self.current_path = path
        self._dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Saved {path}")
        return True

    def _show_project_error(self, title: str, exc: Exception) -> None:
        if isinstance(exc, ValidationError):
            joined = "\n".join(f"- {e}" for e in exc.errors)
        else:
            joined = str(exc)
        QMessageBox.critical(self, title, joined)

    # -- Run ------------------------------------------------------------------

    def run_solver(self) -> None:
        """Build a netlist from the canvas and run the selected solver.

        Validates first (a solver never sees an invalid netlist from this
        path) and runs on a background :class:`SolverWorker` thread so the
        window stays responsive; results land on :attr:`results_panel`.
        """
        if self._worker is not None and self._worker.isRunning():
            return  # guard: run_action is disabled while running, but be safe

        netlist = self.schematic.scene.model.to_netlist()
        errors = self.schematic.scene.model.collect_errors()
        if errors:
            joined = "\n".join(f"- {e}" for e in errors)
            QMessageBox.warning(self, "Cannot run: netlist is invalid", joined)
            return

        solver_name = self.solver_combo.currentText()

        run_dir = Path(tempfile.gettempdir()) / "jjqubit_studio"
        run_dir.mkdir(parents=True, exist_ok=True)
        netlist_path = run_dir / "run_netlist.json"
        dump(netlist, netlist_path, validate=True)

        if self.current_path:
            output_path = str(Path(self.current_path).with_suffix("")) + f".{solver_name}.h5"
        else:
            output_path = str(run_dir / f"result_{solver_name}.h5")

        self._set_running(True)
        self._worker = SolverWorker(solver_name, str(netlist_path), output_path)
        self._worker.progress.connect(self._on_run_progress)
        self._worker.succeeded.connect(self._on_run_succeeded)
        self._worker.failed.connect(self._on_run_failed)
        self._worker.finished.connect(lambda: self._set_running(False))
        self._worker.start()

    def _set_running(self, running: bool) -> None:
        self.run_action.setEnabled(not running)
        self.solver_combo.setEnabled(not running)
        self.progress_bar.setVisible(running)
        if running:
            self.progress_bar.setValue(0)

    def _on_run_progress(self, percent: int, message: str) -> None:
        self.progress_bar.setValue(percent)
        self.statusBar().showMessage(message)

    def _on_run_succeeded(self, output_path: str) -> None:
        solver_name = self._worker.solver_name if self._worker is not None else ""
        self.project.last_run = LastRunInfo(
            solver=solver_name,
            output_path=output_path,
            status="success",
            message="Run completed.",
            timestamp=_utc_now_iso(),
        )
        self.statusBar().showMessage(f"Run complete: {output_path}")
        self.results_panel.show_result(output_path)

    def _on_run_failed(self, message: str) -> None:
        solver_name = self._worker.solver_name if self._worker is not None else ""
        self.project.last_run = LastRunInfo(
            solver=solver_name,
            output_path="",
            status="error",
            message=message,
            timestamp=_utc_now_iso(),
        )
        self.statusBar().showMessage("Run failed.")
        QMessageBox.critical(self, "Run failed", message)

    # -- Help -------------------------------------------------------------------

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME} {APP_VERSION}\n\n"
            "An interactive circuit simulator for superconducting-qubit "
            "designers: schematic canvas -> netlist -> classical/quantum "
            "solvers -> waveform viewer.",
        )

    # -- window lifecycle ---------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: D102 - Qt override
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()


def main(argv: list[str] | None = None) -> int:
    """Launch JJQubit Studio; returns the Qt event loop's exit code."""
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
