from pathlib import Path

import pytest

from models import AppPaths


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("SAFEFLIGHT_CONFIG_DIR", "SAFEFLIGHT_LOG_DIR", "APPDATA", "LOCALAPPDATA",
                 "XDG_CONFIG_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(AppPaths.Path, "home", classmethod(lambda cls: Path("/home/tester")))
    return monkeypatch


@pytest.mark.parametrize("platform,expected", [
    ("win32", "windows"), ("darwin", "macos"), ("linux", "linux"), ("freebsd13", "linux"),
])
def test_platform_key(monkeypatch, platform, expected):
    monkeypatch.setattr(AppPaths.sys, "platform", platform)
    assert AppPaths.platform_key() == expected


def test_windows_keeps_legacy_appdata_location(clean_env):
    clean_env.setattr(AppPaths.sys, "platform", "win32")
    clean_env.setenv("APPDATA", r"C:\Users\x\AppData\Roaming")
    assert AppPaths.user_config_dir() == Path(r"C:\Users\x\AppData\Roaming") / "SafeFlightDesktop"


def test_macos_uses_application_support(clean_env):
    clean_env.setattr(AppPaths.sys, "platform", "darwin")
    assert AppPaths.user_config_dir() == Path("/home/tester/Library/Application Support/SafeFlightDesktop")
    assert AppPaths.user_log_dir() == Path("/home/tester/Library/Logs/SafeFlightDesktop")


def test_linux_honours_xdg(clean_env):
    clean_env.setattr(AppPaths.sys, "platform", "linux")
    assert AppPaths.user_config_dir() == Path("/home/tester/.config/SafeFlightDesktop")
    clean_env.setenv("XDG_CONFIG_HOME", "/xdg")
    assert AppPaths.user_config_dir() == Path("/xdg/SafeFlightDesktop")


def test_override_env(clean_env, tmp_path):
    clean_env.setenv("SAFEFLIGHT_CONFIG_DIR", str(tmp_path))
    assert AppPaths.user_config_dir() == tmp_path
    assert AppPaths.legacy_config_dirs() == []


def test_legacy_dirs_on_macos_include_home_fallback(clean_env):
    clean_env.setattr(AppPaths.sys, "platform", "darwin")
    assert Path("/home/tester/SafeFlightDesktop") in AppPaths.legacy_config_dirs()


def test_resource_dir_points_to_repository_assets():
    assert (AppPaths.resource_dir() / "assets" / "drone_icon.png").is_file()
    assert (AppPaths.resource_dir() / "stream.sdp").is_file()
