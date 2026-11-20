#!/usr/bin/env python3
"""Single build entry point for SafeFlight.

    python build.py                    # SafeFlight Desktop for this OS
    python build.py --target desktop   # same, explicit
    python build.py --target android   # SafeFlight Android debug APK (Gradle)
    python build.py --target all       # every target buildable on this host
    python build.py --clean            # remove intermediate outputs (keeps dist/artifacts), then exit
    python build.py --skip-tests       # package without tests (NOT validated)

Desktop packages are produced for the host operating system only:
PyInstaller does not cross-compile, so Windows, macOS and Linux packages are
built on their own systems (locally or by GitHub Actions).

Outputs (all git-ignored):
    build/pyinstaller/<platform>/     intermediate PyInstaller files
    dist/desktop/<platform>/          unpacked application
    dist/artifacts/                   distributable archives, APK and build reports

The script exits with a non-zero status when any step fails, and a build
report (JSON) states whether tests and the packaged smoke test passed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
APP_NAME = "SafeFlightDesktop"
SPEC_FILE = ROOT / "packaging" / "desktop" / "SafeFlightDesktop.spec"
ANDROID_DIR = ROOT / "android"

BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
ARTIFACTS_DIR = DIST_DIR / "artifacts"
# Only these directories may ever be deleted by --clean. dist/artifacts is
# deliberately excluded: packages and build reports are kept as evidence and
# are only replaced by a new build of the same version and platform.
CLEANABLE = [BUILD_DIR / "pyinstaller", DIST_DIR / "desktop",
             BUILD_DIR / "test-config", BUILD_DIR / "test-logs", BUILD_DIR / "test-results"]

DESKTOP_REQUIRED_MODULES = ["flet", "flet_desktop", "flet_map", "flet_charts", "av", "cv2",
                            "numpy", "PIL", "dronekit", "pymavlink", "dotenv", "PyInstaller"]


class BuildError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def step(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def host_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    raise BuildError(f"Unsupported host platform: {sys.platform}")


def host_arch() -> str:
    machine = platform.machine().lower()
    return {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)


def run(cmd: List[str], cwd: Path = ROOT, env: Optional[Dict[str, str]] = None, timeout: int = 3600) -> None:
    log("$ " + " ".join(str(c) for c in cmd))
    result = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=env, timeout=timeout)
    if result.returncode != 0:
        raise BuildError(f"command failed with exit code {result.returncode}: {cmd[0]}")


def git_revision() -> Dict[str, object]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, timeout=20).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                                    capture_output=True, text=True, timeout=20).stdout.strip())
        return {"commit": commit or None, "dirty_worktree": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty_worktree": None}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_rmtree(path: Path) -> None:
    resolved = path.resolve()
    allowed = [p.resolve() for p in CLEANABLE]
    if resolved not in allowed and not any(a in resolved.parents for a in allowed):
        raise BuildError(f"refusing to delete {resolved}: outside controlled build directories")
    if resolved.exists():
        shutil.rmtree(resolved)
        log(f"removed {resolved.relative_to(ROOT)}")


def write_report(name: str, report: Dict[str, object]) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS_DIR / f"{name}.build-report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# desktop
# ---------------------------------------------------------------------------
def check_desktop_environment(skip_tests: bool) -> None:
    step("Desktop: environment")
    if sys.version_info < (3, 11):
        raise BuildError(f"Python >= 3.11 required (found {platform.python_version()})")
    modules = DESKTOP_REQUIRED_MODULES + ([] if skip_tests else ["pytest"])
    missing = [m for m in modules if importlib.util.find_spec(m) is None]
    if missing:
        raise BuildError(
            "missing Python packages: " + ", ".join(missing)
            + "\n  install with: python -m pip install -r requirements.txt -r requirements-build.txt"
        )
    import flet_desktop  # noqa: WPS433
    bin_dir = Path(flet_desktop.__file__).parent / "app"
    patterns = {"windows": "flet/flet.exe", "macos": "flet-macos.tar.gz", "linux": "flet-linux-*.tar.gz"}
    matches = sorted(bin_dir.glob(patterns[host_platform()]))
    client = matches[0] if matches else bin_dir / patterns[host_platform()]
    if not matches:
        found = sorted(p.name for p in bin_dir.glob("*")) if bin_dir.exists() else []
        raise BuildError(f"Flet desktop client not found at {client} (present: {found})")
    log(f"Python {platform.python_version()} on {host_platform()}-{host_arch()}")
    log(f"Flet client: {client.name}")


def junit_summary(paths: List[Path]) -> Dict[str, int]:
    """Aggregate JUnit XML files (pytest or Gradle) into test counts."""
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for path in paths:
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        for suite in suites:
            for key in totals:
                totals[key] += int(suite.get(key, 0) or 0)
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    return totals


def run_desktop_tests() -> Dict[str, int]:
    step("Desktop: tests")
    junit = BUILD_DIR / "test-results" / "desktop-junit.xml"
    junit.parent.mkdir(parents=True, exist_ok=True)
    if junit.exists():
        junit.unlink()
    try:
        run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"], timeout=1200)
    finally:
        summary = junit_summary([junit]) if junit.exists() else None
    if summary:
        log(f"tests: {summary}")
    return summary or {}


def package_desktop(plat: str, arch: str) -> Path:
    step("Desktop: PyInstaller package")
    work = BUILD_DIR / "pyinstaller" / f"{plat}-{arch}"
    dist = DIST_DIR / "desktop" / f"{plat}-{arch}"
    for path in (work, dist):
        safe_rmtree(path)
    env = {**os.environ, "SAFEFLIGHT_VERSION": VERSION}
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--workpath", work, "--distpath", dist, SPEC_FILE], env=env, timeout=3600)
    app = dist / (f"{APP_NAME}.app" if plat == "macos" else APP_NAME)
    if not app.exists():
        raise BuildError(f"PyInstaller finished but {app} was not produced")
    return app


def packaged_executable(plat: str, app: Path) -> Path:
    if plat == "macos":
        return app / "Contents" / "MacOS" / APP_NAME
    return app / (APP_NAME + (".exe" if plat == "windows" else ""))


def smoke_test_package(plat: str, app: Path) -> Dict[str, object]:
    step("Desktop: packaged smoke test (--self-check)")
    exe = packaged_executable(plat, app)
    if not exe.exists():
        raise BuildError(f"packaged executable not found: {exe}")
    report_file = BUILD_DIR / "pyinstaller" / "self-check.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    if report_file.exists():
        report_file.unlink()
    env = {**os.environ,
           "SAFEFLIGHT_CONFIG_DIR": str(BUILD_DIR / "test-config" / "smoke"),
           "SAFEFLIGHT_LOG_DIR": str(BUILD_DIR / "test-logs" / "smoke")}
    result = subprocess.run([str(exe), "--self-check", "--self-check-output", str(report_file)],
                            cwd=str(app.parent), env=env, capture_output=True, text=True,
                            timeout=300, encoding="utf-8", errors="replace")
    if not report_file.exists():
        raise BuildError("packaged self-check produced no report\n" + result.stdout + result.stderr)
    data = json.loads(report_file.read_text(encoding="utf-8"))
    for name, check in data.get("checks", {}).items():
        log(f"  {'OK  ' if check['ok'] else 'FAIL'} {name}: {check['detail']}")
    if result.returncode != 0 or not data.get("ok"):
        raise BuildError("packaged self-check failed")
    return data


def archive_desktop(plat: str, arch: str, app: Path) -> Path:
    step("Desktop: archive")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    base = f"SafeFlightDesktop-{VERSION}-{plat}-{arch}"
    if plat == "macos":
        target = ARTIFACTS_DIR / f"{base}.zip"
        if target.exists():
            target.unlink()
        # ditto keeps symlinks, permissions and extended attributes of the bundle.
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, target])
        if shutil.which("hdiutil"):
            dmg = ARTIFACTS_DIR / f"{base}.dmg"
            if dmg.exists():
                dmg.unlink()
            try:
                run(["hdiutil", "create", "-volname", "SafeFlight Desktop", "-srcfolder", app,
                     "-ov", "-format", "UDZO", dmg])
            except BuildError as exc:
                log(f"DMG not created ({exc}); the .zip remains the distributable artifact")
    elif plat == "windows":
        target = ARTIFACTS_DIR / f"{base}.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(app.rglob("*")):
                archive.write(path, Path(APP_NAME) / path.relative_to(app))
    else:
        target = ARTIFACTS_DIR / f"{base}.tar.gz"
        with tarfile.open(target, "w:gz") as archive:
            archive.add(app, arcname=APP_NAME)
    log(f"artifact: {target}")
    return target


def build_desktop(skip_tests: bool) -> Dict[str, object]:
    plat, arch = host_platform(), host_arch()
    started = time.time()
    report: Dict[str, object] = {
        "target": "desktop", "version": VERSION, "platform": plat, "arch": arch,
        "python": platform.python_version(), **git_revision(),
        "tests": "skipped" if skip_tests else "not_run", "smoke_test": "not_run",
        "validated": False, "artifact": None, "sha256": None,
    }
    try:
        check_desktop_environment(skip_tests)
        if not skip_tests:
            report["tests"] = "failed"
            report["test_summary"] = run_desktop_tests()
            report["tests"] = "passed"
        app = package_desktop(plat, arch)
        smoke = smoke_test_package(plat, app)
        report["smoke_test"] = "passed"
        report["smoke_test_platform"] = smoke.get("platform")
        artifact = archive_desktop(plat, arch, app)
        report["artifact"] = str(artifact.relative_to(ROOT))
        report["sha256"] = sha256(artifact)
        # A build counts as validated only when tests and smoke test both ran.
        report["validated"] = report["tests"] == "passed" and report["smoke_test"] == "passed"
        report["status"] = "success"
    except (BuildError, subprocess.TimeoutExpired, OSError) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
    report["duration_s"] = round(time.time() - started, 1)
    report_path = write_report(f"SafeFlightDesktop-{VERSION}-{plat}-{arch}", report)
    report["report"] = str(report_path.relative_to(ROOT))
    return report


# ---------------------------------------------------------------------------
# android
# ---------------------------------------------------------------------------
def _candidate_jdks() -> List[Path]:
    paths = []
    if os.environ.get("JAVA_HOME"):
        paths.append(Path(os.environ["JAVA_HOME"]))
    plat = host_platform()
    if plat == "windows":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            if base:
                paths += [Path(base) / "Android" / "Android Studio" / "jbr",
                          Path(base) / "Programs" / "Android Studio" / "jbr"]
    elif plat == "macos":
        paths += [Path("/Applications/Android Studio.app/Contents/jbr/Contents/Home")]
    else:
        paths += [Path("/opt/android-studio/jbr"), Path.home() / "android-studio" / "jbr",
                  Path("/snap/android-studio/current/jbr")]
    return paths


def find_jdk() -> Path:
    exe = "java.exe" if host_platform() == "windows" else "java"
    for candidate in _candidate_jdks():
        if (candidate / "bin" / exe).exists():
            return candidate
    raise BuildError("JDK 17+ not found. Set JAVA_HOME or install Android Studio (bundled JBR).")


def find_android_sdk() -> Path:
    candidates = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    local_props = ANDROID_DIR / "local.properties"
    if local_props.exists():
        for line in local_props.read_text(encoding="utf-8").splitlines():
            if line.startswith("sdk.dir="):
                candidates.append(line.split("=", 1)[1].replace("\\:", ":").replace("\\\\", "\\"))
    plat = host_platform()
    if plat == "windows" and os.environ.get("LOCALAPPDATA"):
        candidates.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk"))
    elif plat == "macos":
        candidates.append(str(Path.home() / "Library" / "Android" / "sdk"))
    else:
        candidates.append(str(Path.home() / "Android" / "Sdk"))
    for candidate in candidates:
        if candidate and (Path(candidate) / "platforms").is_dir():
            return Path(candidate)
    raise BuildError("Android SDK not found. Set ANDROID_HOME or install it with Android Studio.")


def java_major_version(jdk: Path) -> int:
    exe = jdk / "bin" / ("java.exe" if host_platform() == "windows" else "java")
    out = subprocess.run([str(exe), "-version"], capture_output=True, text=True, timeout=60).stderr
    try:
        version = out.split('"')[1]
        major = version.split(".")[0]
        return int(major if major != "1" else version.split(".")[1])
    except (IndexError, ValueError):
        return 0


def build_android(skip_tests: bool) -> Dict[str, object]:
    started = time.time()
    report: Dict[str, object] = {
        "target": "android", "version": VERSION, "variant": "debug", **git_revision(),
        "tests": "skipped" if skip_tests else "not_run", "validated": False,
        "artifact": None, "sha256": None,
    }
    try:
        step("Android: environment")
        jdk = find_jdk()
        major = java_major_version(jdk)
        if major < 17:
            raise BuildError(f"JDK 17+ required by the Android Gradle Plugin (found {major} at {jdk})")
        sdk = find_android_sdk()
        log(f"JDK {major}: {jdk}")
        log(f"Android SDK: {sdk}")
        report.update({"jdk": major, "android_sdk": str(sdk)})
        wrapper = ANDROID_DIR / ("gradlew.bat" if host_platform() == "windows" else "gradlew")
        if not wrapper.exists():
            raise BuildError(f"Gradle wrapper not found at {wrapper}")
        if host_platform() != "windows":
            wrapper.chmod(wrapper.stat().st_mode | 0o111)
        env = {**os.environ, "JAVA_HOME": str(jdk), "ANDROID_HOME": str(sdk),
               "SAFEFLIGHT_VERSION": VERSION}
        tasks = ["assembleDebug"] if skip_tests else ["testDebugUnitTest", "lintDebug", "assembleDebug"]
        step("Android: Gradle " + " ".join(tasks))
        run([wrapper, "--no-daemon", "--stacktrace", *tasks], cwd=ANDROID_DIR, env=env, timeout=3600)
        if not skip_tests:
            report["tests"] = "passed"
            results = sorted((ANDROID_DIR / "app" / "build" / "test-results" / "testDebugUnitTest").glob("*.xml"))
            report["test_summary"] = junit_summary(results)
            log(f"tests: {report['test_summary']}")
        apk_dir = ANDROID_DIR / "app" / "build" / "outputs" / "apk" / "debug"
        apks = sorted(apk_dir.glob("*.apk"))
        if not apks:
            raise BuildError(f"no APK produced in {apk_dir}")
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        target = ARTIFACTS_DIR / f"SafeFlight-Android-{VERSION}-debug.apk"
        shutil.copy2(apks[0], target)
        log(f"artifact: {target}")
        report["artifact"] = str(target.relative_to(ROOT))
        report["sha256"] = sha256(target)
        report["validated"] = report["tests"] == "passed"
        report["status"] = "success"
    except (BuildError, subprocess.TimeoutExpired, OSError) as exc:
        if report["tests"] == "not_run":
            report["tests"] = "failed_or_not_reached"
        report["status"] = "failed"
        report["error"] = str(exc)
    report["duration_s"] = round(time.time() - started, 1)
    report_path = write_report(f"SafeFlight-Android-{VERSION}-debug", report)
    report["report"] = str(report_path.relative_to(ROOT))
    return report


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def clean() -> None:
    step("Clean")
    for path in CLEANABLE:
        safe_rmtree(path)
    android_build = ANDROID_DIR / "app" / "build"
    if android_build.exists() and (ANDROID_DIR / "gradlew").exists():
        log("Android outputs are cleaned by Gradle: cd android && ./gradlew clean")


def summarise(reports: List[Dict[str, object]]) -> int:
    print("\n=== Summary ===")
    failed = False
    for r in reports:
        status = r.get("status")
        failed |= status != "success"
        label = f"{r['target']}" + (f" ({r.get('platform')}-{r.get('arch')})" if r["target"] == "desktop" else "")
        counts = r.get("test_summary") or {}
        count_text = f" ({counts.get('passed', 0)}/{counts.get('tests', 0)} passed, {counts.get('skipped', 0)} skipped)" if counts else ""
        print(f"  {label}: {status.upper()}  tests={r.get('tests')}{count_text}"
              + (f" smoke={r.get('smoke_test')}" if "smoke_test" in r else "")
              + f" validated={r.get('validated')}")
        if r.get("artifact"):
            print(f"    artifact: {ROOT / r['artifact']}")
        print(f"    report:   {ROOT / r['report']}")
        if r.get("error"):
            print(f"    error:    {r['error']}")
        if status == "success" and not r.get("validated"):
            print("    NOTE: tests were skipped; this package is NOT validated.")
    print("BUILD FAILED" if failed else "BUILD SUCCEEDED")
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build SafeFlight Desktop (host OS) and SafeFlight Android.",
        epilog="Desktop packages can only be built for the operating system running this script.",
    )
    parser.add_argument("--target", choices=["desktop", "android", "all"], default="desktop")
    parser.add_argument("--clean", action="store_true",
                        help="remove intermediate build outputs (dist/artifacts is kept) and exit")
    parser.add_argument("--skip-tests", action="store_true",
                        help="package without running tests (result is marked as not validated)")
    args = parser.parse_args(argv)

    if args.clean:
        try:
            clean()
        except BuildError as exc:
            print(f"BUILD FAILED: {exc}")
            return 1
        return 0

    log(f"SafeFlight {VERSION} | host {sys.platform} ({platform.machine()})")
    reports = []
    if args.target in ("desktop", "all"):
        reports.append(build_desktop(args.skip_tests))
    if args.target in ("android", "all"):
        reports.append(build_android(args.skip_tests))
    return summarise(reports)


if __name__ == "__main__":
    sys.exit(main())
