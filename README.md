# plugo
Is a simple plugin manager that will dynamically load plugins from a directory given a config or env variable with dynamic kwargs to pass for plugin loading. Example uses Flask

current_version = "v0.0.4"

## Quickstart

### Install
```shell
pip install plugo
```

### Create a new plugin
> These will be created relative to the path you run them from

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
- `--output-dir`: Relative path for output directory for the new plugin. Defaults to './api/plugins'.

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
The `plugin.py` must have a `init_plugin` function defined in it with any optional named kwargs
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
The `metadata.json` is in place to help define metadata about the plugin. a core consideration is plugin dependencies. This is a list/array of plugins in the same directory that are required to load before this plugin can load.
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

##### Using the Plugo plugin manager
You can load your plugins with the `load_plugins` function by loading it into your project with `from plugo.services.plugin_manager import load_plugins`. This function takes the following parameters:
- `plugin_directory` (*Required*):
- `config_path` (*Required*):
- `logger` (*Optional*):
- `**kwargs` (*Optional*): e.g. `app` is an optional kwarg required for our flask plugins

You can optionally consolidate custom requirements from a plugin using the `consolidate_plugin_requirements` function by loading it into your project with `from plugo.services.consolidate_plugin_requirements import consolidate_plugin_requirements`. The intent of this function is to support deployments and allow only what is required to be installed into your deployment environment. This function takes the following parameters:
- `plugin_directory` (*Required*): The directory where plugins are stored.
- `loaded_plugins` (*Required*): List of plugin names that were loaded (This is the output of the `load_plugins` function).
- `logger` (*Optional*): Logger instance for logging messages.
- `output_file` (*Optional*): The output file to write the consolidated requirements to. Defaults to 'requirements-plugins.txt'

Example `app.py`:
```Python
# app.py

import os

from flask import Flask

from plugo.services.consolidate_plugin_requirements import (
    consolidate_plugin_requirements,
)
from plugo.services.plugin_manager import load_plugins

app = Flask(__name__)

# Initialize your app configurations, database, etc.

# Paths
plugin_directory = os.path.join(app.root_path, "plugins")
plugin_config_path = os.path.join(app.root_path, "plugins_config.json")

os.environ["ENABLED_PLUGINS"] = "SomeOtherPlugin"

# Load plugins based on the configuration
loaded_plugins = load_plugins(
    plugin_directory=plugin_directory, config_path=plugin_config_path, app=app
)

consolidate_plugin_requirements(
    plugin_directory=plugin_directory, loaded_plugins=loaded_plugins
)


if __name__ == "__main__":
    app.run(debug=True)
```


## Development

### Test (TBC)
```shell
(venv) pytest
(venv) coverage run -m pytest
(venv) coverage report
(venv) coverage report -m
(venv) coverage html
(venv) mypy --html-report mypy_report .
(venv) flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --format=html --htmldir="flake8_report/basic" --exclude=venv
(venv) flake8 . --count --exit-zero --max-complexity=11 --max-line-length=127 --statistics --format=html --htmldir="flake8_report/complexity" --exclude=venv
```

### Build
```shell
poetry build
```

### Publish
```shell
poetry publish
```
