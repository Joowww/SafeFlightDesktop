"""Import smoke tests: every Desktop module must import on every platform."""

import importlib
import subprocess
import sys

import pytest

from conftest import ROOT


@pytest.mark.parametrize("module", [
    "models.AppPaths",
    "models.AppLogging",
    "models.ConnectionProfiles",
    "models.DroneConnection",
    "models.DroneManager",
    "models.HeartbeatMonitor",
    "models.KeyboardController",
    "models.Trajectory",
    "models.TrajectoryController",
    "ui.ConnectionProfilesPanel",
])
def test_module_imports(module):
    importlib.import_module(module)


def test_application_self_check(tmp_path):
    """Runs ``App_flet.py --self-check`` in a fresh interpreter."""
    env = {"SAFEFLIGHT_CONFIG_DIR": str(tmp_path / "cfg"), "SAFEFLIGHT_LOG_DIR": str(tmp_path / "log")}
    import os
    result = subprocess.run(
        [sys.executable, str(ROOT / "App_flet.py"), "--self-check"],
        cwd=ROOT, env={**os.environ, **env}, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ok": true' in result.stdout
