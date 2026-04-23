"""Diagnostics stream integration for Tk."""


class TkLogStream:
    """Tee stdout/stderr to the original stream and the app diagnostics sink."""

    def __init__(self, app: "ThoughtbenchApp", original_stream, tag: str):
        self.app = app
        self.original_stream = original_stream
        self.tag = tag

    def write(self, text):
        if not text:
            return 0

        if self.original_stream:
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except Exception:
                pass

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
