import queue
import unittest

from thoughtbench.diagnostics_mixin import DiagnosticsMixin


class _Root:
    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))
        return f"after-{len(self.after_calls)}"


class _DiagnosticsHarness(DiagnosticsMixin):
    def __init__(self):
        self.root = _Root()
        self._diagnostics_log_handle = None
        self._diagnostics_queue = queue.Queue()
        self._diagnostics_flush_job = None
        self.posted_ui_events = []

    def _post_ui_event(self, callback):
        self.posted_ui_events.append(callback)


class DiagnosticsThreadSafetyTests(unittest.TestCase):
    def test_capture_diagnostic_posts_flush_scheduling_through_ui_queue(self):
        app = _DiagnosticsHarness()

        app._capture_diagnostic("Generation started\n", "diagnostic_meta")

        self.assertEqual(app.root.after_calls, [])
        self.assertEqual(len(app.posted_ui_events), 1)
        self.assertEqual(
            app._diagnostics_queue.get_nowait(),
            ("Generation started\n", "diagnostic_meta"),
        )

        app.posted_ui_events[0]()

        self.assertEqual(len(app.root.after_calls), 1)
        self.assertEqual(app.root.after_calls[0][0], 50)
        self.assertIsNotNone(app._diagnostics_flush_job)


if __name__ == "__main__":
    unittest.main()
