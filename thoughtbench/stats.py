"""System statistics and model download progress helpers."""

import tkinter as tk

from tqdm.auto import tqdm


class StatsMonitor:
    def __init__(self):
        import psutil

        self._psutil = psutil
        # Prime cpu_percent so the first real call returns meaningful data
        self._psutil.cpu_percent(interval=None)

    def get(self) -> str:
        parts = []
        cpu = self._psutil.cpu_percent(interval=None)
        mem = self._psutil.virtual_memory()
        parts.append(f"CPU: {cpu:.0f}%")
        parts.append(f"RAM: {mem.used / 1073741824:.1f}/{mem.total / 1073741824:.1f} GB")

        return "  |  ".join(parts)


# ---------------------------------------------------------------------------
# HuggingFace download progress bar → tkinter
# ---------------------------------------------------------------------------
class TkProgressBar(tqdm):
    """Custom tqdm that forwards progress to tkinter variables."""

    _tk_progress_var: tk.DoubleVar | None = None
    _tk_status_var: tk.StringVar | None = None
    _tk_root: tk.Tk | None = None
    _tk_dispatch = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def update(self, n=1):
        super().update(n)
        if self.total and self._tk_progress_var and (self._tk_dispatch or self._tk_root):
            pct = (self.n / self.total) * 100
            desc = self.desc or "Downloading"
            callback = (
                lambda: (
                    self._tk_progress_var.set(pct),
                    self._tk_status_var.set(
                        f"{desc}: {self.n / 1048576:.0f}/{self.total / 1048576:.0f} MB"
                    )
                    if self._tk_status_var
                    else None,
                )
            )
            if self._tk_dispatch is not None:
                self._tk_dispatch(callback)
            elif self._tk_root is not None:
                self._tk_root.after(0, callback)

    def close(self):
        super().close()
