import importlib
import logging
import sys
import types
from typing import Any, Dict, List, Set

import pytest

import plugo.services.plugin_reload as plugin_reload


# =============================
# Fixtures
# =============================


@pytest.fixture
def reload_module():
    """
    Reload the plugin_reload module for isolation.
    """
    module = importlib.reload(plugin_reload)
    yield module


def _cleanup_sys_modules(names: List[str]) -> None:
    for n in names:
        sys.modules.pop(n, None)


# =============================
# reload_module_tree tests
# =============================


def test_reload_module_tree_reloads_matching_modules(
    reload_module, monkeypatch, caplog
):
    module = reload_module

    # Fake modules
    root = types.ModuleType("myplugins")
    child = types.ModuleType("myplugins.child")
    other = types.ModuleType("otherpkg")

    sys.modules["myplugins"] = root
    sys.modules["myplugins.child"] = child
    sys.modules["otherpkg"] = other

    reloaded: List[str] = []

    def fake_reload(m):
        reloaded.append(m.__name__)
        return m

    monkeypatch.setattr(module.importlib, "reload", fake_reload)

    logger = logging.getLogger("test_reload_ok")

    with caplog.at_level(logging.DEBUG, logger=logger.name):
        module.reload_module_tree("myplugins", logger=logger)

    # Should reload only modules starting with "myplugins"
    assert set(reloaded) == {"myplugins", "myplugins.child"}
    assert "otherpkg" not in reloaded

    # Children before parent due to reversed order
    assert reloaded.index("myplugins.child") < reloaded.index("myplugins")

    msgs = [r.getMessage() for r in caplog.records]
    assert any("Reloaded module: myplugins" in m for m in msgs)
    assert any("Reloaded module: myplugins.child" in m for m in msgs)

    _cleanup_sys_modules(["myplugins", "myplugins.child", "otherpkg"])


def test_reload_module_tree_logs_warning_on_failure(reload_module, monkeypatch, caplog):
    module = reload_module

    m = types.ModuleType("mypkg")
    sys.modules["mypkg"] = m

    def fake_reload(mod):
        raise RuntimeError("boom")

    monkeypatch.setattr(module.importlib, "reload", fake_reload)

    logger = logging.getLogger("test_reload_fail")

    with caplog.at_level(logging.WARNING, logger=logger.name):
        module.reload_module_tree("mypkg", logger=logger)

    assert any(
        "Could not reload module mypkg: boom" in r.getMessage() for r in caplog.records
    )

    _cleanup_sys_modules(["mypkg"])


# =============================
# create_reload_callback tests
# =============================


def _install_fake_plugin_manager(
    monkeypatch, expected_result: Set[str], calls: Dict[str, Any]
):
    """
    Install a fake plugo.services.plugin_manager with a load_plugins stub.
    """
    pm = types.ModuleType("plugo.services.plugin_manager")

    def fake_load_plugins(**kwargs):
        calls["kwargs"] = kwargs
        return expected_result

    pm.load_plugins = fake_load_plugins
    sys.modules["plugo.services.plugin_manager"] = pm
    # No monkeypatch.setattr needed; the module import in reload_plugins reads from sys.modules.


def test_create_reload_callback_clears_matching_modules_and_loads(
    monkeypatch, caplog, reload_module
):
    module = reload_module

    # Arrange fake plugin_manager
    calls: Dict[str, Any] = {}
    expected_plugins = {"plugin_a", "plugin_b"}
    _install_fake_plugin_manager(monkeypatch, expected_plugins, calls)

    # Seed sys.modules with plugin + non-plugin modules
    sys.modules["plugins.alpha"] = types.ModuleType("plugins.alpha")
    sys.modules["plugins.beta.sub"] = types.ModuleType("plugins.beta.sub")
    sys.modules["plugo.core"] = types.ModuleType("plugo.core")
    sys.modules["other.module"] = types.ModuleType("other.module")

    logger = logging.getLogger("test_reload_cb")

    # plugin_directory basename -> "plugins" -> prefix "plugins."
    reload_cb = module.create_reload_callback(
        plugin_directory="/path/to/plugins",
        config_path="/path/to/config.json",
        logger=logger,
        clear_modules=True,
    )

    with caplog.at_level(logging.DEBUG, logger=logger.name):
        result = reload_cb()

    # Returns result from load_plugins
    assert result == expected_plugins

    # Matching plugin modules cleared
    assert "plugins.alpha" not in sys.modules
    assert "plugins.beta.sub" not in sys.modules

    # plugo.* untouched
    assert "plugo.core" in sys.modules
    # unrelated modules untouched
    assert "other.module" in sys.modules

    # Debug logs for cleared modules
    msgs = [r.getMessage() for r in caplog.records]
    assert any("Cleared module: plugins.alpha" in m for m in msgs)
    assert any("Cleared module: plugins.beta.sub" in m for m in msgs)

    # load_plugins called with expected args
    kwargs = calls["kwargs"]
    assert kwargs["plugin_directory"] == "/path/to/plugins"
    assert kwargs["config_path"] == "/path/to/config.json"
    assert kwargs["logger"] is logger

    _cleanup_sys_modules(
        [
            "plugins.alpha",
            "plugins.beta.sub",
            "plugo.core",
            "other.module",
            "plugo.services.plugin_manager",
        ]
    )


