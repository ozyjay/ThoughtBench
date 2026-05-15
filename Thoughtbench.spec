# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


block_cipher = None


def safe_collect_data_files(package):
    try:
        return collect_data_files(package)
    except Exception:
        return []


def safe_collect_submodules(package):
    try:
        return collect_submodules(package)
    except Exception:
        return []


datas = []
datas += [("assets/app-icon.png", "assets")]
datas += [("assets/app-icon.ico", "assets")]
datas += safe_collect_data_files("sv_ttk")
datas += safe_collect_data_files("transformers")
datas += safe_collect_data_files("huggingface_hub")

hiddenimports = []
hiddenimports += safe_collect_submodules("sentencepiece")
hiddenimports += safe_collect_submodules("tokenizers")
hiddenimports += safe_collect_submodules("safetensors")
hiddenimports += safe_collect_submodules("accelerate")
hiddenimports += safe_collect_submodules("nvidia")


a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Thoughtbench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app-icon.ico",
)

import sys as _sys

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Thoughtbench",
)

if _sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Thoughtbench.app",
        icon="assets/app-icon.icns",
        bundle_identifier="com.thoughtbench.app",
        info_plist={
            "CFBundleDisplayName": "Thoughtbench",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
