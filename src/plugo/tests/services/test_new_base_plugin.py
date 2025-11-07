import importlib
import os

import pytest
from click.testing import CliRunner


@pytest.fixture
def base_module():
    """
    Reload the new_base_plugin module for a clean state per test.
    """
    import plugo.cli.new_base_plugin as mod

    mod = importlib.reload(mod)
    return mod


def test_new_base_plugin_calls_cookiecutter_with_explicit_output_dir(
    base_module, monkeypatch
):
    """
    Ensure new_base_plugin:
    - calls `cookiecutter` via subprocess.run
    - uses the correct template path based on module __file__
    - passes plugin_name and output directory correctly
    - prints a success message
    """
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(base_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        base_module.new_base_plugin,
        ["--name", "myplugin", "--output-dir", "custom/plugins"],
    )

    assert result.exit_code == 0

    expected_template_path = os.path.join(
        os.path.dirname(base_module.__file__),
        "cookiecutter-base-plugin",
    )

    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "custom/plugins",
        "plugin_name=myplugin",
    ]

    assert (
        "Base Plugin `myplugin` created successfully in custom/plugins!"
        in result.output
    )


def test_new_base_plugin_uses_default_output_dir(base_module, monkeypatch):
    """
    When --output-dir is not provided, it should default to './plugins'.
    """
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(base_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        base_module.new_base_plugin,
        ["--name", "defaultdir"],
    )

    assert result.exit_code == 0

    expected_template_path = os.path.join(
        os.path.dirname(base_module.__file__),
        "cookiecutter-base-plugin",
    )

    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "./plugins",
        "plugin_name=defaultdir",
    ]

    assert (
        "Base Plugin `defaultdir` created successfully in ./plugins!" in result.output
    )


def test_new_base_plugin_allows_empty_name_and_uses_defaults(base_module, monkeypatch):
    """
    With required=True + default="":
    - Invoking without --name currently succeeds.
    - Uses default './plugins' and an empty plugin_name.
    This test documents the current behavior.
    """
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(base_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(base_module.new_base_plugin, [])

    # Command succeeds under current implementation
    assert result.exit_code == 0

    expected_template_path = os.path.join(
        os.path.dirname(base_module.__file__),
        "cookiecutter-base-plugin",
    )

    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "./plugins",
        "plugin_name=",
    ]

    assert "Base Plugin `` created successfully in ./plugins!" in result.output
