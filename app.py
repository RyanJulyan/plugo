import os

from flask import Flask

from consolidate_plugin_requirements import consolidate_plugin_requirements
from plugin_manager import load_plugins

app = Flask(__name__)

# Initialize your app configurations, database, etc.

# Paths
plugin_directory = os.path.join(app.root_path, 'plugins')
plugin_config_path = os.path.join(app.root_path, 'plugins_config.json')

os.environ["ENABLED_PLUGINS"] = "SomeOtherPlugin"

# Load plugins based on the configuration
loaded_plugins = load_plugins(plugin_directory=plugin_directory, config_path=plugin_config_path, app=app)

consolidate_plugin_requirements(plugin_directory=plugin_directory, loaded_plugins=loaded_plugins)


if __name__ == "__main__":
    app.run(debug=True)