import json
import os
import sys
from pathlib import Path

import pytest

import plugo.services.venv_manager as vm_mod  # adjust if your module has a different name


build_venv_key = vm_mod.build_venv_key
VenvManager = vm_mod.VenvManager
VenvInfo = vm_mod.VenvInfo


# -----------------------------
# build_venv_key tests
# -----------------------------


def test_build_venv_key_stable_same_inputs():
    reqs = ["foo==1.0", "bar==2.0"]
    k1 = build_venv_key("my_plugin", "1.0.0", reqs)
    k2 = build_venv_key("my_plugin", "1.0.0", ["bar==2.0", "foo==1.0"])  # re-ordered
    assert k1 == k2
    assert k1.startswith("my_plugin-v1.0.0-")
    # trailing hash length
    assert len(k1.split("-")[-1]) == 12


def test_build_venv_key_diff_version_diff_key():
    reqs = ["foo==1.0"]
    k1 = build_venv_key("my_plugin", "1.0.0", reqs)
    k2 = build_venv_key("my_plugin", "2.0.0", reqs)
    assert k1 != k2


def test_build_venv_key_diff_requirements_diff_key():
    k1 = build_venv_key("my_plugin", "1.0.0", ["foo==1.0"])
    k2 = build_venv_key("my_plugin", "1.0.0", ["foo==1.0", "bar==2.0"])
    assert k1 != k2


def test_build_venv_key_no_version_includes_safe_name_and_hash():
    k = build_venv_key("my_plugin", None, ["foo==1.0"])
    # <plugin_name>-<hash>
    parts = k.split("-")
    assert parts[0] == "my_plugin"
    assert len(parts[1]) == 12


def test_build_venv_key_plugin_name_sanitization():
    raw_name = "my plugin/with:weird\\chars"
    k = build_venv_key(raw_name, None, [])

    # Reproduce the sanitizer logic used in build_venv_key
    expected_safe = (
        raw_name.replace(os.sep, "_").replace(":", "_").replace(" ", "_").strip("_")
        or "plugin"
    )

    # Key should start with "<safe_name>-<hash12>"
    assert k.startswith(expected_safe + "-")

    # Hash part length check
    suffix = k.split("-")[-1]
    assert len(suffix) == 12

    # Basic safety invariants: no spaces or colons in final key
    assert " " not in k
    assert ":" not in k


def test_build_venv_key_version_prefixed_with_v_once():
    k1 = build_venv_key("plug", "1.2.3", [])
    assert "-v1.2.3-" in k1

    k2 = build_venv_key("plug", "v4.5.6", [])
    # should not become vv4.5.6
    assert "-v4.5.6-" in k2
    assert "vv4.5.6" not in k2


def test_build_venv_key_ignores_empty_requirements_and_whitespace():
    k1 = build_venv_key("plug", "1.0", [" foo==1.0  ", " ", "", None])  # type: ignore[arg-type]
    k2 = build_venv_key("plug", "1.0", ["foo==1.0"])
    assert k1 == k2


# -----------------------------
# VenvManager.ensure tests
# -----------------------------


@pytest.fixture
def tmp_base(tmp_path: Path) -> Path:
    return tmp_path / "venvs"


def _expected_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def test_venvmanager_initializes_base_dir(tmp_base: Path):
    vm = VenvManager(base=tmp_base)
    assert vm.base == tmp_base
    assert vm.base.is_dir()


