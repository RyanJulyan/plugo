import importlib
from typing import List

import click
import pytest


@pytest.fixture
def cli_module(monkeypatch):
    """
    Reload the CLI module in a controlled way so that:
    - load_external_commands() runs with a patched entry_points returning no commands.
    This avoids picking up any real environment entry points during tests.
    """

    # Patch importlib.metadata.entry_points BEFORE reload so the module-level
    # `from importlib.metadata import entry_points` sees our fake.
    def fake_entry_points(*args, **kwargs):
        # Simulate no external commands by default
        return []

    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        fake_entry_points,
        raising=False,
    )

    # Import/reload the module under test
    import plugo.cli.main as main_mod  # adjust path if needed

    module = importlib.reload(main_mod)
    return module


# ================
# Basic CLI wiring
# ================


def test_cli_is_click_group(cli_module):
    """
    The top-level `cli` object should be a Click group.
    """
    assert isinstance(cli_module.cli, click.Group)


def test_builtin_commands_registered(cli_module):
    """
    The built-in new_* commands must be registered on the cli group.
    We check by identity, not by name guessing.
    """
    cli = cli_module.cli

    # new_base_plugin
    assert cli_module.new_base_plugin in cli.commands.values()

    # new_api_plugin
    assert cli_module.new_api_plugin in cli.commands.values()

    # new_ui_plugin
    assert cli_module.new_ui_plugin in cli.commands.values()


# =========================
# Dynamic entrypoint loading
# =========================


def test_load_external_commands_adds_entrypoint_commands(cli_module, monkeypatch):
    """
    load_external_commands should:
    - call entry_points(group="plugo.commands")
    - load each entry point
    - register the loaded Click commands on cli
    """

    # Define a dummy external command
    @click.command()
    def external_cmd():
        pass

    # Dummy entry point object
    class DummyEP:
        def __init__(self, name, obj):
            self.name = name
            self._obj = obj

        def load(self):
            return self._obj

    captured_args: List[tuple] = []

    def fake_entry_points(*, group=None, **kwargs):
        # Ensure correct group is requested
        captured_args.append((group, kwargs))
        assert group == "plugo.commands"
        return [DummyEP("external-cmd", external_cmd)]

    # Patch the module's imported entry_points symbol
    monkeypatch.setattr(cli_module, "entry_points", fake_entry_points, raising=True)

    # Call loader again (it already ran at import with empty stub)
    cli_module.load_external_commands()

    # Now the external command should be registered on cli
    cli = cli_module.cli
    # Fetch by Click's command lookup
    found = cli.get_command(None, "external-cmd")
    assert found is external_cmd

    # Confirm we actually called entry_points with the expected group
    assert captured_args
    assert captured_args[0][0] == "plugo.commands"


def test_load_external_commands_handles_multiple_commands(cli_module, monkeypatch):
    """
    Ensure multiple entry points are all added.
    """

    @click.command()
    def cmd_one():
        pass

    @click.command()
    def cmd_two():
        pass

    class DummyEP:
        def __init__(self, name, obj):
            self.name = name
            self._obj = obj

        def load(self):
            return self._obj

    def fake_entry_points(*, group=None, **kwargs):
        assert group == "plugo.commands"
        return [
            DummyEP("cmd-one", cmd_one),
            DummyEP("cmd-two", cmd_two),
        ]

    monkeypatch.setattr(cli_module, "entry_points", fake_entry_points, raising=True)

    cli_module.load_external_commands()

    cli = cli_module.cli
    assert cli.get_command(None, "cmd-one") is cmd_one
    assert cli.get_command(None, "cmd-two") is cmd_two


def test_cli_integration_invokes_group_help(cli_module):
    """
    Sanity check: invoking cli with no args runs and shows help (no crash).
    """
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, [])

    assert result.exit_code == 0
    # Help text should mention at least one known command group/option
    assert "Commands:" in result.output
