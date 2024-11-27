import click
from importlib.metadata import entry_points

from plugo.cli.new_base_plugin import new_base_plugin
from plugo.cli.new_api_plugin import new_api_plugin
from plugo.cli.new_ui_plugin import new_ui_plugin


@click.group()
def cli():
    pass


cli.add_command(new_base_plugin)
cli.add_command(new_api_plugin)
cli.add_command(new_ui_plugin)


# Dynamically load external plugin commands
def load_external_commands():
    for entry_point in entry_points(group="plugo.commands"):
        command = entry_point.load()
        cli.add_command(command)


load_external_commands()

if __name__ == "__main__":
    cli()