def test_ensure_creates_venv_and_installs_requirements(tmp_base: Path, monkeypatch):
    calls = []

    def fake_check_call(cmd, *args, **kwargs):
        calls.append(cmd)
        # Simulate `python -m venv <dir>` by creating the python binary path
        if len(cmd) >= 4 and cmd[0] == sys.executable and cmd[1:3] == ["-m", "venv"]:
            venv_dir = Path(cmd[3])
            python_bin = _expected_python_path(venv_dir)
            python_bin.parent.mkdir(parents=True, exist_ok=True)
            python_bin.write_text("#!python")
        return 0

    monkeypatch.setattr(vm_mod.subprocess, "check_call", fake_check_call)

    vm = VenvManager(base=tmp_base)
    key = "my_plugin-v1-abcdef123456"
    reqs = ["foo==1.0", "bar==2.0"]

    info = vm.ensure(key, reqs)

    # VenvInfo correctness
    assert isinstance(info, VenvInfo)
    assert info.key == key
    assert info.path == tmp_base / key
    assert info.python == _expected_python_path(info.path)

    # One venv create call
    venv_calls = [
        c
        for c in calls
        if len(c) >= 4 and c[0] == sys.executable and c[1:3] == ["-m", "venv"]
    ]
    assert len(venv_calls) == 1
    assert Path(venv_calls[0][3]) == info.path

    # One pip install call (pip -U pip reqs...)
    pip_calls = [c for c in calls if "pip" in c]
    assert pip_calls, "Expected a pip install call"
    assert any("foo==1.0" in c for call in pip_calls for c in call)
    assert any("bar==2.0" in c for call in pip_calls for c in call)


def test_ensure_reuses_existing_venv_and_only_installs_new_requirements(
    tmp_base: Path,
    monkeypatch,
):
    calls = []

    def fake_check_call(cmd, *args, **kwargs):
        calls.append(cmd)
        # When creating venv, also create python binary so it "exists"
        if len(cmd) >= 4 and cmd[0] == sys.executable and cmd[1:3] == ["-m", "venv"]:
            venv_dir = Path(cmd[3])
            python_bin = _expected_python_path(venv_dir)
            python_bin.parent.mkdir(parents=True, exist_ok=True)
            python_bin.write_text("#!python")
        return 0

    monkeypatch.setattr(vm_mod.subprocess, "check_call", fake_check_call)

    vm = VenvManager(base=tmp_base)
    key = "plugin-v1-aaaaaa111111"

    # First ensure: create venv + install foo
    info1 = vm.ensure(key, ["foo==1.0"])
    assert info1.path.exists()
    first_call_count = len(calls)

    # Second ensure: venv exists -> no new `python -m venv`, only pip call
    info2 = vm.ensure(key, ["foo==1.0", "bar==2.0"])
    assert info2.path == info1.path
    second_calls = calls[first_call_count:]

    # No new venv creation
    assert not any(
        len(c) >= 4 and c[0] == sys.executable and c[1:3] == ["-m", "venv"]
        for c in second_calls
    )

    # At least one pip-related call for second ensure
    assert any("pip" in c for c in second_calls)


def test_ensure_filters_empty_requirements(tmp_base: Path, monkeypatch):
    recorded = []

    def fake_check_call(cmd, *args, **kwargs):
        recorded.append(cmd)
        # Create python bin on venv creation
        if len(cmd) >= 4 and cmd[0] == sys.executable and cmd[1:3] == ["-m", "venv"]:
            venv_dir = Path(cmd[3])
            python_bin = _expected_python_path(venv_dir)
            python_bin.parent.mkdir(parents=True, exist_ok=True)
            python_bin.write_text("#!python")
        return 0

    monkeypatch.setattr(vm_mod.subprocess, "check_call", fake_check_call)

    vm = VenvManager(base=tmp_base)
    key = "plugin-no-empty-reqs-aaaaaa111111"

    vm.ensure(key, ["foo==1.0", "", "  ", None])  # type: ignore[list-item]

    # Only foo==1.0 should appear in pip install args
    pip_calls = [c for c in recorded if "pip" in c]
    assert pip_calls
    # Flatten
    flat = [arg for call in pip_calls for arg in call]
    assert "foo==1.0" in flat
    # No stray empty strings in pip args
    assert "" not in flat
    assert "  " not in flat


