"""Exercise the real shell runner with local package-manager/Python stand-ins."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUB = r"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

name, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ["INSTALL_TEST_LOG"], "a") as output:
    output.write(json.dumps([name, args, str(Path.cwd())]) + "\n")
if name == "uname":
    print("Linux")
elif name == "dpkg-query":
    if args[-1] == os.environ.get("INSTALL_TEST_MISSING_PACKAGE"):
        sys.exit(1)
    print("install ok installed")
elif name == "sudo":
    os.execvp(args[0], args)
elif name == "uv" or args[:2] == ["-m", "venv"]:
    path = Path("venv/bin/python")
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(__file__, path)
elif args[:1] == ["-c"]:
    if "hashlib" in args[1]:
        print(hashlib.sha256(Path("requirements.txt").read_bytes()).hexdigest())
    else:
        print(os.environ.get("INSTALL_TEST_PYTHON_VERSION", "3.12"))
elif args[:2] == ["-m", "pip"] and "install" in args:
    if os.environ.get("INSTALL_TEST_FAIL_PIP"):
        sys.exit(1)
"""


@pytest.fixture
def sandbox(tmp_path):
    root, bin_dir = tmp_path / "checkout with spaces", tmp_path / "bin"
    root.mkdir()
    bin_dir.mkdir()
    shutil.copy2(ROOT / "run.sh", root / "run.sh")
    (root / "config").mkdir()
    (root / "config/config.json").write_text("{}")
    (root / "requirements.txt").write_text("requests\n")
    (root / ".env").write_text("OPENAI_API_KEY=existing-test-key\n")
    for name in ("uname", "dpkg-query", "apt-get", "sudo", "ffmpeg", "python3.12", "uv"):
        path = bin_dir / name
        path.write_text(f"#!{sys.executable}\n" + STUB)
        path.chmod(0o755)
    log = tmp_path / "calls.jsonl"
    env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin", "INSTALL_TEST_LOG": str(log)}
    env.pop("OPENAI_API_KEY", None)
    return root, bin_dir, log, env


def run(sandbox, *args):
    root, _, _, env = sandbox
    # Launch outside the checkout to cover repository-relative paths.
    return subprocess.run(
        ["/bin/bash", str(root / "run.sh"), *args],
        cwd=root.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def calls(sandbox):
    log = sandbox[2]
    return [json.loads(line)[:2] for line in log.read_text().splitlines()] if log.exists() else []


def existing_venv(sandbox):
    root, bin_dir, *_ = sandbox
    path = root / "venv/bin/python"
    path.parent.mkdir(parents=True)
    shutil.copy2(bin_dir / "python3.12", path)
    (root / "venv/.requirements.sha256").write_text(
        hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest()
    )


def test_help_without_installation_has_no_side_effects(sandbox):
    result = run(sandbox, "--help")
    assert result.returncode == 0
    assert "--doctor" in result.stdout
    assert calls(sandbox) == []
    assert not (sandbox[0] / "venv").exists()


@pytest.mark.parametrize("args", [("--config",), ("--typo",), ("--doctor", "--setup-only")])
def test_bad_arguments_fail_before_installation(sandbox, args):
    assert run(sandbox, *args).returncode != 0
    assert calls(sandbox) == []


def test_doctor_without_venv_does_not_install(sandbox):
    result = run(sandbox, "--doctor")
    assert result.returncode != 0
    assert "--setup-only" in result.stderr
    assert calls(sandbox) == []


def test_existing_venv_runs_without_system_python_or_package_manager(sandbox):
    root, bin_dir, *_ = sandbox
    existing_venv(sandbox)
    (bin_dir / "python3.12").unlink()
    custom = root / "config/my settings.json"
    custom.write_text("{}")
    result = run(sandbox, "--config", "config/my settings.json")
    assert result.returncode == 0, result.stderr
    assert calls(sandbox)[-1] == [
        "python",
        ["src/realtime_voice_assistant.py", "--config", "config/my settings.json"],
    ]
    assert all(name in {"python", "uname"} for name, _ in calls(sandbox))
    assert (root / ".env").read_text() == "OPENAI_API_KEY=existing-test-key\n"


def test_doctor_uses_existing_venv_without_running_setup(sandbox):
    existing_venv(sandbox)
    assert run(sandbox, "--doctor").returncode == 0
    assert calls(sandbox)[-1] == [
        "python",
        ["src/setup_assistant.py", "--config", "config/config.json"],
    ]
    assert len(calls(sandbox)) == 2


def test_old_venv_is_preserved_with_actionable_error(sandbox):
    existing_venv(sandbox)
    sandbox[3]["INSTALL_TEST_PYTHON_VERSION"] = "3.11"
    original = (sandbox[0] / "venv/bin/python").read_bytes()
    result = run(sandbox, "--setup-only")
    assert result.returncode != 0
    assert "Move venv aside" in result.stderr
    assert (sandbox[0] / "venv/bin/python").read_bytes() == original
    assert all(name in {"python", "uname"} for name, _ in calls(sandbox))


def test_fresh_setup_installs_each_missing_system_dependency_and_checks_pip(sandbox):
    sandbox[3]["INSTALL_TEST_MISSING_PACKAGE"] = "libsndfile1"
    result = run(sandbox, "--setup-only")
    assert result.returncode == 0, result.stderr
    recorded = calls(sandbox)
    assert ["apt-get", ["install", "-y", "libsndfile1"]] in recorded
    assert ["python", ["-m", "pip", "check"]] in recorded
    assert recorded[-1] == [
        "python",
        ["src/setup_assistant.py", "--prepare", "--config", "config/config.json"],
    ]
    assert sum(name == "dpkg-query" for name, _ in recorded) == 5
    assert (sandbox[0] / "venv/.requirements.sha256").is_file()


def test_uv_bootstraps_python_with_pip_when_system_python_is_absent(sandbox):
    root, bin_dir, *_ = sandbox
    shutil.copy2(bin_dir / "python3.12", bin_dir / "uv")
    (bin_dir / "python3.12").unlink()
    assert run(sandbox, "--setup-only", "--config=config/config.json").returncode == 0
    assert ["uv", ["venv", "--python", "3.12", "--managed-python", "--seed", "venv"]] in calls(
        sandbox
    )
    assert (root / "venv/bin/python").is_file()


def test_failed_repair_removes_success_stamp(sandbox):
    existing_venv(sandbox)
    sandbox[3]["INSTALL_TEST_FAIL_PIP"] = "1"
    assert run(sandbox, "--setup-only").returncode != 0
    assert not (sandbox[0] / "venv/.requirements.sha256").exists()
    assert not any("--prepare" in args for _, args in calls(sandbox))
