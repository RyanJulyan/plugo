"""
Plugin Runtime - Singleton manager for automatic hot reload.

This module manages plugin watchers in the background, automatically starting
and stopping them based on environment variables without requiring application
code to do any plumbing.
"""

import atexit
import logging
import os
import threading
from typing import Any, Dict, Optional, Set, Tuple

from plugo.services.plugin_reload import create_reload_callback
from plugo.services.plugin_watcher import PluginWatcher


class PluginRuntime:
    """
    Singleton runtime that manages plugin hot reload watchers automatically.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._watchers: Dict[Tuple[str, ...], PluginWatcher] = {}
        self._logger = logging.getLogger(__name__)
        self._watcher_lock = threading.Lock()

        # Register cleanup on exit
        atexit.register(self.shutdown)

    def ensure_hot_reload(
        self,
        plugin_directory: Optional[str] = None,
        config_path: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        **kwargs: Any,
    ) -> None:
        """
        Ensure hot reload is running if enabled via environment variable.

        This is called automatically by load_plugins. If ENABLE_PLUGIN_HOT_RELOAD
        is true, it will start a watcher in the background. If a watcher is already
        running for the same paths, it reuses it.

        Args:
            plugin_directory: The path to the directory containing plugin folders
            config_path: The path to the plugin configuration JSON file
            logger: Logger instance for logging messages
            **kwargs: Additional keyword arguments passed to plugin reload
        """
        # Check if hot reload is enabled
        enable_hot_reload = (
            os.getenv("ENABLE_PLUGIN_HOT_RELOAD", "true").lower() == "true"
        )
        if not enable_hot_reload:
            return

        # Need at least one path to watch
        if not plugin_directory and not config_path:
            return

        # Use provided logger or the runtime logger
        log = logger or self._logger

        # Check for Flask app - warn about limitations
        if "app" in kwargs:
            app = kwargs.get("app")
            # Check if it's a Flask app
            if hasattr(app, "blueprints") and hasattr(app, "debug"):
                log.warning(
                    "Flask app detected. Hot reload has limitations with Flask blueprints. "
                    "For full hot reload, Flask's debug mode (already enabled) will restart "
                    "the entire app when files change. The watchdog will detect changes but "
                    "may not reload blueprints without app restart."
                )

        # Create a cache key for this watcher configuration
        watch_key = self._create_watch_key(plugin_directory, config_path)

        with self._watcher_lock:
            # If we already have a watcher for this configuration, skip
            if watch_key in self._watchers:
                log.debug(f"Hot reload watcher already running for {watch_key}")
                return

            log.info("Initializing automatic plugin hot reload...")

            # Create reload callback
            reload_callback = create_reload_callback(
                plugin_directory=plugin_directory,
                config_path=config_path,
                logger=log,
                clear_modules=True,
                **kwargs,
            )

            # Determine which directories to watch
            watch_paths = []
            if plugin_directory and os.path.exists(plugin_directory):
                watch_paths.append(plugin_directory)
            if config_path and os.path.exists(os.path.dirname(config_path)):
                config_dir = os.path.dirname(config_path)
                if config_dir not in watch_paths:
                    watch_paths.append(config_dir)

            if not watch_paths:
                log.warning("No valid paths to watch for hot reload")
                return

            # Create and start the watcher
            watcher = PluginWatcher(
                watch_paths=watch_paths,
                reload_callback=reload_callback,
                debounce_seconds=1.0,
                logger=log,
            )
            watcher.start()

            # Store the watcher
            self._watchers[watch_key] = watcher

            log.info(
                f"Plugin hot reload is ENABLED - watching {len(watch_paths)} "
                f"director{'y' if len(watch_paths) == 1 else 'ies'} in the background"
            )

    def _create_watch_key(
        self, plugin_directory: Optional[str], config_path: Optional[str]
    ) -> Tuple[str, ...]:
        """
        Create a cache key for watcher configuration.

        Args:
            plugin_directory: Plugin directory path
            config_path: Config file path

        Returns:
            Tuple of normalized paths
        """
        key_parts = []
        if plugin_directory:
            key_parts.append(os.path.abspath(plugin_directory))
        if config_path:
            key_parts.append(os.path.abspath(config_path))
        return tuple(key_parts)

    def stop_hot_reload(
        self, plugin_directory: Optional[str] = None, config_path: Optional[str] = None
    ) -> None:
        """
        Stop a specific hot reload watcher.

        Args:
            plugin_directory: Plugin directory path
            config_path: Config file path
        """
        watch_key = self._create_watch_key(plugin_directory, config_path)

        with self._watcher_lock:
            watcher = self._watchers.pop(watch_key, None)
            if watcher:
                watcher.stop()
                self._logger.info(f"Stopped hot reload watcher for {watch_key}")

    def is_hot_reload_active(
        self, plugin_directory: Optional[str] = None, config_path: Optional[str] = None
    ) -> bool:
        """
        Check if hot reload is active for a specific configuration.

        Args:
            plugin_directory: Plugin directory path
            config_path: Config file path

        Returns:
            True if a watcher is active for this configuration
        """
        watch_key = self._create_watch_key(plugin_directory, config_path)
        with self._watcher_lock:
            return watch_key in self._watchers

    def shutdown(self) -> None:
        """
        Shutdown all watchers. Called automatically on exit.
        """
        with self._watcher_lock:
            if self._watchers:
                self._logger.info(
                    f"Shutting down {len(self._watchers)} plugin watcher(s)..."
                )
                for watcher in self._watchers.values():
                    try:
                        watcher.stop()
                    except Exception as e:
                        self._logger.error(f"Error stopping watcher: {e}")
                self._watchers.clear()


# Global singleton instance
_runtime = PluginRuntime()


def get_runtime() -> PluginRuntime:
    """
    Get the global PluginRuntime singleton.

    Returns:
        The PluginRuntime instance
    """
    return _runtime
