import os
import shutil
import subprocess
from time import sleep

from plugo.services.plugin_manager import load_plugins
from plugo.services.consolidate_plugin_requirements import (
    consolidate_plugin_requirements,
)


# Paths (Optional if using plugin_directory and config_path)
plugin_directory = os.path.join("plugins")
plugin_config_path = os.path.join("plugins_config.json")

# Load plugins based on the configuration
loaded_plugins = load_plugins(
    # Load plugins based on the configuration
    plugin_directory=plugin_directory,  # Optional
    # config_path=plugin_config_path,  # Optional Comment back in to use the config and not load dynamic plugin
    logger=None,  # Optional
)

# Create Dynamic requirements-plugins.txt for deployments
consolidate_plugin_requirements(
    plugin_directory=plugin_directory,
    loaded_plugins=loaded_plugins,
)

# Use the Python executable from the virtual environment to run plugo
subprocess.run(
    [
        os.sys.executable,  # Use the Python interpreter from the virtual environment
        "-m",
        "plugo",
        "new-base-plugin",
        "--name=another_plugin",
    ],
    check=False,
)

sleep(1)
print()
input("press enter to remove 'another_plugin' folder...")

# Path to the 'another_plugin' folder
another_plugin_path = os.path.join(plugin_directory, "another_plugin")

# Remove the 'another_plugin' folder if it exists
if os.path.exists(another_plugin_path):
    shutil.rmtree(another_plugin_path)
    print(f"Removed folder: {another_plugin_path}")
else:
    print(f"Folder not found: {another_plugin_path}")

print()
input("press enter to exit...")
print()
