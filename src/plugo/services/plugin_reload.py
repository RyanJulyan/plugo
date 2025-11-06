import importlib
import logging
import os
import sys
from typing import Any, Optional, Set


def reload_module_tree(
    module_name: str, logger: Optional[logging.Logger] = None
) -> None:
    """
    Reload a module and all its submodules recursively.

    Args:
        module_name: Name of the module to reload
        logger: Logger instance for logging messages
    """
    if not logger:
        logger = logging.getLogger(__name__)

    modules_to_reload = []

    # Find all modules that start with the given module name
    for name, module in list(sys.modules.items()):
        if name.startswith(module_name):
            modules_to_reload.append((name, module))

    # Reload modules in reverse order (children before parents)
    for name, module in reversed(modules_to_reload):
        try:
            importlib.reload(module)
            logger.debug(f"Reloaded module: {name}")
        except Exception as e:
            logger.warning(f"Could not reload module {name}: {e}")


def create_reload_callback(
    plugin_directory: Optional[str] = None,
    config_path: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    clear_modules: bool = True,
    plugin_module_prefixes: Optional[list[str]] = None,
    **kwargs: Any,
):
    """
    Create a callback function for reloading plugins.

    Args:
        plugin_directory: The path to the directory containing plugin folders
        config_path: The path to the plugin configuration JSON file
        logger: Logger instance for logging messages
        clear_modules: Whether to clear plugin modules from sys.modules before reloading
        plugin_module_prefixes: List of module name prefixes to clear (e.g., ['plugins.', 'my_plugins.'])
                               If None and plugin_directory is provided, will use 'plugins.'
        **kwargs: Additional keyword arguments passed to each plugin's init_plugin function

    Returns:
        A callable that reloads plugins and returns the set of loaded plugin names
    """

    if not logger:
        logger = logging.getLogger(__name__)

    # Determine plugin module prefixes to clear
    if plugin_module_prefixes is None:
        plugin_module_prefixes = []
        if plugin_directory:
            # Extract the plugin directory name to use as prefix
            plugin_dir_name = os.path.basename(plugin_directory)
            plugin_module_prefixes.append(f"{plugin_dir_name}.")

    def reload_plugins() -> Optional[Set[str]]:
        """
        Reload all plugins.

        Returns:
            Set of loaded plugin names
        """
        from plugo.services.plugin_manager import load_plugins

        if clear_modules and plugin_module_prefixes:
            # Clear only plugin modules from sys.modules to force a fresh reload
            # Avoid clearing core plugo modules
            modules_to_clear = []
            for module_name in list(sys.modules.keys()):
                # Only clear modules that match our plugin prefixes
                # Avoid clearing plugo.* modules
                if any(
                    module_name.startswith(prefix) for prefix in plugin_module_prefixes
                ) and not module_name.startswith("plugo."):
                    modules_to_clear.append(module_name)

            for module_name in modules_to_clear:
                try:
                    del sys.modules[module_name]
                    logger.debug(f"Cleared module: {module_name}")
                except Exception as e:
                    logger.warning(f"Could not clear module {module_name}: {e}")

        # Reload plugins
        return load_plugins(
            plugin_directory=plugin_directory,
            config_path=config_path,
            logger=logger,
            **kwargs,
        )

    return reload_plugins
