"""Diagnostics capture and display mixin."""

import queue
import sys
import tkinter as tk
from datetime import datetime

from .diagnostics import TkLogStream


class DiagnosticsMixin:
    def _setup_diagnostics_capture(self):
        self._start_diagnostics_log()
        sys.stdout = TkLogStream(self, self._stdout_original, "stdout")
        sys.stderr = TkLogStream(self, self._stderr_original, "stderr")
        self._diagnostics_redirected = True
        self._capture_diagnostic(
            f"Diagnostics started: {datetime.now().isoformat(timespec='seconds')}\n",
            "diagnostic_meta",
        )
        if self._diagnostics_log_handle and self.diagnostics_log_path:
            self._capture_diagnostic(
                f"Diagnostics log: {self.diagnostics_log_path}\n",
                "diagnostic_meta",
            )
        else:
            self._capture_diagnostic(
                "Diagnostics file logging unavailable: no transcript folder selected.\n",
                "diagnostic_meta",
            )

    def _start_diagnostics_log(self):
        if not self.log_dir:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.diagnostics_log_path = self.log_dir / f"diagnostics_{timestamp}.log"
        counter = 2
        while self.diagnostics_log_path.exists():
            self.diagnostics_log_path = self.log_dir / f"diagnostics_{timestamp}_{counter}.log"
            counter += 1

        try:
            self._diagnostics_log_handle = self.diagnostics_log_path.open(
                "a", encoding="utf-8"
            )
        except OSError as exc:
            self._diagnostics_log_handle = None
            self._write_original_stderr(f"Diagnostics file logging disabled: {exc}\n")

    def _capture_diagnostic(self, text: str, tag: str):
        if not text:
            return

        self._write_diagnostics_file(text, tag)
        self._diagnostics_queue.put((text, tag))
        if self._diagnostics_flush_job is None:
            try:
                self._diagnostics_flush_job = self.root.after(50, self._flush_diagnostics)
            except tk.TclError:
                self._diagnostics_flush_job = None

    def _write_diagnostics_file(self, text: str, tag: str):
        if not self._diagnostics_log_handle:
            return

        try:
            if tag == "stderr":
                prefix = "[stderr] "
            elif tag == "diagnostic_meta":
                prefix = "[meta] "
            else:
                prefix = ""
            self._diagnostics_log_handle.write(prefix + text)
            self._diagnostics_log_handle.flush()
        except OSError as exc:
            self._close_diagnostics_log()
            self._write_original_stderr(f"Diagnostics file logging disabled: {exc}\n")

    def _flush_diagnostics(self):
        self._diagnostics_flush_job = None
        if not hasattr(self, "diagnostics_display"):
            return

        should_scroll = self._should_autoscroll(self.diagnostics_display)
        self.diagnostics_display.configure(state=tk.NORMAL)
        while True:
            try:
                text, tag = self._diagnostics_queue.get_nowait()
            except queue.Empty:
                break
            self.diagnostics_display.insert(tk.END, text, tag)
        self.diagnostics_display.configure(state=tk.NORMAL)
        if should_scroll:
            self.diagnostics_display.see(tk.END)

    def _restore_standard_streams(self):
        if not self._diagnostics_redirected:
            return

        sys.stdout = self._stdout_original
        sys.stderr = self._stderr_original
        self._diagnostics_redirected = False

    def _close_diagnostics_log(self):
        if not self._diagnostics_log_handle:
            return

        try:
            self._diagnostics_log_handle.close()
        except OSError:
            pass
        self._diagnostics_log_handle = None

    def _write_original_stderr(self, text: str):
        if not self._stderr_original:
            return

        try:
            self._stderr_original.write(text)
            self._stderr_original.flush()
        except Exception:
            pass
