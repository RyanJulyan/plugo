import importlib
import logging
from typing import Any, Callable, List

import pytest

import plugo.services.plugin_watcher as plugin_watcher


# =============================
# Fixtures & Test Doubles
# =============================


@pytest.fixture
def watcher_module():
    """
    Reload the module for isolation between tests.
    """
    module = importlib.reload(plugin_watcher)
    return module


class DummyEvent:
    def __init__(
        self, src_path: str, is_directory: bool = False, event_type: str = "modified"
    ):
        self.src_path = src_path
        self.is_directory = is_directory
        self.event_type = event_type


class FakeTimer:
    """
    Synchronous-ish Timer double:
    - Records interval & function
    - start() / cancel() just flip flags
    - Does NOT auto-execute callback
    """

    def __init__(self, interval: float, function: Callable, *args: Any, **kwargs: Any):
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.started = False
        self.canceled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.canceled = True


class DummyObserver:
    """
    Observer double to avoid real threads & OS watchers.
    """

    def __init__(self):
        self.scheduled = []
        self.started = False
        self.stopped = False
        self.joined = False

    def schedule(self, handler, path, recursive=True):
        self.scheduled.append((handler, path, recursive))

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def join(self):
        self.joined = True


def patch_timer(watcher_module, monkeypatch, created: List[FakeTimer]):
    def _factory(interval, function, *args, **kwargs):
        t = FakeTimer(interval, function, *args, **kwargs)
        created.append(t)
        return t

    monkeypatch.setattr(watcher_module.threading, "Timer", _factory)


def patch_observer(watcher_module, monkeypatch, created: List[DummyObserver]):
    def _factory(*args, **kwargs):
        o = DummyObserver()
        created.append(o)
        return o

    monkeypatch.setattr(watcher_module, "Observer", _factory)


# =============================
# PluginFileEventHandler tests
# =============================


def test_file_event_handler_ignores_directories(watcher_module, monkeypatch):
    created_timers: List[FakeTimer] = []
    patch_timer(watcher_module, monkeypatch, created_timers)

    handler = watcher_module.PluginFileEventHandler(
        reload_callback=lambda: None,
        debounce_seconds=1.0,
    )

    event = DummyEvent(src_path="/plugins/some_dir", is_directory=True)
    handler.on_any_event(event)

    assert handler.pending_timer is None
    assert created_timers == []


@pytest.mark.parametrize(
    "path",
    [
        "/plugins/__pycache__/x.py",
        "/plugins/foo.pyc",
        "/plugins/bar.pyo",
        "/plugins/tmp.swp",
        "/plugins/file.tmp",
    ],
)
def test_file_event_handler_ignores_ignored_files(watcher_module, monkeypatch, path):
    created_timers: List[FakeTimer] = []
    patch_timer(watcher_module, monkeypatch, created_timers)

    handler = watcher_module.PluginFileEventHandler(
        reload_callback=lambda: None,
        debounce_seconds=1.0,
    )

    handler.on_any_event(DummyEvent(src_path=path, is_directory=False))
    assert handler.pending_timer is None
    assert created_timers == []


def test_file_event_handler_ignores_unrelated_extensions(watcher_module, monkeypatch):
    created_timers: List[FakeTimer] = []
    patch_timer(watcher_module, monkeypatch, created_timers)

    handler = watcher_module.PluginFileEventHandler(
        reload_callback=lambda: None,
        debounce_seconds=1.0,
    )

    handler.on_any_event(DummyEvent(src_path="/plugins/readme.md", is_directory=False))

    assert handler.pending_timer is None
    assert created_timers == []


def test_file_event_handler_sets_timer_for_valid_file(
    watcher_module, monkeypatch, caplog
):
    created_timers: List[FakeTimer] = []
    patch_timer(watcher_module, monkeypatch, created_timers)

    handler = watcher_module.PluginFileEventHandler(
        reload_callback=lambda: None,
        debounce_seconds=2.5,
    )

    with caplog.at_level(logging.INFO, logger=watcher_module.__name__):
        handler.on_any_event(
            DummyEvent(src_path="/plugins/plugin.py", is_directory=False)
        )

    # Timer created & started
    assert len(created_timers) == 1
    t = created_timers[0]
    assert t.started is True
    assert t.interval == 2.5
    assert handler.pending_timer is t

    # Log emitted
    assert any("File change detected:" in r.getMessage() for r in caplog.records)


def test_file_event_handler_debounce_cancels_previous_timer(
    watcher_module, monkeypatch
):
    created_timers: List[FakeTimer] = []
    patch_timer(watcher_module, monkeypatch, created_timers)

    handler = watcher_module.PluginFileEventHandler(
        reload_callback=lambda: None,
        debounce_seconds=1.0,
    )

    # First event
    handler.on_any_event(DummyEvent(src_path="/plugins/a.py", is_directory=False))
    # Second event quickly after
    handler.on_any_event(DummyEvent(src_path="/plugins/b.py", is_directory=False))

    assert len(created_timers) == 2
    first, second = created_timers

    # First timer should have been cancelled
    assert first.canceled is True
    # Second is the active one
    assert handler.pending_timer is second
    assert second.started is True
    assert not second.canceled


