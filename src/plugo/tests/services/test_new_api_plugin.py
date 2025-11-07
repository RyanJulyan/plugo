import importlib
import os

import pytest
from click.testing import CliRunner


@pytest.fixture
def api_module():
    """
    Reload the new_api_plugin module for a clean CLI/namespace per test.
    """
    import plugo.cli.new_api_plugin as mod

    mod = importlib.reload(mod)
    return mod


def test_new_api_plugin_calls_cookiecutter_with_explicit_output_dir(
    api_module, monkeypatch
):
    """
    Ensure new_api_plugin:
    - calls `cookiecutter` via subprocess.run
    - uses the correct template path based on module __file__
    - passes plugin_name and output directory correctly
    - prints a success message
    """
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd

        # Simulate successful run
        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(api_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        api_module.new_api_plugin,
        ["--name", "myplugin", "--output-dir", "custom/output"],
    )

    assert result.exit_code == 0

    # Check subprocess.run was called
    assert "cmd" in calls

    expected_template_path = os.path.join(
        os.path.dirname(api_module.__file__),
        "cookiecutter-api-plugin",
    )

    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "custom/output",
        "plugin_name=myplugin",
    ]

    # Output message
    assert (
        "API Plugin `myplugin` created successfully in custom/output!" in result.output
    )


def test_new_api_plugin_uses_default_output_dir(api_module, monkeypatch):
    """
    When --output-dir is not provided, it should default to './api/plugins'.
    """
    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(api_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        api_module.new_api_plugin,
        ["--name", "defaultdir"],
    )

    assert result.exit_code == 0

    expected_template_path = os.path.join(
        os.path.dirname(api_module.__file__),
        "cookiecutter-api-plugin",
    )

    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "./api/plugins",
        "plugin_name=defaultdir",
    ]

    assert (
        "API Plugin `defaultdir` created successfully in ./api/plugins!"
        in result.output
    )


def test_new_api_plugin_allows_empty_name_and_uses_defaults(api_module, monkeypatch):
    """
    Given the current implementation (required + default=""),
    invoking without --name succeeds and uses:
    - default output dir './api/plugins'
    - empty plugin_name in cookiecutter args.
    This test documents that behavior.
    """
    from click.testing import CliRunner

    calls = {}

    def fake_run(cmd, *args, **kwargs):
        calls["cmd"] = cmd

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(api_module.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(api_module.new_api_plugin, [])

    # Command currently succeeds
    assert result.exit_code == 0

    expected_template_path = os.path.join(
        os.path.dirname(api_module.__file__),
        "cookiecutter-api-plugin",
    )

    # With no --name passed, Click uses default "" -> "plugin_name="
    assert calls["cmd"] == [
        "cookiecutter",
        expected_template_path,
        "-o",
        "./api/plugins",
        "plugin_name=",
    ]

    # And success message reflects the empty name
    assert "API Plugin `` created successfully in ./api/plugins!" in result.output
