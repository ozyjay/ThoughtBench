"""System statistics and model download progress helpers."""

import tkinter as tk

from tqdm.auto import tqdm


class StatsMonitor:
    def __init__(self):
        import psutil

        self._psutil = psutil
        self._pynvml = None
        self._gpu_handle = None
        try:
            import pynvml

            pynvml.nvmlInit()
            self._pynvml = pynvml
        except Exception:
            self._pynvml = None

        if self._pynvml:
            try:
                self._gpu_handle = self._pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception:
                pass
        # Prime cpu_percent so the first real call returns meaningful data
        self._psutil.cpu_percent(interval=None)

    def get(self) -> str:
        parts = []
        cpu = self._psutil.cpu_percent(interval=None)
        mem = self._psutil.virtual_memory()
        parts.append(f"CPU: {cpu:.0f}%")
        parts.append(f"RAM: {mem.used / 1073741824:.1f}/{mem.total / 1073741824:.1f} GB")

        if self._gpu_handle and self._pynvml:
            try:
                mi = self._pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                util = self._pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                temp = self._pynvml.nvmlDeviceGetTemperature(
                    self._gpu_handle, self._pynvml.NVML_TEMPERATURE_GPU
                )
                parts.append(
                    f"GPU: {mi.used / 1073741824:.1f}/{mi.total / 1073741824:.1f} GB"
                )
                parts.append(f"GPU Util: {util.gpu}%")
                parts.append(f"Temp: {temp}°C")
            except Exception:
                parts.append("GPU: N/A")

        return "  |  ".join(parts)


# ---------------------------------------------------------------------------
# HuggingFace download progress bar → tkinter
# ---------------------------------------------------------------------------
class TkProgressBar(tqdm):
    """Custom tqdm that forwards progress to tkinter variables."""

    _tk_progress_var: tk.DoubleVar | None = None
    _tk_status_var: tk.StringVar | None = None
    _tk_root: tk.Tk | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def update(self, n=1):
        super().update(n)
        if self.total and self._tk_progress_var and self._tk_root:
            pct = (self.n / self.total) * 100
            desc = self.desc or "Downloading"
            self._tk_root.after(
                0,
                lambda: (
                    self._tk_progress_var.set(pct),
                    self._tk_status_var.set(
                        f"{desc}: {self.n / 1048576:.0f}/{self.total / 1048576:.0f} MB"
                    )
                    if self._tk_status_var
                    else None,
                ),
            )

    def close(self):
        super().close()
