import os
import json
import importlib.util
import importlib
import logging
import subprocess
import sys
from typing import Any, Optional, Set, List, Dict

from pkg_resources import (
    Requirement as PkgRequirement,
    DistributionNotFound,
    VersionConflict,
    get_distribution,
)

from plugo.models.plugin_config import PLUGINS
from plugo.services.plugin_runtime import get_runtime
from plugo.services.plugin_dependencies import get_plugin_dependencies
from plugo.services.venv_manager import VenvManager, build_venv_key


def load_plugin_module(plugin_name, plugin_path, plugin_main, logger):
    """
    Dynamically load a plugin module, ensuring proper package hierarchy.
    """
    parent_dir = os.path.dirname(os.path.dirname(plugin_path))
    sys.path.insert(0, parent_dir)

    module_name = ""

    try:
        # Construct the module name based on the plugin's relative path
        # For example: 'plugins.test.plugin'
        relative_path = os.path.relpath(plugin_path, parent_dir)
        module_name = ".".join(relative_path.split(os.sep) + ["plugin"])

        spec = importlib.util.spec_from_file_location(module_name, plugin_main)
        if spec is None or spec.loader is None:
            logger.error(f"Failed to load spec for module {module_name}")
            raise ImportError(f"Failed to load spec for module {module_name}")

        plugin_module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = plugin_module
        spec.loader.exec_module(plugin_module)

        logger.info(f"Successfully loaded plugin module: {module_name}")
        return plugin_module

    except Exception as e:
        logger.error(f"Error loading plugin module '{module_name}': {e}")
        raise e

    finally:
        # Only remove if we added what we expect
        if sys.path and sys.path[0] == parent_dir:
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

    - Keeps existing behavior by default.
    - If PLUGO_USE_VENVS=true|1|yes|on:
        * Python deps for each plugin are installed into a dedicated venv
          keyed by (plugin_name, version, requirements).
        * That venv's site-packages are added to sys.path so imports work.
    """

    # ---------------------------
    # Logger setup (unchanged)
    # ---------------------------
    if not logger:
        logger = logging.getLogger("load_plugins")
        logger.setLevel(logging.INFO)

        if not logger.hasHandlers():
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    loaded_plugins: Set[str] = set()
    enabled_plugins: Set[str] = set()
    disabled_plugins: Set[str] = set()

    # ---------------------------
    # Optional: per-plugin venvs
    # ---------------------------
    use_venvs = os.getenv("PLUGO_USE_VENVS", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    venv_manager: Optional[VenvManager] = None
    if use_venvs:
        venv_manager = VenvManager()
        logger.info(f"Using per-plugin virtualenvs under: {venv_manager.base}")
    else:
        logger.info(
            "PLUGO_USE_VENVS disabled; using current environment for plugin dependencies."
        )

    # ---------------------------
    # Config file (unchanged)
    # ---------------------------
    if config_path:
        if not os.path.exists(config_path):
            logger.error(
                f"Plugin configuration file '{config_path}' does not exist or is not accessible."
            )
            return

        try:
            with open(config_path) as config_file:
                config_data = json.load(config_file)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from config file '{config_path}': {e}")
            return

        for plugin in config_data.get("plugins", []):
            name = plugin["name"]
            enabled = plugin["enabled"]
            if enabled:
                enabled_plugins.add(name)
            else:
                disabled_plugins.add(name)
    else:
        logger.info("No configuration file provided. Proceeding without it.")
        if plugin_directory:
            for plugin_name in os.listdir(plugin_directory):
                plugin_path = os.path.join(plugin_directory, plugin_name)
                if os.path.isdir(plugin_path):
                    enabled_plugins.add(plugin_name)

    # ---------------------------
    # ENABLED_PLUGINS env (unchanged)
    # ---------------------------
    env_plugins = os.getenv("ENABLED_PLUGINS", "")
    if env_plugins:
        env_plugin_list = [
            plugin.strip() for plugin in env_plugins.split(",") if plugin.strip()
        ]
        enabled_plugins.update(env_plugin_list)
        disabled_plugins.difference_update(env_plugin_list)

    configured_plugins = enabled_plugins.union(disabled_plugins)

    # ---------------------------
    # Discover directory plugins
    # ---------------------------
    plugin_info: Dict[str, Dict[str, Any]] = {}
    all_plugins_in_directory: Set[str] = set()

    if plugin_directory:
        if not os.path.exists(plugin_directory) or not os.path.isdir(plugin_directory):
            logger.error(
                f"Plugin directory '{plugin_directory}' does not exist or is not accessible."
            )
            return

        for plugin_name in os.listdir(plugin_directory):
            plugin_path = os.path.join(plugin_directory, plugin_name)
            if not os.path.isdir(plugin_path):
                continue

            all_plugins_in_directory.add(plugin_name)

            metadata_path = os.path.join(plugin_path, "metadata.json")
            plugin_main = os.path.join(plugin_path, "plugin.py")

            # Require metadata + plugin.py as before
            if not os.path.exists(metadata_path) or not os.path.exists(plugin_main):
                logger.warning(
                    f"Plugin `{plugin_name}` is missing required files: `metadata.json` or `plugin.py`."
                )
                continue

            # Load metadata first (so we can use version in venv key)
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(
                    f"Error decoding JSON from metadata file for plugin '{plugin_name}': {e}"
                )
                continue

            plugin_deps = metadata.get("dependencies", [])
            if not isinstance(plugin_deps, list):
                logger.error(
                    f"Dependencies for plugin '{plugin_name}' should be a list."
                )
                continue

            version = metadata.get("version") or metadata.get("plugin_version") or ""

            # Python/package dependencies from repository files
            pip_requirements: List[str] = get_plugin_dependencies(plugin_path, logger)

            if pip_requirements:
                logger.info(
                    f"Processing {len(pip_requirements)} dependencies for plugin '{plugin_name}'"
                )

                if venv_manager:
                    # Version + requirements aware venv key
                    venv_key = build_venv_key(
                        plugin_name,
                        version,
                        pip_requirements,
                    )
                    try:
                        venv = venv_manager.ensure(venv_key, pip_requirements)
                        venv_manager.add_site_packages_to_sys_path(venv)
                        logger.info(
                            f"Using dedicated venv '{venv_key}' for plugin '{plugin_name}'."
                        )
                    except Exception as e:
                        logger.error(
                            f"Error preparing venv for plugin '{plugin_name}': {e}"
                        )
                        # Intentionally continue; plugin may still run if deps already satisfied
                else:
                    # Original behavior: install into current environment
                    for line in pip_requirements:
                        try:
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
                                subprocess.check_call(
                                    [sys.executable, "-m", "pip", "install", line]
                                )
                        except Exception as e:
                            logger.error(
                                f"Error processing requirement '{line}' in plugin '{plugin_name}': {e}"
                            )
            else:
                logger.info(f"No dependencies found for plugin '{plugin_name}'.")

            # Store plugin info (unchanged semantics)
            plugin_info[plugin_name] = {
                "path": plugin_path,
                "dependencies": plugin_deps,  # plugin-to-plugin deps
                "metadata": metadata,
                "version": version,
                "pip_requirements": pip_requirements,
                "is_loaded": False,
                "module": None,
            }
    else:
        logger.info(
            "No plugin directory provided. Proceeding without loading directory plugins."
        )

    # ---------------------------
    # Topological sort (unchanged)
    # ---------------------------
    loading_order: List[str] = []
    visited: Dict[str, bool] = {}
    temp_marks: Dict[str, bool] = {}

    def visit(name: str):
        if name in temp_marks:
            logger.error(f"Circular dependency detected: {name}")
            raise Exception(f"Circular dependency detected involving plugin '{name}'.")
        if name not in visited:
            temp_marks[name] = True
            plugin = plugin_info.get(name)
            if not plugin:
                logger.error(f"Plugin '{name}' not found in plugin directory.")
                raise Exception(f"Plugin '{name}' not found in plugin directory.")

            if name in disabled_plugins:
                logger.error(f"Plugin '{name}' is required but is explicitly disabled.")
                raise Exception(
                    f"Plugin '{name}' is required but is explicitly disabled."
                )

            for dep in plugin["dependencies"]:
                visit(dep)

            visited[name] = True
            temp_marks.pop(name, None)
            loading_order.append(name)

    if plugin_directory:
        try:
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

        # ---------------------------
        # Load plugins in order (unchanged)
        # ---------------------------
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

        # Log not-loaded plugins (unchanged)
        not_loaded_plugins = all_plugins_in_directory - loaded_plugins

        for plugin_name in not_loaded_plugins:
            if plugin_name in disabled_plugins:
                logger.info(f"Plugin `{plugin_name}` is disabled and was not loaded.")
            elif plugin_name not in enabled_plugins and plugin_name in plugin_info:
                logger.info(
                    f"Plugin `{plugin_name}` is not enabled and was not loaded."
                )
            else:
                logger.warning(
                    f"Plugin `{plugin_name}` was not loaded for unknown reasons."
                )

        for plugin_name in disabled_plugins:
            if plugin_name not in all_plugins_in_directory:
                logger.warning(
                    f"Plugin '{plugin_name}' is specified as disabled but not found in plugin directory."
                )

    else:
        logger.info(
            "Skipping plugin loading from directory since no plugin directory is provided."
        )

    # ---------------------------
    # PLUGINS list (unchanged)
    # ---------------------------
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
                if hasattr(plugin_class, "init_plugin") and callable(
                    plugin_class.init_plugin
                ):
                    plugin_class.init_plugin(**kwargs)
                else:
                    plugin_class(**kwargs)
                loaded_plugins.add(plugin_name)
                logger.info(
                    f"Plugin '{plugin_name}' loaded successfully from '{module_path}.{module_class_name}'."
                )
            else:
                logger.warning(f"Plugin class '{module_class_name}' is not callable.")
        except Exception as e:
            logger.error(f"Error loading plugin '{plugin_name}': {e}")

    # ---------------------------
    # ENABLED_PLUGINS modules (unchanged)
    # ---------------------------
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

    # ---------------------------
    # Hot reload (unchanged)
    # ---------------------------
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
