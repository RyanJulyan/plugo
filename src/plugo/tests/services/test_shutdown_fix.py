"""
Test suite for plugin watcher shutdown fix.

This module tests the plugin watcher's behavior during interpreter shutdown:
1. Verifies that file events are normally processed
2. Verifies that file events during shutdown are safely ignored
3. Ensures no exceptions are raised during shutdown
"""

import logging
import pytest
from unittest.mock import Mock
from watchdog.events import FileSystemEvent

from plugo.services.plugin_watcher import (
    PluginFileEventHandler,
    _mark_shutdown,
)


# ---------- Fixtures ----------


@pytest.fixture
def logger():
    """Provide a logger for tests."""
    return logging.getLogger(__name__)


@pytest.fixture
def dummy_reload_callback():
    """Provide a dummy reload callback."""

    def callback():
        return {"test_plugin"}

    return callback


@pytest.fixture
def event_handler(dummy_reload_callback, logger):
    """Provide a PluginFileEventHandler instance."""
    return PluginFileEventHandler(
        reload_callback=dummy_reload_callback,
        debounce_seconds=0.1,
        logger=logger,
    )


@pytest.fixture
def reset_shutdown_flag():
    """Reset the shutdown flag before and after each test."""
    # Store original value
    import plugo.services.plugin_watcher as pw

    original_value = pw._INTERPRETER_SHUTTING_DOWN

    # Reset before test
    pw._INTERPRETER_SHUTTING_DOWN = False

    yield

    # Reset after test
    pw._INTERPRETER_SHUTTING_DOWN = original_value


# ---------- Helpers ----------


class MockFileSystemEvent(FileSystemEvent):
    """Mock FileSystemEvent for testing."""

    def __init__(self, src_path="/tmp/test_plugin.py", event_type="modified"):
        self.is_directory = False
        self.src_path = src_path
        self.event_type = event_type


# ---------- Normal Operation Tests ----------


def test_python_file_event_is_processed(event_handler):
    """Test that Python file changes are processed."""
    event = MockFileSystemEvent("/tmp/test_plugin.py", "modified")

    # Should not raise any exception
    event_handler.on_any_event(event)

    # Should have created a pending timer
    assert event_handler.pending_timer is not None


def test_json_file_event_is_processed(event_handler):
    """Test that JSON config file changes are processed."""
    event = MockFileSystemEvent("/tmp/config.json", "modified")

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is not None


def test_txt_file_event_is_processed(event_handler):
    """Test that text file changes are processed."""
    event = MockFileSystemEvent("/tmp/requirements.txt", "modified")

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is not None


def test_directory_event_is_ignored(event_handler):
    """Test that directory events are ignored."""
    event = Mock(spec=FileSystemEvent)
    event.is_directory = True

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is None


def test_pyc_file_event_is_ignored(event_handler):
    """Test that compiled Python files are ignored."""
    event = MockFileSystemEvent("/tmp/test_plugin.pyc", "modified")

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is None


def test_pycache_event_is_ignored(event_handler):
    """Test that __pycache__ events are ignored."""
    event = MockFileSystemEvent("/tmp/__pycache__/test.py", "modified")

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is None


def test_swp_file_event_is_ignored(event_handler):
    """Test that editor swap files are ignored."""
    event = MockFileSystemEvent("/tmp/test_plugin.swp", "modified")

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is None


def test_tmp_file_event_is_ignored(event_handler):
    """Test that temporary files are ignored."""
    event = MockFileSystemEvent("/tmp/test_plugin.tmp", "modified")

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is None


def test_unsupported_file_type_is_ignored(event_handler):
    """Test that unsupported file types are ignored."""
    event = MockFileSystemEvent("/tmp/test_plugin.md", "modified")

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is None


# ---------- Shutdown Tests ----------


def test_file_event_during_shutdown_is_ignored(event_handler, reset_shutdown_flag):
    """Test that file events during shutdown are safely ignored."""
    event = MockFileSystemEvent("/tmp/test_plugin.py", "modified")

    # Simulate shutdown
    _mark_shutdown()

    # Should not raise any exception and should not create timer
    event_handler.on_any_event(event)

    assert event_handler.pending_timer is None


def test_no_exception_raised_during_shutdown(event_handler, reset_shutdown_flag):
    """Test that no exceptions are raised when processing events during shutdown."""
    event = MockFileSystemEvent("/tmp/test_plugin.py", "modified")

    _mark_shutdown()

    # Should complete without raising any exception
    event_handler.on_any_event(event)  # Should not raise


def test_shutdown_prevents_all_file_events(event_handler, reset_shutdown_flag):
    """Test that all file types are ignored during shutdown."""
    test_cases = [
        ("/tmp/plugin.py", "modified"),
        ("/tmp/config.json", "created"),
        ("/tmp/requirements.txt", "deleted"),
    ]

    _mark_shutdown()

    for src_path, event_type in test_cases:
        event = MockFileSystemEvent(src_path, event_type)
        event_handler.on_any_event(event)
        assert event_handler.pending_timer is None


# ---------- Timer Management Tests ----------


def test_pending_timer_is_cancelled_on_new_event(event_handler):
    """Test that a pending timer is cancelled when a new event arrives."""
    event = MockFileSystemEvent("/tmp/test_plugin.py", "modified")

    # Create first timer
    event_handler.on_any_event(event)
    first_timer = event_handler.pending_timer
    assert first_timer is not None

    # Create second timer - should cancel the first
    event_handler.on_any_event(event)
    second_timer = event_handler.pending_timer

    assert second_timer is not None
    assert first_timer is not second_timer
    # First timer should have been cancelled
    assert not first_timer.is_alive() or first_timer.finished.is_set()


def test_timer_is_started_automatically(event_handler):
    """Test that timers are automatically started."""
    event = MockFileSystemEvent("/tmp/test_plugin.py", "modified")

    event_handler.on_any_event(event)

    assert event_handler.pending_timer is not None
    assert event_handler.pending_timer.is_alive()
