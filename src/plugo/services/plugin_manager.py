import os
import json
import importlib.util
import logging
import subprocess
import sys
from typing import Any, Optional, Set

from pkg_resources import (
    Requirement as PkgRequirement,
    DistributionNotFound,
    VersionConflict,
    get_distribution,
)

from plugo.models.plugin_config import PLUGINS
from plugo.services.plugin_runtime import get_runtime


def load_plugin_module(plugin_name, plugin_path, plugin_main, logger):
    """
    Dynamically load a plugin module, ensuring proper package hierarchy.
    """
    # Add the parent directory of the plugins directory to sys.path temporarily
    parent_dir = os.path.dirname(os.path.dirname(plugin_path))
    sys.path.insert(0, parent_dir)

    module_name = ""

    try:
        # Construct the module name based on the plugin's relative path
        # For example: 'plugins.test.plugin'
        relative_path = os.path.relpath(plugin_path, parent_dir)
        module_name = ".".join(relative_path.split(os.sep) + ["plugin"])

        # Load the plugin module
        spec = importlib.util.spec_from_file_location(module_name, plugin_main)
        if spec is None or spec.loader is None:
            logger.error(f"Failed to load spec for module {module_name}")
            raise ImportError(f"Failed to load spec for module {module_name}")

        plugin_module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = plugin_module  # Ensure it's added to sys.modules
        spec.loader.exec_module(plugin_module)

        logger.info(f"Successfully loaded plugin module: {module_name}")
        return plugin_module

    except Exception as e:
        logger.error(f"Error loading plugin module '{module_name}': {e}")
        raise e

    finally:
        # Remove the parent directory from sys.path to avoid conflicts
        sys.path.pop(0)


