import os
import unittest
from unittest.mock import patch

try:
    import torch
except ModuleNotFoundError:
    torch = None


@unittest.skipIf(torch is None, "torch is not installed in this Python environment")
class ModelLoadingTests(unittest.TestCase):
    def setUp(self):
        from thoughtbench.model_loading import build_model_load_kwargs, choose_load_mode

        self.build_model_load_kwargs = build_model_load_kwargs
        self.choose_load_mode = choose_load_mode

    def test_auto_and_bf16_are_supported_load_modes(self):
        with patch("thoughtbench.model_loading._preferred_dtype", return_value=torch.float16):
            self.assertEqual(self.choose_load_mode("auto"), ("auto", torch.float16, None))
            self.assertEqual(self.choose_load_mode("bf16"), ("bf16", torch.float16, None))

    def test_cpu_fallback_uses_float32(self):
        with patch("torch.backends.mps.is_available", return_value=False):
            self.assertEqual(self.choose_load_mode("auto"), ("auto", torch.float32, None))

    def test_unsupported_and_legacy_load_modes_fall_back_to_auto(self):
        with patch("thoughtbench.model_loading._preferred_dtype", return_value=torch.float16):
            self.assertEqual(self.choose_load_mode("4bit"), ("auto", torch.float16, None))
            self.assertEqual(self.choose_load_mode("low-vram"), ("auto", torch.float16, None))
            self.assertEqual(self.choose_load_mode("quantized"), ("auto", torch.float16, None))
            self.assertEqual(self.choose_load_mode("not-real"), ("auto", torch.float16, None))

    def test_legacy_env_var_is_ignored(self):
        env = {"GEMMA4" + "_LOAD_MODE": "bf16"}
        with patch.dict(os.environ, env, clear=True):
            with patch("thoughtbench.model_loading._preferred_dtype", return_value=torch.float16):
                self.assertEqual(self.choose_load_mode(), ("auto", torch.float16, None))

    def test_build_kwargs_never_returns_quantization_config(self):
        with patch("thoughtbench.model_loading._preferred_dtype", return_value=torch.float16):
            kwargs, load_info = self.build_model_load_kwargs("4bit")

        self.assertEqual(load_info.mode, "auto")
        self.assertNotIn("quantization_config", kwargs)

    def test_cpu_fallback_build_kwargs_report_cpu_load(self):
        with patch("torch.backends.mps.is_available", return_value=False):
            kwargs, load_info = self.build_model_load_kwargs("auto")

        self.assertEqual(kwargs["device_map"], "auto")
        self.assertEqual(kwargs["dtype"], torch.float32)
        self.assertEqual(load_info.dtype, torch.float32)
        self.assertEqual(load_info.detail, "CPU float32 load")


if __name__ == "__main__":
    unittest.main()
