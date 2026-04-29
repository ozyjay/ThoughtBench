"""Diagnostics stream integration for Tk."""


class TkLogStream:
    """Write to the original stream and optionally mirror text to app diagnostics."""

    def __init__(self, app: "ThoughtbenchApp", original_stream, tag: str, capture_to_app: bool = True):
        self.app = app
        self.original_stream = original_stream
        self.tag = tag
        self.capture_to_app = capture_to_app

    def write(self, text):
        if not text:
            return 0

        if self.original_stream:
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except Exception:
                pass

        if self.capture_to_app and not getattr(self.app, "_suppress_stream_diagnostics", False):
            try:
                self.app._capture_diagnostic(text, self.tag)
            except Exception:
                pass

        return len(text)

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass

    def isatty(self):
        if self.original_stream and hasattr(self.original_stream, "isatty"):
            try:
                return self.original_stream.isatty()
            except Exception:
                return False
        return False

    def __getattr__(self, name):
        if self.original_stream:
            return getattr(self.original_stream, name)
        raise AttributeError(name)
