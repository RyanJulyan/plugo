import importlib
import logging
import os
import sys
import types
from typing import List, Dict, Set

import pytest

import plugo.services.plugin_dependencies as plugin_dependencies


# =============================
# Fixtures & helpers
# =============================


@pytest.fixture
def deps_module():
    """
    Reload module for isolation between tests.
    """
    module = importlib.reload(plugin_dependencies)
    return module


def _write(path, content: str):
    path.write_text(content, encoding="utf-8")


# =============================
# get_plugin_dependencies
# =============================


def test_get_plugin_dependencies_prefers_pyproject_over_requirements(
    deps_module, monkeypatch, tmp_path
):
    """
    If pyproject.toml exists and returns dependencies, it should be used
    and requirements.txt should not be consulted.
    """
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    pyproj = plugin_dir / "pyproject.toml"
    req = plugin_dir / "requirements.txt"
    _write(pyproj, "dummy")
    _write(req, "dummy")

    calls: Dict[str, int] = {}

    def fake_read_pyproject(path, logger):
        calls["pyproject"] = calls.get("pyproject", 0) + 1
        return ["dep_from_pyproject"]

    def fake_read_requirements(path, logger):
        calls["requirements"] = calls.get("requirements", 0) + 1
        return ["dep_from_requirements"]

    monkeypatch.setattr(
        deps_module, "_read_pyproject_dependencies", fake_read_pyproject
    )
    monkeypatch.setattr(deps_module, "_read_requirements_txt", fake_read_requirements)

    deps = deps_module.get_plugin_dependencies(str(plugin_dir), logger=None)

    assert deps == ["dep_from_pyproject"]
    assert calls.get("pyproject") == 1
    # requirements.txt should not be called because pyproject returned deps
    assert calls.get("requirements") is None


def test_get_plugin_dependencies_falls_back_to_requirements_when_pyproject_empty(
    deps_module, monkeypatch, tmp_path
):
    """
    If pyproject.toml exists but yields no dependencies,
    fall back to requirements.txt.
    """
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    pyproj = plugin_dir / "pyproject.toml"
    req = plugin_dir / "requirements.txt"
    _write(pyproj, "dummy")
    _write(req, "dummy")

    calls: Dict[str, int] = {}

    def fake_read_pyproject(path, logger):
        calls["pyproject"] = calls.get("pyproject", 0) + 1
        return []

    def fake_read_requirements(path, logger):
        calls["requirements"] = calls.get("requirements", 0) + 1
        return ["dep_from_requirements"]

    monkeypatch.setattr(
        deps_module, "_read_pyproject_dependencies", fake_read_pyproject
    )
    monkeypatch.setattr(deps_module, "_read_requirements_txt", fake_read_requirements)

    deps = deps_module.get_plugin_dependencies(str(plugin_dir), logger=None)

    assert deps == ["dep_from_requirements"]
    assert calls.get("pyproject") == 1
    assert calls.get("requirements") == 1


def test_get_plugin_dependencies_no_files_returns_empty(deps_module, tmp_path):
    """
    If neither pyproject.toml nor requirements.txt exist, return [].
    """
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()

    deps = deps_module.get_plugin_dependencies(str(plugin_dir), logger=None)
    assert deps == []


def test_get_plugin_dependencies_uses_default_logger_when_none(
    deps_module, monkeypatch, caplog, tmp_path
):
    """
    When logger is None, get_plugin_dependencies should use module-level logger.
    We assert via the logger used in _read_pyproject_dependencies.
    """
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    pyproj = plugin_dir / "pyproject.toml"
    _write(pyproj, "dummy")

    captured = {}

    def fake_read_pyproject(path, logger):
        captured["logger_name"] = logger.name
        return ["x"]

    monkeypatch.setattr(
        deps_module, "_read_pyproject_dependencies", fake_read_pyproject
    )

    with caplog.at_level(logging.DEBUG, logger=deps_module.__name__):
        deps = deps_module.get_plugin_dependencies(str(plugin_dir), logger=None)

    assert deps == ["x"]
    # Ensures it used logging.getLogger(__name__) from this module
    assert captured["logger_name"] == deps_module.__name__


# =============================
# _convert_poetry_version_to_pip
# =============================