def test_venv_dir_sanitization(tmp_base: Path):
    vm = VenvManager(base=tmp_base)
    bad_key = " my key/with:spaces "
    venv_dir = vm._venv_dir(bad_key)

    # Reproduce the sanitizer logic from VenvManager._venv_dir
    expected_safe = (
        bad_key.replace(os.sep, "_").replace(":", "_").replace(" ", "_").strip("_")
        or "plugin"
    )

    # Matches implementation: base / safe_key
    assert venv_dir == tmp_base / expected_safe

    # Now validate only the relative portion (the generated key),
    # not the full absolute path (which may contain ':' on Windows).
    rel = venv_dir.relative_to(tmp_base)

    # Ensure no spaces or colons introduced by sanitization
    rel_str = str(rel)
    assert " " not in rel_str
    assert ":" not in rel_str


# -----------------------------
# add_site_packages_to_sys_path tests
# -----------------------------


def test_add_site_packages_to_sys_path_adds_paths(monkeypatch, tmp_path: Path):
    # Prepare fake paths that exist
    site1 = tmp_path / "venv" / "lib" / "pythonX" / "site-packages"
    site2 = tmp_path / "venv" / "lib2" / "pythonX" / "site-packages"
    site1.mkdir(parents=True, exist_ok=True)
    site2.mkdir(parents=True, exist_ok=True)

    fake_paths = [str(site1), str(site2)]

    def fake_check_output(cmd, text=True, **kwargs):
        # We expect "[venv.python, '-c', <code>]"
        assert "-c" in cmd
        return json.dumps(fake_paths)

    monkeypatch.setattr(vm_mod.subprocess, "check_output", fake_check_output)

    vm = VenvManager(base=tmp_path / "venvs")
    venv = VenvInfo(
        key="k",
        path=tmp_path / "venv",
        python=tmp_path / "venv" / "bin" / "python",
    )

    original_sys_path = list(sys.path)
    try:
        vm.add_site_packages_to_sys_path(venv)
        # All fake paths should now be present
        for p in fake_paths:
            assert p in sys.path
        # They should be near the front (because insert(0, ...))
        # i.e., their indices are less than or equal to where original entries start
        first_orig_index = min(
            (sys.path.index(p) for p in original_sys_path if p in sys.path),
            default=len(sys.path),
        )
        for p in fake_paths:
            assert sys.path.index(p) <= first_orig_index
    finally:
        # restore
        sys.path[:] = original_sys_path


def test_add_site_packages_to_sys_path_ignores_invalid_json(
    monkeypatch, tmp_path: Path
):
    def fake_check_output(cmd, text=True, **kwargs):
        return "not-json at all"

    monkeypatch.setattr(vm_mod.subprocess, "check_output", fake_check_output)

    vm = VenvManager(base=tmp_path / "venvs")
    venv = VenvInfo(
        key="k",
        path=tmp_path / "venv",
        python=tmp_path / "venv" / "bin" / "python",
    )

    original_sys_path = list(sys.path)
    try:
        vm.add_site_packages_to_sys_path(venv)
        # No changes expected
        assert sys.path == original_sys_path
    finally:
        sys.path[:] = original_sys_path


def test_add_site_packages_to_sys_path_ignores_nonexistent_dirs(
    monkeypatch, tmp_path: Path
):
    # Return paths that don't exist + one that does
    good = tmp_path / "exists"
    good.mkdir(parents=True, exist_ok=True)

    fake_paths = [str(tmp_path / "missing1"), str(good), str(tmp_path / "missing2")]

    def fake_check_output(cmd, text=True, **kwargs):
        # Emulate the code executed in the child interpreter:
        # only existing directories are kept.
        filtered = [p for p in fake_paths if os.path.isdir(p)]
        return json.dumps(filtered)

    monkeypatch.setattr(vm_mod.subprocess, "check_output", fake_check_output)

    vm = VenvManager(base=tmp_path / "venvs")
    venv = VenvInfo(
        key="k",
        path=tmp_path / "venv",
        python=tmp_path / "venv" / "bin" / "python",
    )

    original_sys_path = list(sys.path)
    try:
        vm.add_site_packages_to_sys_path(venv)
        # only existing directory should be added
        assert str(good) in sys.path
        assert str(tmp_path / "missing1") not in sys.path
        assert str(tmp_path / "missing2") not in sys.path
    finally:
        sys.path[:] = original_sys_path
