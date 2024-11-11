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
    default="./plugins",
    type=str,
    help="Output directory for the new plugin. Defaults to './plugins'.",
)
def new_base_plugin(name, output_dir):
    """Create a new plugin using Cookiecutter."""
    template_path = os.path.join(os.path.dirname(__file__), "cookiecutter-base-plugin")

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

    print(f"Base Plugin `{name}` created successfully in {output_dir}!")


if __name__ == "__main__":
    new_base_plugin()
