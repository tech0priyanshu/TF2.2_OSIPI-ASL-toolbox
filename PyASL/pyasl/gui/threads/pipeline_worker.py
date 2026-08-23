"""
gui/threads/pipeline_worker.py
-------------------------------
QThread worker for non-blocking single-pipeline execution.
Emits Qt signals so the GUI can update safely from the main thread.
"""
from __future__ import annotations

try:
    from PyQt6.QtCore import QThread, pyqtSignal  # type: ignore
except ImportError:
    raise ImportError(
        "PyQt6 is required for the GUI. Install with: pip install PyQt6"
    )

from pyasl.pipeline.exceptions.errors import PipelineAbortedError


class PipelineWorkerThread(QThread):
    """
    Runs a Pipeline in a background thread.

    Signals
    -------
    node_started(node_id)
    node_finished(node_id, status)   status: 'COMPLETED' | 'FAILED'
    pipeline_done(result_dict)
    log_line(json_str)               one JSON log entry per signal
    error_occurred(message)
    """

    node_started = pyqtSignal(str)
    node_finished = pyqtSignal(str, str)
    pipeline_done = pyqtSignal(dict)
    log_line = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline

    def stop(self) -> None:
        """Signal the background pipeline to abort execution."""
        if self._pipeline:
            self._pipeline.abort()

    def run(self):
        import json
        from pyasl.pipeline.structured_logger import get_logger

        log = get_logger()

        def _drain():
            for entry in log.drain():
                self.log_line.emit(json.dumps(entry))

        def _progress_cb(node_id: str, status: str) -> None:
            _drain()  # Real-time log streaming after each node step
            if status == "RUNNING":
                self.node_started.emit(node_id)
            else:
                self.node_finished.emit(node_id, status)

        self._pipeline.progress_callback = _progress_cb

        try:
            result = self._pipeline.execute()
            _drain()
            self.pipeline_done.emit(result)
        except PipelineAbortedError:
            _drain()
            self.pipeline_done.emit({
                "pipeline": getattr(self._pipeline, "name", "pipeline"),
                "status": "aborted",
                "nodes": {},
                "execution_log": getattr(self._pipeline, "execution_log", []),
            })
        except Exception as exc:  # noqa: BLE001
            _drain()
            self.error_occurred.emit(str(exc))
