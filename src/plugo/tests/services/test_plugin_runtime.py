import importlib
import logging
from typing import Any, Dict, List

import pytest

import plugo.services.plugin_runtime as plugin_runtime


# ---------- Fixtures ----------


@pytest.fixture
def runtime_module():
    """
    Reload the module before each test to ensure a fresh singleton + clean state.
    Also guarantees _runtime is recreated.
    """
    module = importlib.reload(plugin_runtime)
    # Safety: ensure we start from a clean state
    module.get_runtime().shutdown()
    module.get_runtime()._watchers.clear()
    yield module
    # Cleanup after each test
    module.get_runtime().shutdown()
    module.get_runtime()._watchers.clear()


@pytest.fixture
def runtime(runtime_module):
    """Return the global PluginRuntime instance for convenience."""
    return runtime_module.get_runtime()


# ---------- Helpers ----------


class DummyWatcher:
    """
    Test double for PluginWatcher.
    Records constructor args and start/stop calls.
    """

    def __init__(
        self,
        watch_paths,
        reload_callback,
        debounce_seconds,
        logger,
    ):
        self.watch_paths = watch_paths
        self.reload_callback = reload_callback
        self.debounce_seconds = debounce_seconds
        self.logger = logger
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def patch_dummy_watcher(runtime_module, monkeypatch, created: List[DummyWatcher]):
    def _factory(*args, **kwargs):
        watcher = DummyWatcher(*args, **kwargs)
        created.append(watcher)
        return watcher

    monkeypatch.setattr(runtime_module, "PluginWatcher", _factory)


# ---------- Tests ----------


def test_singleton_behavior(runtime_module, runtime):
    """PluginRuntime should behave as a singleton and match get_runtime()."""
    from_instance_1 = runtime_module.PluginRuntime()
    from_instance_2 = runtime_module.PluginRuntime()
    from_get = runtime_module.get_runtime()

    assert from_instance_1 is from_instance_2 is from_get is runtime


def test_ensure_hot_reload_env_disabled(runtime_module, runtime, monkeypatch):
    """
    If ENABLE_PLUGIN_HOT_RELOAD is 'false', no watcher must be created.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "false")

    # If PluginWatcher is ever instantiated, the test should fail.
    def _fail(*args, **kwargs):
        raise AssertionError("PluginWatcher should not be instantiated when disabled")

    monkeypatch.setattr(runtime_module, "PluginWatcher", _fail)

    runtime.ensure_hot_reload(
        plugin_directory="/plugins", config_path="/config/plugins.json"
    )

    assert runtime._watchers == {}


def test_ensure_hot_reload_no_paths(runtime_module, runtime, monkeypatch):
    """
    If neither plugin_directory nor config_path is provided, do nothing.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")

    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)

    runtime.ensure_hot_reload(plugin_directory=None, config_path=None)

    assert created == []
    assert runtime._watchers == {}


def test_ensure_hot_reload_starts_watcher(runtime_module, runtime, monkeypatch, caplog):
    """
    When enabled and valid paths exist, a watcher should be created, started,
    stored in _watchers, and reload_callback created with expected kwargs.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")

    # Pretend all paths exist
    monkeypatch.setattr(
        runtime_module.os.path,
        "exists",
        lambda path: True,
    )

    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)

    callback_kwargs: Dict[str, Any] = {}

    def fake_create_reload_callback(**kwargs):
        callback_kwargs.update(kwargs)
        return lambda: None

    monkeypatch.setattr(
        runtime_module, "create_reload_callback", fake_create_reload_callback
    )

    # Scope logging to the module logger to ensure we capture its INFO logs
    with caplog.at_level(logging.INFO, logger=runtime_module.__name__):
        runtime.ensure_hot_reload(
            plugin_directory="/plugins",
            config_path="/config/plugins.json",
        )

    # One watcher created
    assert len(created) == 1
    watcher = created[0]

    # Watcher started
    assert watcher.started is True

    # Correct watch key and registry entry
    watch_key = runtime._create_watch_key("/plugins", "/config/plugins.json")
    assert watch_key in runtime._watchers
    assert runtime._watchers[watch_key] is watcher

    # Watch paths should contain plugin dir and config dir (unique)
    assert set(watcher.watch_paths) == {"/plugins", "/config"}

    # Reload callback called with expected args
    assert callback_kwargs["plugin_directory"] == "/plugins"
    assert callback_kwargs["config_path"] == "/config/plugins.json"
    assert callback_kwargs["clear_modules"] is True

    # Confirm the "enabled" message was logged (using records instead of text-only scan)
    assert any(
        "Plugin hot reload is ENABLED" in record.getMessage()
        for record in caplog.records
    )


def test_ensure_hot_reload_reuses_existing_watcher(
    runtime_module, runtime, monkeypatch
):
    """
    Calling ensure_hot_reload with the same (plugin_directory, config_path)
    must reuse the existing watcher instead of creating a new one.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")
    monkeypatch.setattr(runtime_module.os.path, "exists", lambda path: True)

    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)
    monkeypatch.setattr(
        runtime_module, "create_reload_callback", lambda **_: (lambda: None)
    )

    # First call: creates watcher
    runtime.ensure_hot_reload("/plugins", "/config/plugins.json")
    # Second call: should NOT create another watcher
    runtime.ensure_hot_reload("/plugins", "/config/plugins.json")

    assert len(created) == 1  # only one watcher constructed

    watch_key = runtime._create_watch_key("/plugins", "/config/plugins.json")
    assert watch_key in runtime._watchers


