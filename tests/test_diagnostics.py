import io
import unittest

from thoughtbench.diagnostics import TkLogStream


class FakeDiagnosticsApp:
    def __init__(self):
        self.captured = []
        self._suppress_stream_diagnostics = False

    def _capture_diagnostic(self, text, tag):
        self.captured.append((text, tag))


class TkLogStreamTests(unittest.TestCase):
    def test_stdout_passthrough_does_not_capture_to_app_diagnostics(self):
        app = FakeDiagnosticsApp()
        original = io.StringIO()
        stream = TkLogStream(app, original, "stdout", capture_to_app=False)

        written = stream.write("loading output\n")

        self.assertEqual(written, len("loading output\n"))
        self.assertEqual(original.getvalue(), "loading output\n")
        self.assertEqual(app.captured, [])

    def test_stderr_passthrough_captures_to_app_diagnostics(self):
        app = FakeDiagnosticsApp()
        original = io.StringIO()
        stream = TkLogStream(app, original, "stderr", capture_to_app=True)

        stream.write("traceback\n")

        self.assertEqual(original.getvalue(), "traceback\n")
        self.assertEqual(app.captured, [("traceback\n", "stderr")])

    def test_empty_write_returns_zero_and_does_not_capture(self):
        app = FakeDiagnosticsApp()
        original = io.StringIO()
        stream = TkLogStream(app, original, "stderr", capture_to_app=True)

        written = stream.write("")

        self.assertEqual(written, 0)
        self.assertEqual(original.getvalue(), "")
        self.assertEqual(app.captured, [])

    def test_suppressed_stream_still_writes_original_but_does_not_capture(self):
        app = FakeDiagnosticsApp()
        app._suppress_stream_diagnostics = True
        original = io.StringIO()
        stream = TkLogStream(app, original, "stderr", capture_to_app=True)

        stream.write("download progress\n")

        self.assertEqual(original.getvalue(), "download progress\n")
        self.assertEqual(app.captured, [])


if __name__ == "__main__":
    unittest.main()
