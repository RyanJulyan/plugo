import click

from plugo.cli.new_base_plugin import new_base_plugin
from plugo.cli.new_api_plugin import new_api_plugin
from plugo.cli.new_ui_plugin import new_ui_plugin


@click.group()
def cli():
    pass


cli.add_command(new_base_plugin)
cli.add_command(new_api_plugin)
cli.add_command(new_ui_plugin)

if __name__ == "__main__":
    cli()