def test_stop_hot_reload_stops_and_removes(runtime_module, runtime, monkeypatch):
    """
    stop_hot_reload should stop the watcher and remove it from _watchers.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")
    monkeypatch.setattr(runtime_module.os.path, "exists", lambda path: True)

    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)
    monkeypatch.setattr(
        runtime_module, "create_reload_callback", lambda **_: (lambda: None)
    )

    runtime.ensure_hot_reload("/plugins", "/config/plugins.json")
    watch_key = runtime._create_watch_key("/plugins", "/config/plugins.json")

    watcher = runtime._watchers[watch_key]
    assert watcher.stopped is False

    runtime.stop_hot_reload("/plugins", "/config/plugins.json")

    assert watcher.stopped is True
    assert watch_key not in runtime._watchers


def test_is_hot_reload_active(runtime_module, runtime, monkeypatch):
    """
    is_hot_reload_active should correctly reflect watcher presence.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")
    monkeypatch.setattr(runtime_module.os.path, "exists", lambda path: True)

    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)
    monkeypatch.setattr(
        runtime_module, "create_reload_callback", lambda **_: (lambda: None)
    )

    # Initially inactive
    assert runtime.is_hot_reload_active("/plugins", "/config/plugins.json") is False

    # After starting
    runtime.ensure_hot_reload("/plugins", "/config/plugins.json")
    assert runtime.is_hot_reload_active("/plugins", "/config/plugins.json") is True

    # After stopping
    runtime.stop_hot_reload("/plugins", "/config/plugins.json")
    assert runtime.is_hot_reload_active("/plugins", "/config/plugins.json") is False


def test_shutdown_stops_all_watchers(runtime_module, runtime, monkeypatch):
    """
    shutdown should stop all watchers and clear _watchers.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")
    monkeypatch.setattr(runtime_module.os.path, "exists", lambda path: True)

    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)
    monkeypatch.setattr(
        runtime_module, "create_reload_callback", lambda **_: (lambda: None)
    )

    # Create two different watcher configurations
    runtime.ensure_hot_reload("/plugins_a", "/config_a.json")
    runtime.ensure_hot_reload("/plugins_b", "/config_b.json")

    assert len(created) == 2
    assert len(runtime._watchers) == 2

    runtime.shutdown()

    # All watchers stopped
    for w in created:
        assert w.stopped is True

    # Registry cleared
    assert runtime._watchers == {}


def test_ensure_hot_reload_flask_app_warning(
    runtime_module, runtime, monkeypatch, caplog
):
    """
    When a Flask-like app is passed via kwargs, a warning about blueprint
    hot reload limitations should be logged.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")

    # Pretend all paths exist
    monkeypatch.setattr(runtime_module.os.path, "exists", lambda path: True)

    # Use DummyWatcher so we don't start real threads
    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)

    # Simple no-op reload callback
    monkeypatch.setattr(
        runtime_module,
        "create_reload_callback",
        lambda **_: (lambda: None),
    )

    # Minimal Flask-like app
    class FakeFlaskApp:
        def __init__(self):
            self.blueprints = {}
            self.debug = True

    app = FakeFlaskApp()

    # Capture warnings from this module's logger
    with caplog.at_level(logging.WARNING, logger=runtime_module.__name__):
        runtime.ensure_hot_reload(
            plugin_directory="/plugins",
            config_path="/config/plugins.json",
            app=app,
        )

    # Watcher should still be created
    assert len(created) == 1

    # And the Flask-specific warning should be present
    assert any(
        "Flask app detected. Hot reload has limitations with Flask blueprints."
        in record.getMessage()
        for record in caplog.records
    )


