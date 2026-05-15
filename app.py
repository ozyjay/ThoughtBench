"""Desktop chat UI entrypoint for Thoughtbench."""

import multiprocessing
multiprocessing.freeze_support()  # must be first — prevents re-launching the UI in spawned worker processes (macOS)

import tkinter as tk
from tkinter import ttk

from thoughtbench.config import APP_NAME
from thoughtbench.resources import _set_windows_app_id


def _show_startup_dialog(root: tk.Tk) -> tk.Toplevel:
    dialog = tk.Toplevel(root)
    dialog.title(f"Starting {APP_NAME}")
    dialog.resizable(False, False)
    dialog.transient(root)

    frame = ttk.Frame(dialog, padding=(24, 20))
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(
        frame,
        text=APP_NAME,
        font=("Segoe UI", 15, "bold"),
        anchor=tk.CENTER,
    ).pack(fill=tk.X, pady=(0, 8))
    ttk.Label(
        frame,
        text="Starting application...",
        anchor=tk.CENTER,
    ).pack(fill=tk.X, pady=(0, 14))

    progress = ttk.Progressbar(frame, mode="indeterminate", length=320)
    progress.pack(fill=tk.X)
    progress.start(12)

    dialog.update_idletasks()
    width = dialog.winfo_width()
    height = dialog.winfo_height()
    x = (dialog.winfo_screenwidth() - width) // 2
    y = (dialog.winfo_screenheight() - height) // 2
    dialog.geometry(f"+{x}+{y}")
    dialog.deiconify()
    dialog.lift()
    try:
        dialog.attributes("-topmost", True)
    except tk.TclError:
        pass
    try:
        dialog.focus_force()
    except tk.TclError:
        pass
    root.update_idletasks()
    dialog.update()
    root.update()
    try:
        dialog.attributes("-topmost", False)
    except tk.TclError:
        pass
    return dialog


def main():
    _set_windows_app_id()
    root = tk.Tk()
    root.withdraw()
    startup_dialog = _show_startup_dialog(root)

    from thoughtbench.ui import ThoughtbenchApp

    ThoughtbenchApp(root)
    root.update_idletasks()
    startup_dialog.destroy()
    root.deiconify()
    root.lift()
    root.mainloop()


if __name__ == "__main__":
    main()
