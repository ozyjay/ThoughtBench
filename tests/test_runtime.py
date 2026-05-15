import unittest
from dataclasses import dataclass

try:
    import torch  # noqa: F401
except ModuleNotFoundError:
    torch = None

if torch is not None:
    from thoughtbench.runtime import RuntimeMixin
else:
    RuntimeMixin = object


class _Root:
    def __init__(self):
        self.idle_callbacks = []

    def after_idle(self, callback):
        self.idle_callbacks.append(callback)


class _Progress:
    def __init__(self):
        self.stopped = False
        self.configured = []

    def stop(self):
        self.stopped = True

    def configure(self, **kwargs):
        self.configured.append(kwargs)


class _Var:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


@dataclass(frozen=True)
class _Option:
    display_name: str = "Qwen3 0.6B"
    model_id: str = "Qwen/Qwen3-0.6B"


@dataclass(frozen=True)
class _LoadInfo:
    detail: str = "MPS load"


class _RuntimeHarness(RuntimeMixin):
    def __init__(self):
        self.root = _Root()
        self.active_model_option = None
        self.loading_progress = _Progress()
        self.progress_var = _Var()
        self.status_var = _Var()
        self._pending_send = True
        self.events = []

    def _stop_elapsed_timer(self):
        self.events.append("stop_elapsed")

    def _hide_loading_screen(self):
        self.events.append("hide_loading")

    def _schedule_token_usage_update(self):
        self.events.append("schedule_tokens")

    def _refresh_send_button_state(self):
        self.events.append("refresh_send")

    def _append_log_entry(self, role, content):
        self.events.append(("log", role, content))

    def _append_chat(self, text, tag=None):
        self.events.append(("append_chat", text, tag))

    def _start_generate(self):
        self.events.append("start_generate")


@unittest.skipIf(torch is None, "torch is not installed in this Python environment")
class RuntimeLoadingTests(unittest.TestCase):
    def test_pending_send_starts_after_loading_screen_is_hidden_and_idle(self):
        app = _RuntimeHarness()

        app._finish_model_load(_Option(), _LoadInfo())

        self.assertEqual(app.active_model_option.model_id, "Qwen/Qwen3-0.6B")
        self.assertFalse(app._pending_send)
        self.assertIn("hide_loading", app.events)
        self.assertIn("refresh_send", app.events)
        self.assertNotIn("start_generate", app.events)
        self.assertEqual(len(app.root.idle_callbacks), 1)

        app.root.idle_callbacks[0]()

        self.assertEqual(app.events[-1], "start_generate")

    def test_cpu_load_warning_is_shown_before_ready_state(self):
        app = _RuntimeHarness()
        app._pending_send = False

        app._finish_model_load(_Option(), _LoadInfo("CPU float32 load"))

        self.assertIn("hide_loading", app.events)
        self.assertIn(
            (
                "append_chat",
                "Model is running on CPU because PyTorch MPS is unavailable. Responses may be slow.\n\n",
                "system_msg",
            ),
            app.events,
        )
        self.assertIn("CPU float32 load", app.status_var.value)


if __name__ == "__main__":
    unittest.main()