def test_create_reload_callback_respects_custom_prefixes_and_no_clear_when_disabled(
    monkeypatch, caplog, reload_module
):
    module = reload_module

    calls: Dict[str, Any] = {}
    expected_plugins = {"x"}
    _install_fake_plugin_manager(monkeypatch, expected_plugins, calls)

    # Seed sys.modules - candidate to clear
    sys.modules["custom.plugin"] = types.ModuleType("custom.plugin")

    logger = logging.getLogger("test_reload_cb_custom")

    # clear_modules=False -> should NOT clear sys.modules
    reload_cb = module.create_reload_callback(
        plugin_directory=None,
        config_path="/cfg.json",
        logger=logger,
        clear_modules=False,
        plugin_module_prefixes=["custom."],
    )

    with caplog.at_level(logging.DEBUG, logger=logger.name):
        result = reload_cb()

    assert result == expected_plugins

    # Module should remain because clear_modules=False
    assert "custom.plugin" in sys.modules

    # No "Cleared module" logs
    assert not any("Cleared module:" in r.getMessage() for r in caplog.records)

    # load_plugins still called with our args
    kwargs = calls["kwargs"]
    assert kwargs["plugin_directory"] is None
    assert kwargs["config_path"] == "/cfg.json"
    assert kwargs["logger"] is logger

    _cleanup_sys_modules(["custom.plugin", "plugo.services.plugin_manager"])


def test_create_reload_callback_logs_warning_when_clear_fails(
    monkeypatch, caplog, reload_module
):
    """
    Simulate an error during module clearing to exercise the warning path.
    """
    module = reload_module

    calls: Dict[str, Any] = {}
    expected_plugins = set()
    _install_fake_plugin_manager(monkeypatch, expected_plugins, calls)

    # We'll simulate failure by wrapping sys.modules with a proxy for one key
    class FailingDict(dict):
        def __delitem__(self, key):
            if key == "plugins.broken":
                raise RuntimeError("delete failed")
            return super().__delitem__(key)

    # Install failing modules dict (careful: restore after)
    original_modules = sys.modules
    failing_modules = FailingDict(original_modules)
    sys.modules = failing_modules  # type: ignore[assignment]

    sys.modules["plugins.broken"] = types.ModuleType("plugins.broken")

    logger = logging.getLogger("test_reload_cb_fail")

    reload_cb = module.create_reload_callback(
        plugin_directory="/path/to/plugins",
        logger=logger,
        clear_modules=True,
    )

    with caplog.at_level(logging.WARNING, logger=logger.name):
        reload_cb()

    # Warning logged for failure
    assert any(
        "Could not clear module plugins.broken: delete failed" in r.getMessage()
        for r in caplog.records
    )

    # Restore original sys.modules
    sys.modules = original_modules
    sys.modules.pop("plugo.services.plugin_manager", None)
    sys.modules.pop("plugins.broken", None)


def test_reload_module_tree_uses_default_logger_when_none(
    reload_module, monkeypatch, caplog
):
    """
    When logger is None, reload_module_tree should use its module-level logger
    (logging.getLogger(__name__)).
    """
    module = reload_module

    # Create a fake module to reload
    import types

    mod = types.ModuleType("mypkg_default")
    sys.modules["mypkg_default"] = mod

    # Make reload a no-op so we don't care about side effects
    monkeypatch.setattr(module.importlib, "reload", lambda m: m)

    # Default logger inside module is logging.getLogger(module.__name__)
    with caplog.at_level(logging.DEBUG, logger=module.__name__):
        module.reload_module_tree("mypkg_default", logger=None)

    # Ensure the debug log came from the module's default logger
    assert any(
        r.name == module.__name__ and "Reloaded module: mypkg_default" in r.getMessage()
        for r in caplog.records
    )

    _cleanup_sys_modules(["mypkg_default"])


def test_create_reload_callback_uses_default_logger_when_none(
    monkeypatch, caplog, reload_module
):
    """
    When logger is None, create_reload_callback should use its module-level logger.
    We verify:
    - plugin modules are cleared
    - logs are emitted by the default logger (module.__name__).
    """
    module = reload_module

    import types

    # Arrange fake plugin_manager + capture calls
    calls: dict = {}
    expected_plugins: Set[str] = set()
    _install_fake_plugin_manager(monkeypatch, expected_plugins, calls)

    # Seed a plugin module that should be cleared
    sys.modules["plugins.foo"] = types.ModuleType("plugins.foo")

    # logger=None -> should fall back to logging.getLogger(module.__name__)
    reload_cb = module.create_reload_callback(
        plugin_directory="/path/to/plugins",  # basename -> "plugins."
        config_path="/path/to/config.json",
        logger=None,
        clear_modules=True,
    )

    # Capture logs for the module's default logger
    with caplog.at_level(logging.DEBUG, logger=module.__name__):
        reload_cb()

    # Module with prefix "plugins." should be cleared
    assert "plugins.foo" not in sys.modules

    # And the clearing should be logged by the module's logger
    assert any(
        r.name == module.__name__ and "Cleared module: plugins.foo" in r.getMessage()
        for r in caplog.records
    )

    # load_plugins was still called
    assert calls["kwargs"]["plugin_directory"] == "/path/to/plugins"
    assert calls["kwargs"]["config_path"] == "/path/to/config.json"
    # logger passed into load_plugins should be the same default logger
    # (i.e., name == module.__name__)
    assert calls["kwargs"]["logger"].name == module.__name__

    _cleanup_sys_modules(
        [
            "plugo.services.plugin_manager",
        ]
    )