@pytest.mark.parametrize(
    "inp, expected",
    [
        ("", ""),
        # Caret
        ("^1.2.3", ">=1.2.3,<2.0.0"),
        ("^0.2.3", ">=0.2.3,<0.3.0"),
        ("^0.0.3", ">=0.0.3,<0.0.4"),
        ("^abc", ">=abc"),  # invalid numeric -> >= only
        # Tilde
        ("~1.2.3", ">=1.2.3,<1.3.0"),
        ("~1.2", ">=1.2,<1.3.0"),
        ("~1", ">=1,<2.0.0"),
        # Wildcard
        ("*", ""),
        # Pip-style comparisons (passthrough)
        (">=1.0,<2.0", ">=1.0,<2.0"),
        ("==1.0.0", "==1.0.0"),
        ("~=1.0", "~=1.0"),
        # Bare version
        ("2.31.0", "==2.31.0"),
        # Non-numeric start (URL, path, etc.)
        ("git+https://example.com/repo.git", "git+https://example.com/repo.git"),
    ],
)
def test_convert_poetry_version_to_pip(deps_module, inp, expected):
    """
    Validate _convert_poetry_version_to_pip behavior for key patterns.
    NOTE: These expectations follow the documented intent; if tests fail,
    adjust implementation, not the tests.
    """
    fn = deps_module._convert_poetry_version_to_pip
    assert fn(inp) == expected


# =============================
# _read_pyproject_dependencies
# =============================


def test_read_pyproject_dependencies_no_tomllib_logs_warning(
    deps_module, monkeypatch, caplog, tmp_path
):
    """
    When tomllib is not available, function should log a warning and return [].
    """
    monkeypatch.setattr(deps_module, "tomllib", None)

    pyproj = tmp_path / "pyproject.toml"
    _write(pyproj, "[project]\nname='x'\n")

    logger = logging.getLogger(deps_module.__name__)

    with caplog.at_level(logging.WARNING, logger=deps_module.__name__):
        deps = deps_module._read_pyproject_dependencies(str(pyproj), logger)

    assert deps == []
    assert any("tomli/tomllib not available" in r.getMessage() for r in caplog.records)


def test_read_pyproject_dependencies_project_section(
    deps_module, monkeypatch, caplog, tmp_path
):
    """
    [project] dependencies list (PEP 621) should be returned directly.
    """

    class DummyTomlLib:
        @staticmethod
        def load(f):
            return {
                "project": {
                    "dependencies": ["requests>=2.0", "rich==13.0.0"],
                }
            }

    monkeypatch.setattr(deps_module, "tomllib", DummyTomlLib)

    pyproj = tmp_path / "pyproject.toml"
    _write(pyproj, "dummy")

    logger = logging.getLogger(deps_module.__name__)

    with caplog.at_level(logging.DEBUG, logger=deps_module.__name__):
        deps = deps_module._read_pyproject_dependencies(str(pyproj), logger)

    assert deps == ["requests>=2.0", "rich==13.0.0"]
    assert any(
        "Found 2 dependencies in [project] section" in r.getMessage()
        for r in caplog.records
    )


def test_read_pyproject_dependencies_poetry_section_various(
    deps_module, monkeypatch, caplog, tmp_path
):
    """
    [tool.poetry] dependencies should:
    - skip python
    - handle simple strings (using _convert_poetry_version_to_pip)
    - handle dict with version+extras
    - handle extras-only dict
    """

    class DummyTomlLib:
        @staticmethod
        def load(f):
            return {
                "tool": {
                    "poetry": {
                        "dependencies": {
                            "python": "^3.11",
                            "requests": "^2.31.0",
                            "rich": "~13.0.0",
                            "simple": "*",
                            "complex": {
                                "version": "^1.2.3",
                                "extras": ["s3", "gcs"],
                            },
                            "extras_only": {
                                "extras": ["foo"],
                            },
                        }
                    }
                }
            }

    monkeypatch.setattr(deps_module, "tomllib", DummyTomlLib)

    pyproj = tmp_path / "pyproject.toml"
    _write(pyproj, "dummy")

    logger = logging.getLogger(deps_module.__name__)

    with caplog.at_level(logging.DEBUG, logger=deps_module.__name__):
        deps = deps_module._read_pyproject_dependencies(str(pyproj), logger)

    # Order isn't critical; check presence
    joined = " ".join(deps)

    # python skipped
    assert not any(d.lower().startswith("python") for d in deps)

    assert any(d.startswith("requests") for d in deps)
    assert any(d.startswith("rich") for d in deps)
    assert "simple" in deps  # "*" -> no version constraint

    # complex with extras & version
    assert any("complex[" in d and "s3" in d and "gcs" in d for d in deps)

    # extras_only without version => name[extras]
    assert "extras_only[foo]" in deps

    assert any(
        "Found" in r.getMessage()
        and "dependencies in [tool.poetry] section" in r.getMessage()
        for r in caplog.records
    )


def test_read_pyproject_dependencies_logs_error_on_exception(
    deps_module, monkeypatch, caplog, tmp_path
):
    """
    Any exception while reading/parsing should be logged and [] returned.
    """

    class DummyTomlLib:
        @staticmethod
        def load(f):
            raise ValueError("bad toml")

    monkeypatch.setattr(deps_module, "tomllib", DummyTomlLib)

    pyproj = tmp_path / "pyproject.toml"
    _write(pyproj, "dummy")

    logger = logging.getLogger(deps_module.__name__)

    with caplog.at_level(logging.ERROR, logger=deps_module.__name__):
        deps = deps_module._read_pyproject_dependencies(str(pyproj), logger)

    assert deps == []
    assert any(
        "Error reading pyproject.toml from" in r.getMessage()
        and "bad toml" in r.getMessage()
        for r in caplog.records
    )


