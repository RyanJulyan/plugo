import importlib
import os

import pytest
from click.testing import CliRunner


@pytest.fixture
def ui_module():
    """
    Reload the new_ui_plugin module for a clean state per test.
    """
    import plugo.cli.new_ui_plugin as mod

    mod = importlib.reload(mod)
    return mod


def test_new_ui_plugin_calls_cookiecutter_with_explicit_output_dir(
    ui_module, monkeypatch
):
    """
    Ensure new_ui_plugin:
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

    monkeypatch.setattr(ui_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        ui_module.new_ui_plugin,
        ["--name", "myuiplugin", "--output-dir", "custom/ui/plugins"],
    )

    assert result.exit_code == 0

    expected_template_path = os.path.join(
        os.path.dirname(ui_module.__file__),
        "cookiecutter-ui-plugin",
    )

    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "custom/ui/plugins",
        "plugin_name=myuiplugin",
    ]

    assert (
        "UI Plugin `myuiplugin` created successfully in custom/ui/plugins!"
        in result.output
    )


def test_new_ui_plugin_uses_default_output_dir(ui_module, monkeypatch):
    """
    When --output-dir is not provided, it should default to './ui/plugins'.
    """
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(ui_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        ui_module.new_ui_plugin,
        ["--name", "defaultui"],
    )

    assert result.exit_code == 0

    expected_template_path = os.path.join(
        os.path.dirname(ui_module.__file__),
        "cookiecutter-ui-plugin",
    )

    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "./ui/plugins",
        "plugin_name=defaultui",
    ]

    assert (
        "UI Plugin `defaultui` created successfully in ./ui/plugins!" in result.output
    )


def test_new_ui_plugin_allows_empty_name_and_uses_defaults(ui_module, monkeypatch):
    """
    With required=True + default="":
    - Invoking without --name currently succeeds.
    - Uses default './ui/plugins' and an empty plugin_name.
    This test documents the current behavior.
    """
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(ui_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(ui_module.new_ui_plugin, [])

    # Command succeeds under current implementation
    assert result.exit_code == 0

    expected_template_path = os.path.join(
        os.path.dirname(ui_module.__file__),
        "cookiecutter-ui-plugin",
    )

    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "./ui/plugins",
        "plugin_name=",
    ]

    assert "UI Plugin `` created successfully in ./ui/plugins!" in result.output
