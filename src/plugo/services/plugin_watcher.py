import atexit
import logging
import os
import threading
import time
from typing import Any, Callable, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# Module-level flag to track if the interpreter is shutting down
_INTERPRETER_SHUTTING_DOWN = False


def _mark_shutdown():
    """Mark that the interpreter is shutting down."""
    global _INTERPRETER_SHUTTING_DOWN
    _INTERPRETER_SHUTTING_DOWN = True


# Register shutdown handler
atexit.register(_mark_shutdown)


class PluginFileEventHandler(FileSystemEventHandler):
    """
    Event handler for plugin file changes.
    """

    def __init__(
        self,
        reload_callback: Callable[[], Optional[Set[str]]],
        debounce_seconds: float = 1.0,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the event handler.

        Args:
            reload_callback: Function to call when changes are detected
            debounce_seconds: Time to wait before reloading after a change
            logger: Logger instance for logging messages
        """
        super().__init__()
        self.reload_callback = reload_callback
        self.debounce_seconds = debounce_seconds
        self.logger = logger or logging.getLogger(__name__)
        self.last_reload_time = 0
        self.pending_timer: Optional[threading.Timer] = None

    def on_any_event(self, event: FileSystemEvent) -> None:
        """
        Called when any file system event occurs.

        Args:
            event: The file system event
        """
        # Ignore directory events and certain file types
        if event.is_directory:
            return

        # Ignore certain files
        if (
            event.src_path.endswith((".pyc", ".pyo", ".swp", ".tmp"))
            or "__pycache__" in event.src_path
        ):
            return

        # Only react to Python files and config files
        if not event.src_path.endswith((".py", ".json", ".txt")):
            return

        # Silently ignore events during interpreter shutdown
        if _INTERPRETER_SHUTTING_DOWN:
            return

        self.logger.info(f"File change detected: {event.src_path} ({event.event_type})")

        # Cancel any pending reload timer
        if self.pending_timer is not None:
            try:
                self.pending_timer.cancel()
            except RuntimeError:
                # Timer may fail to cancel during shutdown
                pass

        # Schedule a new reload after the debounce period
        try:
            self.pending_timer = threading.Timer(
                self.debounce_seconds, self._trigger_reload
            )
            self.pending_timer.start()
        except RuntimeError:
            # Ignore errors during timer creation or start (can happen during shutdown)
            self.pending_timer = None

    def _trigger_reload(self) -> None:
        """
        Trigger the reload callback.
        """
        self.last_reload_time = time.time()
        self.pending_timer = None
        self.logger.info("Reloading plugins due to file changes...")

        try:
            loaded_plugins = self.reload_callback()
            if loaded_plugins:
                self.logger.info(
                    f"Successfully reloaded {len(loaded_plugins)} plugins: {loaded_plugins}"
                )
            else:
                self.logger.warning(
                    "Plugin reload returned no plugins - this may be expected if using Flask blueprints"
                )
        except Exception as e:
            self.logger.error(f"Error reloading plugins: {e}", exc_info=True)


class PluginWatcher:
    """
    Watches plugin directories for changes and triggers reloads.
    """

    def __init__(
        self,
        watch_paths: list[str],
        reload_callback: Callable[[], Optional[Set[str]]],
        debounce_seconds: float = 1.0,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the plugin watcher.

        Args:
            watch_paths: List of directory paths to watch
            reload_callback: Function to call when changes are detected
            debounce_seconds: Time to wait before reloading after a change
            logger: Logger instance for logging messages
        """
        self.watch_paths = watch_paths
        self.reload_callback = reload_callback
        self.debounce_seconds = debounce_seconds
        self.logger = logger or logging.getLogger(__name__)

        self.observer = Observer()
        self.event_handler = PluginFileEventHandler(
            reload_callback=reload_callback,
            debounce_seconds=debounce_seconds,
            logger=self.logger,
        )
        self._setup_watchers()

    def _setup_watchers(self) -> None:
        """
        Set up file system watchers for all watch paths.
        """
        for path in self.watch_paths:
            if os.path.exists(path):
                self.observer.schedule(
                    self.event_handler,
                    path,
                    recursive=True,
                )
                self.logger.info(f"Watching directory: {path}")
            else:
                self.logger.warning(f"Watch path does not exist: {path}")

    def start(self) -> None:
        """
        Start watching for file changes.
        """
        self.observer.start()
        self.logger.info("Plugin watcher started")

    def stop(self) -> None:
        """
        Stop watching for file changes.
        """
        # Cancel any pending reload timer to ensure clean shutdown
        if self.event_handler.pending_timer is not None:
            self.event_handler.pending_timer.cancel()
            self.event_handler.pending_timer = None

        self.observer.stop()
        self.observer.join()
        self.logger.info("Plugin watcher stopped")

    def __enter__(self):
        """
        Context manager entry.
        """
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit.
        """
        self.stop()