def load_plugins(
    plugin_directory: Optional[str] = None,
    config_path: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    **kwargs: Any,
) -> Optional[Set[str]]:
    """
    Loads plugins from the specified directory and/or from the PLUGINS list,
    handling dependencies and loading order.

    Args:
        plugin_directory (Optional[str]): The path to the directory containing plugin folders.
        config_path (Optional[str]): The path to the plugin configuration JSON file.
        logger (Optional[logging.Logger], optional): A `logging.Logger` instance for logging. Defaults to None.
        **kwargs (Any): Additional keyword arguments passed to each plugin's `init_plugin` function.

    Returns:
        Optional[Set[str]]: A set of loaded plugin names if successful, or None if an error occurs.

    Raises:
        Exception: If a circular dependency is detected among plugins or a required plugin is disabled.
    """
    if not logger:
        # Create a logger
        logger = logging.getLogger("load_plugins")
        logger.setLevel(logging.INFO)

        # Prevent duplicate handlers if the logger already has handlers
        if not logger.hasHandlers():
            # Create console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)

            # Create a formatter
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(formatter)

            # Add handler to the logger
            logger.addHandler(console_handler)

    loaded_plugins = set()

    # Initialize sets for enabled and disabled plugins
    enabled_plugins = set()
    disabled_plugins = set()

    # Read the plugin configuration file if config_path is provided
    if config_path:
        # Check if the plugin configuration file exists
        if not os.path.exists(config_path):
            logger.error(
                f"Plugin configuration file '{config_path}' does not exist or is not accessible."
            )
            return  # Stop execution if the config file does not exist

        # Read the plugin configuration file
        try:
            with open(config_path) as config_file:
                config_data = json.load(config_file)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from config file '{config_path}': {e}")
            return

        # Populate from the configuration file
        for plugin in config_data.get("plugins", []):
            name = plugin["name"]
            enabled = plugin["enabled"]
            if enabled:
                enabled_plugins.add(name)
            else:
                disabled_plugins.add(name)
    else:
        # Config path not provided, proceed without it
        logger.info("No configuration file provided. Proceeding without it.")
        # If no config file is provided, automatically enable all valid plugins in the directory
        if plugin_directory:
            for plugin_name in os.listdir(plugin_directory):
                plugin_path = os.path.join(plugin_directory, plugin_name)
                if os.path.isdir(plugin_path):
                    enabled_plugins.add(plugin_name)

    # Update with environment variables if present
    env_plugins = os.getenv("ENABLED_PLUGINS", "")
    if env_plugins:
        env_plugin_list = [
            plugin.strip() for plugin in env_plugins.split(",") if plugin.strip()
        ]
        enabled_plugins.update(env_plugin_list)
        disabled_plugins.difference_update(
            env_plugin_list
        )  # Remove from disabled if enabled via env var

    # Collect all plugins specified in configuration
    configured_plugins = enabled_plugins.union(disabled_plugins)

    # Initialize plugin_info dictionary
    plugin_info = {}
    all_plugins_in_directory = set()

    if plugin_directory:
        # Check if the plugin directory exists
        if not os.path.exists(plugin_directory) or not os.path.isdir(plugin_directory):
            logger.error(
                f"Plugin directory '{plugin_directory}' does not exist or is not accessible."
            )
            return  # Stop execution if the directory does not exist

        # Build plugin_info dictionary for all plugins in the directory
        for plugin_name in os.listdir(plugin_directory):
            plugin_path = os.path.join(plugin_directory, plugin_name)

            if not os.path.isdir(plugin_path):
                continue  # Skip if not a directory

            all_plugins_in_directory.add(plugin_name)

            # Check for requirements.txt in the plugin directory
            requirements_file = os.path.join(plugin_path, "requirements.txt")
            if os.path.exists(requirements_file):
                logger.info(f"Processing requirements for plugin '{plugin_name}'")
                with open(requirements_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            try:
                                # Use pkg_resources to check if the requirement is installed
                                req = PkgRequirement.parse(line)
                                try:
                                    get_distribution(req)
                                    logger.info(
                                        f"Requirement '{line}' already satisfied for plugin '{plugin_name}'."
                                    )
                                except (DistributionNotFound, VersionConflict):
                                    logger.info(
                                        f"Installing requirement '{line}' for plugin '{plugin_name}'."
                                    )
                                    # Install the requirement using pip
                                    subprocess.check_call(
                                        [sys.executable, "-m", "pip", "install", line]
                                    )
                            except Exception as e:
                                logger.error(
                                    f"Error processing requirement '{line}' in plugin '{plugin_name}': {e}"
                                )
            else:
                logger.info(f"No requirements.txt found for plugin '{plugin_name}'.")

            metadata_path = os.path.join(plugin_path, "metadata.json")
            plugin_main = os.path.join(plugin_path, "plugin.py")
            if not os.path.exists(metadata_path) or not os.path.exists(plugin_main):
                logger.warning(
                    f"Plugin `{plugin_name}` is missing required files: `metadata.json` or `plugin.py`."
                )
                continue

            # Load and validate metadata
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Error decoding JSON from metadata file for plugin '{plugin_name}': {e}"
                )
                continue

            dependencies = metadata.get("dependencies", [])
            if not isinstance(dependencies, list):
                logger.error(
                    f"Dependencies for plugin '{plugin_name}' should be a list."
                )
                continue

            plugin_info[plugin_name] = {
                "path": plugin_path,
                "dependencies": dependencies,
                "metadata": metadata,
                "is_loaded": False,
                "module": None,
            }
    else:
        # Plugin directory not provided, proceed without loading directory plugins
        logger.info(
            "No plugin directory provided. Proceeding without loading directory plugins."
        )

    # Now perform topological sort to determine loading order
    loading_order = []
    visited = {}
    temp_marks = {}

    def visit(plugin_name):
        if plugin_name in temp_marks:
            logger.error(f"Circular dependency detected: {plugin_name}")
            raise Exception(
                f"Circular dependency detected involving plugin '{plugin_name}'."
            )
        if plugin_name not in visited:
            temp_marks[plugin_name] = True
            plugin = plugin_info.get(plugin_name)
            if not plugin:
                logger.error(f"Plugin '{plugin_name}' not found in plugin directory.")
                raise Exception(
                    f"Plugin '{plugin_name}' not found in plugin directory."
                )
            # Check if the plugin is explicitly disabled
            if plugin_name in disabled_plugins:
                logger.error(
                    f"Plugin '{plugin_name}' is required but is explicitly disabled."
                )
                raise Exception(
                    f"Plugin '{plugin_name}' is required but is explicitly disabled."
                )
            for dep in plugin["dependencies"]:
                visit(dep)
            visited[plugin_name] = True
            temp_marks.pop(plugin_name, None)
            loading_order.append(plugin_name)

    if plugin_directory:
        try:
            # Start from plugins that are explicitly enabled
            for plugin_name in list(enabled_plugins):
                if plugin_name not in plugin_info:
                    logger.error(
                        f"Plugin '{plugin_name}' specified as enabled but not found in plugin directory."
                    )
                    continue
                if plugin_name not in visited:
                    visit(plugin_name)
        except Exception as e:
            logger.error(f"Failed to resolve dependencies: {e}")
            return

        # Now load plugins in the determined loading order
        for plugin_name in loading_order:
            plugin = plugin_info[plugin_name]
            plugin_path = plugin["path"]
            plugin_main = os.path.join(plugin_path, "plugin.py")

            try:
                plugin_module = load_plugin_module(
                    plugin_name, plugin_path, plugin_main, logger
                )

                if hasattr(plugin_module, "init_plugin"):
                    plugin_module.init_plugin(**kwargs)
                    plugin["is_loaded"] = True
                    plugin["module"] = plugin_module
                    loaded_plugins.add(plugin_name)
                    logger.info(f"Plugin `{plugin_name}` loaded successfully.")
                else:
                    logger.warning(
                        f"Plugin `{plugin_name}` does not have an 'init_plugin' function."
                    )
            except Exception as e:
                logger.error(f"Error loading plugin `{plugin_name}`: {e}")

        # Log plugins that are present but not loaded
        not_loaded_plugins = all_plugins_in_directory - loaded_plugins

        for plugin_name in not_loaded_plugins:
            if plugin_name in disabled_plugins:
                logger.info(f"Plugin `{plugin_name}` is disabled and was not loaded.")
            elif plugin_name not in enabled_plugins and plugin_name in plugin_info:
                logger.info(
                    f"Plugin `{plugin_name}` is not enabled and was not loaded."
                )
            else:
                # This case should not occur, but we include it for completeness
                logger.warning(
                    f"Plugin `{plugin_name}` was not loaded for unknown reasons."
                )

        # Log disabled plugins specified in configuration but not found in directory
        for plugin_name in disabled_plugins:
            if plugin_name not in all_plugins_in_directory:
                logger.warning(
                    f"Plugin '{plugin_name}' is specified as disabled but not found in plugin directory."
                )
            else:
                # Plugin exists in directory but was not loaded (already logged above)
                pass
    else:
        logger.info(
            "Skipping plugin loading from directory since no plugin directory is provided."
        )

    # Process plugins specified in PLUGINS
    for plugin_config in PLUGINS:
        plugin_name = plugin_config.plugin_name
        status = plugin_config.status

        if status != "active":
            logger.info(f"Plugin '{plugin_name}' is not active. Skipping.")
            continue

        if plugin_name in loaded_plugins:
            logger.info(f"Plugin '{plugin_name}' already loaded. Skipping.")
            continue

        module_path = plugin_config.import_class_details.module_path
        module_class_name = plugin_config.import_class_details.module_class_name

        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, module_class_name)
            if callable(plugin_class):
                # Instantiate the class or call init_plugin if it exists
                if hasattr(plugin_class, "init_plugin") and callable(
                    plugin_class.init_plugin
                ):
                    plugin_class.init_plugin(**kwargs)
                else:
                    plugin_instance = plugin_class(**kwargs)
                loaded_plugins.add(plugin_name)
                logger.info(
                    f"Plugin '{plugin_name}' loaded successfully from '{module_path}.{module_class_name}'."
                )
            else:
                logger.warning(f"Plugin class '{module_class_name}' is not callable.")
        except Exception as e:
            logger.error(f"Error loading plugin '{plugin_name}': {e}")

    # Process plugins specified in ENABLED_PLUGINS environment variable
    env_plugins = os.getenv("ENABLED_PLUGINS", "")
    if env_plugins:
        env_plugin_list = [
            plugin.strip() for plugin in env_plugins.split(",") if plugin.strip()
        ]
        for plugin_name in env_plugin_list:
            if plugin_name in loaded_plugins:
                logger.info(
                    f"Plugin '{plugin_name}' already loaded from environment variable. Skipping."
                )
                continue
            try:
                # Attempt to import the plugin as a module
                plugin_module = importlib.import_module(plugin_name)
                if hasattr(plugin_module, "init_plugin"):
                    plugin_module.init_plugin(**kwargs)
                    loaded_plugins.add(plugin_name)
                    logger.info(
                        f"Plugin '{plugin_name}' loaded successfully from environment variable."
                    )
                else:
                    logger.warning(
                        f"Plugin '{plugin_name}' does not have an 'init_plugin' function."
                    )
            except Exception as e:
                logger.error(
                    f"Error loading plugin '{plugin_name}' from environment variable: {e}"
                )

    # Automatically start hot reload in the background if enabled
    try:
        runtime = get_runtime()
        runtime.ensure_hot_reload(
            plugin_directory=plugin_directory,
            config_path=config_path,
            logger=logger,
            **kwargs,
        )
    except Exception as e:
        logger.warning(f"Could not initialize automatic hot reload: {e}")

    return loaded_plugins
