"""build.py safety: --clean removes only controlled directories; JUnit parsing."""

import shutil
import subprocess
import sys

from conftest import ROOT


def _sandbox(tmp_path):
    shutil.copy2(ROOT / "build.py", tmp_path / "build.py")
    shutil.copy2(ROOT / "VERSION", tmp_path / "VERSION")
    controlled = ["build/pyinstaller/x", "dist/desktop/x", "build/test-config/x",
                  "build/test-logs/x", "build/test-results/x"]
    preserved = ["dist/artifacts/SafeFlight.zip", "build/other/keep.txt", "dist/keep.txt",
                 "android/app/build/keep.txt", "App_flet.py", "docs/keep.md"]
    for rel in controlled + preserved:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    return controlled, preserved


def test_clean_only_touches_controlled_directories(tmp_path):
    controlled, preserved = _sandbox(tmp_path)
    result = subprocess.run([sys.executable, str(tmp_path / "build.py"), "--clean"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    for rel in controlled:
        assert not (tmp_path / rel).parent.exists(), rel
    for rel in preserved:
        assert (tmp_path / rel).exists(), f"{rel} must survive --clean"


def test_safe_rmtree_refuses_paths_outside_build_dirs(tmp_path):
    sys.path.insert(0, str(ROOT))
    import build  # noqa: WPS433
    for target in (ROOT, ROOT / "dist", ROOT / "dist" / "artifacts", ROOT / "docs", tmp_path):
        try:
            build.safe_rmtree(target)
        except build.BuildError:
            continue
        raise AssertionError(f"safe_rmtree accepted {target}")


def test_junit_summary(tmp_path):
    sys.path.insert(0, str(ROOT))
    import build  # noqa: WPS433
    xml = tmp_path / "r.xml"
    xml.write_text('<testsuites><testsuite tests="5" failures="1" errors="0" skipped="1"/>'
                   '<testsuite tests="2" failures="0" errors="0" skipped="0"/></testsuites>', encoding="utf-8")
    assert build.junit_summary([xml]) == {"tests": 7, "failures": 1, "errors": 0, "skipped": 1, "passed": 5}
