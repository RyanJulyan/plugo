import os

from flask import Flask

from plugo.models.import_class import ImportClassDetails
from plugo.models.plugin_config import PluginConfig, PLUGINS
from plugo.services.consolidate_plugin_requirements import (
    consolidate_plugin_requirements,
)
from plugo.services.plugin_manager import load_plugins

app = Flask(__name__)

# Initialize your app configurations, database, etc.

# Paths (Optional if using plugin_directory and config_path)
plugin_directory = os.path.join(app.root_path, "plugins")
plugin_config_path = os.path.join(app.root_path, "plugins_config.json")

# Create a PluginConfig instance with the plugin's name, import details, and status
plugin_config = PluginConfig(
    plugin_name="test_env_plugin",
    # Create an ImportClassDetails instance specifying the module and class/function to import
    import_class_details=ImportClassDetails(
        module_path="plugo.examples.flask_base_plugins.plugins.test_env_plugin.plugin",
        module_class_name="init_plugin",
    ),
    status="active",
)

# Add the PluginConfig instance to the PLUGINS list
PLUGINS.append(plugin_config)

# Set Environment Variable for Plugins (Optional)
os.environ["ENABLED_PLUGINS"] = "SomeOtherPlugin"

# Load plugins based on the configuration
loaded_plugins = load_plugins(
    plugin_directory=plugin_directory,  # Optional
    config_path=plugin_config_path,  # Optional
    logger=None,  # Optional
    app=app,  # kwargs passed to init_plugin
)

# Create Dynamic requirements-plugins.txt for deployments
consolidate_plugin_requirements(
    plugin_directory=plugin_directory,
    loaded_plugins=loaded_plugins,
)


if __name__ == "__main__":
    app.run(debug=True)
