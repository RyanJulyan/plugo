# plugo
plugo is a simple plugin manager that dynamically loads plugins from a directory, a `json` configuration file e.g.`plugins_config.json`, an environment variable `ENABLED_PLUGINS`, or a predefined list (`PLUGINS`). It allows for dynamic keyword arguments (`kwargs`) to be passed during plugin loading, making it flexible for various applications like Flask

current_version = "v0.0.5"

## Quickstart

### Install
```shell
pip install plugo
```

### Create a new plugin
> Plugins will be created relative to the path you run the commands from.

#### Base Plugin
```shell
plugo new-base-plugin
```

#### Flask HTML Plugin
```shell
plugo new-ui-plugin
```

#### Flask RESTX API Plugin
```shell
plugo new-api-plugin
```

#### Optional Parameters
- `--name`: Name of the Plugin. This will default the Cookiecutter answer
- `--output-dir`: Relative path for output directory for the new plugin. Defaults to `./api/plugins`.

##### Example Creation with Optional Parameters
```shell
plugo new-base-plugin --name="Example Plugin" --output-dir="plugins"
```

### Example Plugin

#### Plugin Structure
All plugins have the following files:
- `metadata.json` (*Required*)
- `plugin.py` (*Required*)
- `requirements.txt` (*Optional*)
```
└── 📁sample_plugin
    └── __init__.py
    └── metadata.json
    └── plugin.py
    └── requirements.txt
```

#### `plugin.py` Example
The `plugin.py` must have a `init_plugin` function defined in it with any optional named kwargs (key word arguments) that can be referenced or passed in as context later.
```Python
# plugin.py
from flask import Blueprint

plugin_blueprint = Blueprint('sample_plugin', __name__, template_folder='templates', static_folder='static')

@plugin_blueprint.route('/sample_plugin')
def plugin_route():
    return "Hello from sample_plugin!"


def init_plugin(app):
    app.register_blueprint(plugin_blueprint, url_prefix='/plugins')

```

#### `metadata.json` Example
The `metadata.json` defines metadata about the plugin. A core consideration is plugin dependencies—a list of plugins in the same directory that are required to load before this plugin can load.
```JSON
// metadata.json

{
    "name": "sample_plugin",
    "version": "1.0.0",
    "description": "A sample plugin",
    "identifier": "com.example.sample_plugin",
    "dependencies": [
        "test_env_plugin"
    ],
    "author": "Your Name",
    "core_version": ">=1.0.0"
}
```

#### Example Project

##### Project Structure
```
└── 📁flask_base_plugins
    └── 📁plugins
        └── 📁sample_plugin
            └── __init__.py
            └── metadata.json
            └── plugin.py
            └── requirements.txt
        └── 📁test_env_plugin
            └── __init__.py
            └── metadata.json
            └── plugin.py
            └── requirements.txt
        └── __init__.py
    └── __init__.py
    └── app.py
    └── plugins_config.json
```

##### Loading Plugins
Plugins can be loaded from a `plugins_config.json` file or a comma separated list Environment Variable `ENABLED_PLUGINS`. The major difference is the level of control. The Environment Variable will assume all plugins in the list are active, while the `plugins_config.json` file allows you to specify if a plugin is active or not e.g.:
```JSON
// plugins_config.json

{
    "plugins": [
        {
            "name": "sample_plugin",
            "enabled": true
        },
        {
            "name": "another_plugin",
            "enabled": false
        }
    ]
}
```

##### Using the Plugo Plugin Manager
You can load your plugins with the `load_plugins` function by importing it into your project:
```python
from plugo.services.plugin_manager import load_plugins
```
The `load_plugins` function takes the following parameters:
- `plugin_directory` (*Optional*): The path to the directory containing plugin folders.
- `config_path` (*Optional*): The path to the plugin configuration JSON file.
- `logger` (*Optional*): A logging.Logger instance for logging.
- `**kwargs` (*Optional*): Additional keyword arguments passed to each plugin's init_plugin function (e.g., app for Flask applications).

###### Extended Functionality
- The **Environment Variable** (`ENABLED_PLUGINS`): Load plugins specified in a comma-separated list in the `ENABLED_PLUGINS` environment variable.
- The Predefined `PLUGINS` List **variable**: Allows you to Load plugins defined in a `PLUGINS` list variable using `ImportClassDetails` and `PluginConfig`.

###### Defining Plugins with ImportClassDetails and PluginConfig
You can define plugins programmatically using `ImportClassDetails` and `PluginConfig` and `PLUGINS`.
```python
from plugo.models.import_class import ImportClassDetails
from plugo.models.plugin_config import PluginConfig, PLUGINS
```
Data Classes
- **`ImportClassDetails`:** Specifies the module path and class or function name to import.
- **`PluginConfig`:** Holds the configuration for a plugin, including its name, import details, and status.
- **`PLUGINS`:** A Singleton list, used to store `PluginConfig` instances for programmatic plugin loading.

###### Defining Plugins Programmatically
By using ImportClassDetails and PluginConfig, you have full control over how plugins are loaded in your application. This method allows you to specify plugins that might not be located in the default plugin directory or to programmatically activate or deactivate plugins based on certain conditions.

Example `app.py`:
```Python
# app.py

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

```
###### Explanation
- **Import Statements:** Import necessary modules and classes from `plugo` and `Flask`.
- **App Initialization:** Create a `Flask` app instance.
- **Logging Setup:** Configure logging for better visibility (optional). In our example we are using the default logger set up in the function.
- **Paths:** Define `plugin_directory` and `plugin_config_path` (optional if *not* using directory or config file).
- **Define Programmatic Plugins:** Use `PluginConfig` and `ImportClassDetails` to define plugins programmatically.
    - **ImportClassDetails:** Specify the module path and class/function name for the plugin.
    - **PluginConfig:** Create a configuration for the plugin, including its `name`, `module` and `class` details and `status`.
    - **Add to PLUGINS:** Append the `PluginConfig` instance to the `PLUGINS` list.
- **Environment Variable:** Set `ENABLED_PLUGINS` to load plugins specified in the environment (optional assumed to be active if set and found in the plugin directory).
- **Load Plugins:** Call `load_plugins` with the appropriate parameters.
    - If `plugin_directory` and `config_path` are not provided, the function relies on `ENABLED_PLUGINS` and `PLUGINS`.
- **Loaded Plugins:** Print the set of loaded plugins for verification.
- **Run the App:** Start the Flask application.

##### Consolidating Plugin Requirements
You can optionally consolidate custom requirements from plugins using the consolidate_plugin_requirements function:
```python
from plugo.services.consolidate_plugin_requirements import consolidate_plugin_requirements
```
The intent of this function is to support deployments and allow only what is required to be installed into your deployment environment especially if you have multiple plugins for different clients. This function takes the following parameters:
- `plugin_directory` (*Required*): The directory where plugins are stored.
- `loaded_plugins` (*Required*): List of plugin names that were loaded (This is the output of the `load_plugins` function).
- `logger` (*Optional*): Logger instance for logging messages.
- `output_file` (*Optional*): The output file to write the consolidated requirements to. Defaults to `requirements-plugins.txt`

## Development

### Test
```shell
pytest
coverage run -m pytest
coverage report
coverage html
mypy --html-report mypy_report .
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --format=html --htmldir="flake8_report/basic" --exclude=venv
flake8 . --count --exit-zero --max-complexity=11 --max-line-length=127 --statistics --format=html --htmldir="flake8_report/complexity" --exclude=venv
```

### Build
```shell
poetry build
```

### Publish
```shell
poetry publish
```
