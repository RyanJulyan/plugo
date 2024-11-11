import click
import os
import subprocess


@click.command()
@click.option(
    "--name",
    required=True,
    default="",
    type=str,
    help="Name of the Plugin",
)
@click.option(
    "--output-dir",
    default="./api/plugins",
    type=str,
    help="Relative path for output directory for the new plugin. Defaults to './api/plugins'.",
)
def new_api_plugin(name, output_dir):
    """Create a new flask api plugin using Cookiecutter."""
    template_path = os.path.join(os.path.dirname(__file__), "cookiecutter-api-plugin")

    # Run Cookiecutter
    subprocess.run(
        [
            "cookiecutter",
            template_path,
            "-o",
            output_dir,
            f"plugin_name={name}",
        ]
    )

    print(f"API Plugin `{name}` created successfully in {output_dir}!")


if __name__ == "__main__":
    new_api_plugin()