# =============================
# _read_requirements_txt
# =============================


def test_read_requirements_txt_parses_and_skips_comments(deps_module, caplog, tmp_path):
    req = tmp_path / "requirements.txt"
    _write(
        req,
        """
        # comment
        requests>=2.0

        rich==13.0.0
        # another
        """,
    )

    logger = logging.getLogger(deps_module.__name__)

    with caplog.at_level(logging.DEBUG, logger=deps_module.__name__):
        deps = deps_module._read_requirements_txt(str(req), logger)

    assert deps == ["requests>=2.0", "rich==13.0.0"]
    assert any(
        "Found 2 dependencies in requirements.txt" in r.getMessage()
        for r in caplog.records
    )


def test_read_requirements_txt_logs_error_on_exception(
    deps_module, monkeypatch, caplog
):
    """
    If reading requirements.txt fails, log error and return [].
    """

    def fake_open(*args, **kwargs):
        raise OSError("nope")

    # Patch the open used in this module's namespace only
    monkeypatch.setattr(
        "plugo.services.plugin_dependencies.open",
        fake_open,
        raising=False,
    )

    logger = logging.getLogger(deps_module.__name__)

    with caplog.at_level(logging.ERROR, logger=deps_module.__name__):
        deps = deps_module._read_requirements_txt("requirements.txt", logger)

    assert deps == []
    assert any(
        "Error reading requirements.txt from requirements.txt: nope" in r.getMessage()
        for r in caplog.records
    )


def test_tomllib_import_when_python_ge_311(monkeypatch):
    """
    Ensure that when sys.version_info >= (3, 11), the module uses tomllib.
    We simulate this by forcing version_info and providing a dummy tomllib.
    """
    import types
    import plugo.services.plugin_dependencies as orig_mod

    # Force Python 3.11+ semantics
    monkeypatch.setattr(sys, "version_info", (3, 11, 0, "final", 0))

    dummy_tomllib = types.ModuleType("tomllib")
    monkeypatch.setitem(sys.modules, "tomllib", dummy_tomllib)

    reloaded = importlib.reload(orig_mod)

    assert reloaded.tomllib is dummy_tomllib


def test_tomllib_none_when_tomli_missing_on_older_python(monkeypatch):
    """
    Simulate Python < 3.11 with no tomli installed:
    plugin_dependencies should end up with tomllib = None.
    """
    import builtins
    import plugo.services.plugin_dependencies as orig_mod

    # Simulate Python < 3.11 so it goes into the 'else: try: import tomli' block
    monkeypatch.setattr(sys, "version_info", (3, 10, 0, "final", 0))

    # Ensure tomli/tomllib are not already satisfied via sys.modules
    monkeypatch.delitem(sys.modules, "tomli", raising=False)
    monkeypatch.delitem(sys.modules, "tomllib", raising=False)

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        # When the module under test tries `import tomli as tomllib`, make it fail
        if name == "tomli":
            raise ImportError("no tomli")
        return real_import(name, globals, locals, fromlist, level)

    # Apply import hook before reload so its top-level import logic sees it
    monkeypatch.setattr(builtins, "__import__", fake_import)

    reloaded = importlib.reload(orig_mod)

    assert reloaded.tomllib is None


def test_read_pyproject_poetry_branches_for_pip_spec_and_no_version(
    deps_module, monkeypatch, tmp_path
):
    """
    Cover the branches:
      - pip_spec truthy -> 'package{pip_spec}'
      - pip_spec falsy  -> 'package'
    in [tool.poetry].dependencies dict handling.
    """

    class DummyTomlLib:
        @staticmethod
        def load(f):
            return {
                "tool": {
                    "poetry": {
                        "dependencies": {
                            "with_version": {"version": "^1.0.0"},
                            "no_version": {},  # no version, no extras
                        }
                    }
                }
            }

    # Use our dummy tomllib
    monkeypatch.setattr(deps_module, "tomllib", DummyTomlLib)

    # Force predictable conversion for ^1.0.0
    def fake_convert_poetry_version_to_pip(spec: str) -> str:
        assert spec == "^1.0.0"
        return ">=1.0.0"

    monkeypatch.setattr(
        deps_module,
        "_convert_poetry_version_to_pip",
        fake_convert_poetry_version_to_pip,
    )

    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text("dummy", encoding="utf-8")

    logger = logging.getLogger(deps_module.__name__)
    deps = deps_module._read_pyproject_dependencies(str(pyproj), logger)

    # pip_spec truthy -> with_version>=1.0.0
    assert "with_version>=1.0.0" in deps

    # pip_spec falsy (no version, no extras) -> bare package name
    assert "no_version" in deps