def test_ensure_hot_reload_no_valid_paths_logs_warning(
    runtime_module, runtime, monkeypatch, caplog
):
    """
    If neither plugin_directory nor config_path resolve to existing paths,
    no watcher is created and a warning is logged.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")

    # No paths exist
    monkeypatch.setattr(runtime_module.os.path, "exists", lambda path: False)

    # Fail if a watcher is somehow created
    def _fail(*args, **kwargs):
        raise AssertionError(
            "PluginWatcher should not be created when no paths are valid"
        )

    monkeypatch.setattr(runtime_module, "PluginWatcher", _fail)
    monkeypatch.setattr(
        runtime_module, "create_reload_callback", lambda **_: (lambda: None)
    )

    with caplog.at_level(logging.WARNING, logger=runtime_module.__name__):
        runtime.ensure_hot_reload(
            plugin_directory="/does/not/exist/plugins",
            config_path="/also/invalid/config.json",
        )

    assert runtime._watchers == {}
    assert any(
        "No valid paths to watch for hot reload" in record.getMessage()
        for record in caplog.records
    )


def test_ensure_hot_reload_uses_config_dir_when_plugin_dir_missing(
    runtime_module, runtime, monkeypatch
):
    """
    If plugin_directory does not exist but the config_path directory does,
    we should watch only the config directory.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")

    plugin_directory = "/missing/plugins"
    config_path = "/valid/config/plugins.json"
    config_dir = "/valid/config"

    def fake_exists(path: str) -> bool:
        return path == config_dir  # only config_dir exists

    monkeypatch.setattr(runtime_module.os.path, "exists", fake_exists)

    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)

    monkeypatch.setattr(
        runtime_module, "create_reload_callback", lambda **_: (lambda: None)
    )

    runtime.ensure_hot_reload(
        plugin_directory=plugin_directory,
        config_path=config_path,
    )

    # One watcher created
    assert len(created) == 1
    watcher = created[0]

    # Should only be watching the config directory
    assert watcher.watch_paths == [config_dir]

    # Watcher registered under correct key
    watch_key = runtime._create_watch_key(plugin_directory, config_path)
    assert watch_key in runtime._watchers
    assert runtime._watchers[watch_key] is watcher


def test_ensure_hot_reload_deduplicates_plugin_and_config_dirs(
    runtime_module, runtime, monkeypatch
):
    """
    When config_path's directory is the same as plugin_directory,
    it should not be added twice to watch_paths.
    """
    monkeypatch.setenv("ENABLE_PLUGIN_HOT_RELOAD", "true")

    plugin_directory = "/plugins"
    config_path = "/plugins/plugins.json"  # same directory as plugin_directory

    # Everything exists
    monkeypatch.setattr(runtime_module.os.path, "exists", lambda path: True)

    created: List[DummyWatcher] = []
    patch_dummy_watcher(runtime_module, monkeypatch, created)

    monkeypatch.setattr(
        runtime_module, "create_reload_callback", lambda **_: (lambda: None)
    )

    runtime.ensure_hot_reload(
        plugin_directory=plugin_directory,
        config_path=config_path,
    )

    assert len(created) == 1
    watcher = created[0]

    # Only one unique path should be watched
    assert watcher.watch_paths == [plugin_directory]

    watch_key = runtime._create_watch_key(plugin_directory, config_path)
    assert watch_key in runtime._watchers
    assert runtime._watchers[watch_key] is watcher


def test_shutdown_logs_error_when_watcher_stop_fails(runtime_module, runtime, caplog):
    """
    If a watcher.stop() raises, shutdown should:
    - log an error
    - continue processing other watchers
    - clear the _watchers dict
    """

    # Local test doubles so we don't touch real PluginWatcher
    class GoodWatcher:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    class BadWatcher:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True
            raise RuntimeError("boom from stop")

    good = GoodWatcher()
    bad = BadWatcher()

    # Seed the runtime with two watchers: one good, one that fails
    runtime._watchers = {
        ("good",): good,
        ("bad",): bad,
    }

    with caplog.at_level(logging.ERROR, logger=runtime_module.__name__):
        runtime.shutdown()

    # Good watcher should be stopped
    assert good.stopped is True
    # Bad watcher stop() was called even though it raised
    assert bad.stopped is True

    # All watchers should be cleared even if one failed
    assert runtime._watchers == {}

    # Error should be logged for the failing watcher
    assert any(
        "Error stopping watcher:" in record.getMessage() for record in caplog.records
    )
