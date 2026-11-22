# -*- mode: python ; coding: utf-8 -*-
# Cross-platform PyInstaller specification for SafeFlight Desktop.
#
# Invoked by build.py (python build.py --target desktop). It produces a
# one-folder distribution on Windows and Linux and an .app bundle on macOS.
# PyInstaller cannot cross-compile: each platform is built on that platform.
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
VERSION = os.environ.get("SAFEFLIGHT_VERSION", "0.0.0")
APP_NAME = "SafeFlightDesktop"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

datas = [
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "stream.sdp"), "."),
    (os.path.join(ROOT, "VERSION"), "."),
]
binaries = []
hiddenimports = []

# PyAV ships FFmpeg as shared libraries; flet_desktop ships the Flutter
# client (flet.exe, flet-macos.tar.gz or flet-linux-<arch>.tar.gz).
for package in ("av", "flet_desktop"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
datas += collect_data_files("flet")
hiddenimports += ["flet_map", "flet_charts", "ui.ConnectionProfilesPanel"]
# pymavlink imports its dialect modules dynamically and switches to the
# MAVLink 2 dialect when the first 0xFD frame arrives (ArduPilot default).
# PyInstaller cannot see those imports, so both dialects are listed.
hiddenimports += ["pymavlink.dialects.v10.ardupilotmega", "pymavlink.dialects.v20.ardupilotmega"]

a = Analysis(
    [os.path.join(ROOT, "App_flet.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Legacy Tkinter UI and web server stacks are not part of the desktop app.
    excludes=["customtkinter", "tkintermapview", "matplotlib.tests", "numpy.tests"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if IS_WIN:
    icon = os.path.join(ROOT, "assets", "safe_flight_logo.ico")
elif IS_MAC:
    icon = os.path.join(ROOT, "assets", "drone_icon.png")  # converted to .icns (Pillow)
else:
    icon = None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Windows keeps the diagnostic console of previous releases. macOS and
    # Linux write the same output to the session log (models/AppLogging.py).
    console=not IS_MAC,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="org.safeflight.desktop",
        version=VERSION,
        info_plist={
            "CFBundleName": "SafeFlight Desktop",
            "CFBundleDisplayName": "SafeFlight Desktop",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.0",  # av (arm64) and opencv-python (x64) wheels require macOS 14+
            # macOS 15+ asks before an app talks to the local network
            # (MAVLink/RTP from the Raspberry Pi on the LAN or SIYI link).
            "NSLocalNetworkUsageDescription":
                "SafeFlight recibe telemetría MAVLink y vídeo del dron a través de la red local.",
        },
    )