def test_trigger_reload_logs_success(watcher_module, caplog):
    loaded = {"p1", "p2"}

    def callback():
        return loaded

    handler = watcher_module.PluginFileEventHandler(
        reload_callback=callback,
        debounce_seconds=0.1,
    )

    with caplog.at_level(logging.INFO, logger=watcher_module.__name__):
        handler._trigger_reload()

    assert handler.pending_timer is None
    assert handler.last_reload_time > 0

    msgs = [r.getMessage() for r in caplog.records]
    assert any("Reloading plugins due to file changes..." in m for m in msgs)
    assert any("Successfully reloaded 2 plugins" in m for m in msgs)


@pytest.mark.parametrize("result", [None, set()])
def test_trigger_reload_logs_warning_on_empty(watcher_module, caplog, result):
    def callback():
        return result

    handler = watcher_module.PluginFileEventHandler(
        reload_callback=callback,
        debounce_seconds=0.1,
    )

    with caplog.at_level(logging.WARNING, logger=watcher_module.__name__):
        handler._trigger_reload()

    msgs = [r.getMessage() for r in caplog.records]
    assert any("Plugin reload returned no plugins" in m for m in msgs)


def test_trigger_reload_logs_error_on_exception(watcher_module, caplog):
    def callback():
        raise RuntimeError("boom")

    handler = watcher_module.PluginFileEventHandler(
        reload_callback=callback,
        debounce_seconds=0.1,
    )

    with caplog.at_level(logging.ERROR, logger=watcher_module.__name__):
        handler._trigger_reload()

    msgs = [r.getMessage() for r in caplog.records]
    assert any("Error reloading plugins: boom" in m for m in msgs)


# =============================
# PluginWatcher tests
# =============================


def test_setup_watchers_existing_and_missing_paths(watcher_module, monkeypatch, caplog):
    """
    _setup_watchers should:
    - schedule observer for existing paths
    - warn for missing paths
    """
    created_observers: List[DummyObserver] = []
    patch_observer(watcher_module, monkeypatch, created_observers)

    # Only /exists is considered present
    def fake_exists(path: str) -> bool:
        return path == "/exists"

    monkeypatch.setattr(watcher_module.os.path, "exists", fake_exists)

    with caplog.at_level(logging.INFO, logger=watcher_module.__name__):
        watcher = watcher_module.PluginWatcher(
            watch_paths=["/exists", "/missing"],
            reload_callback=lambda: None,
            debounce_seconds=0.1,
        )

    assert len(created_observers) == 1
    observer = created_observers[0]

    # Only /exists scheduled
    assert len(observer.scheduled) == 1
    handler, path, recursive = observer.scheduled[0]
    assert isinstance(handler, watcher_module.PluginFileEventHandler)
    assert path == "/exists"
    assert recursive is True

    msgs = [r.getMessage() for r in caplog.records]
    assert any("Watching directory: /exists" in m for m in msgs)
    assert any("Watch path does not exist: /missing" in m for m in msgs)


def test_plugin_watcher_start_stops_and_logs(watcher_module, monkeypatch, caplog):
    created_observers: List[DummyObserver] = []
    patch_observer(watcher_module, monkeypatch, created_observers)
    monkeypatch.setattr(watcher_module.os.path, "exists", lambda p: True)

    watcher = watcher_module.PluginWatcher(
        watch_paths=["/plugins"],
        reload_callback=lambda: None,
        debounce_seconds=0.1,
    )
    observer = created_observers[0]

    with caplog.at_level(logging.INFO, logger=watcher_module.__name__):
        watcher.start()

    assert observer.started is True
    assert any("Plugin watcher started" in r.getMessage() for r in caplog.records)

    caplog.clear()

    with caplog.at_level(logging.INFO, logger=watcher_module.__name__):
        watcher.stop()

    assert observer.stopped is True
    assert observer.joined is True
    assert any("Plugin watcher stopped" in r.getMessage() for r in caplog.records)


def test_plugin_watcher_context_manager(watcher_module, monkeypatch):
    created_observers: List[DummyObserver] = []
    patch_observer(watcher_module, monkeypatch, created_observers)
    monkeypatch.setattr(watcher_module.os.path, "exists", lambda p: True)

    with watcher_module.PluginWatcher(
        watch_paths=["/plugins"],
        reload_callback=lambda: None,
        debounce_seconds=0.1,
    ) as w:
        # Inside context: started
        observer = created_observers[0]
        assert observer.started is True
        assert w is not None

    # After context: stopped & joined
    assert observer.stopped is True
    assert observer.joined is True
