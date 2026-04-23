"""Resource lookup and Windows shell integration helpers."""

from pathlib import Path
import ctypes
import sys


def _resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def _set_windows_app_id():
    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Thoughtbench.App"
        )
    except Exception:
        pass
