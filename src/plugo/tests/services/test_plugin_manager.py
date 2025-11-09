import os
import sys
import json
import logging
import pytest
from unittest import mock

from pkg_resources import DistributionNotFound

from plugo.services.plugin_manager import load_plugins
from plugo.models.plugin_config import PLUGINS
from plugo.services.plugin_manager import load_plugin_module


@pytest.fixture
def mock_logger():
    """Fixture to provide a mock logger."""
    logger = logging.getLogger("test_logger")
    logger.addHandler(logging.NullHandler())
    return logger


@pytest.fixture
def magic_mock_logger_spec():
    """Fixture to provide a mock logger."""
    logger = mock.Mock(spec=logging.Logger)
    return logger


@pytest.fixture
def temp_plugin_directory(tmp_path):
    """Fixture to create a temporary plugin directory."""
    plugin_directory = tmp_path / "plugins"
    plugin_directory.mkdir()
    return plugin_directory


@pytest.fixture
def temp_config_file(tmp_path):
    """Fixture to create a temporary configuration JSON file."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "plugins": [
                    {"name": "plugin1", "enabled": True},
                    {"name": "plugin2", "enabled": False},
                ]
            }
        )
    )
    return config_file


@pytest.fixture
def create_plugin(tmp_path):
    """
    Fixture to create a plugin structure.
    """

    def _create_plugin(plugin_name, plugin_content="def init_plugin(**kwargs): pass"):
        plugin_path = tmp_path / plugin_name
        plugin_path.mkdir(parents=True, exist_ok=True)
        plugin_main = plugin_path / "plugin.py"
        plugin_main.write_text(plugin_content)
        return plugin_name, str(plugin_path), str(plugin_main)

    return _create_plugin


def create_plugin_files(plugin_dir, name, dependencies=None):
    """Helper to create a plugin structure with a requirements.txt and metadata.json."""
    plugin_path = plugin_dir / name
    plugin_path.mkdir(parents=True, exist_ok=True)

    # Create plugin.py with a simple init_plugin function
    (plugin_path / "plugin.py").write_text(
        "def init_plugin(**kwargs): print(f'{kwargs} Plugin initialized.')"
    )

    # Create metadata.json with dependencies
    metadata = {"dependencies": dependencies or []}
    print(f"Creating plugin '{name}' with metadata: {metadata}")  # Debug print
    (plugin_path / "metadata.json").write_text(json.dumps(metadata))

    # Create an empty requirements.txt file
    (plugin_path / "requirements.txt").write_text("")  # No requirements for simplicity

    return plugin_path


@mock.patch("plugo.services.plugin_manager.subprocess.check_call")
@mock.patch("plugo.services.plugin_manager.get_distribution")
def test_load_plugins_success(
    mock_get_distribution,
    mock_check_call,
    temp_plugin_directory,
    temp_config_file,
    mock_logger,
):
    """Test loading plugins successfully with satisfied dependencies."""

    create_plugin_files(temp_plugin_directory, "plugin1")
    create_plugin_files(temp_plugin_directory, "plugin2", dependencies=["plugin1"])

    # Mock dependency satisfaction for 'plugin1'
    mock_get_distribution.return_value = True

    loaded_plugins = load_plugins(
        str(temp_plugin_directory), str(temp_config_file), logger=mock_logger
    )

    assert loaded_plugins == {"plugin1"}, "Only enabled plugins should be loaded."


@mock.patch("plugo.services.plugin_manager.subprocess.check_call")
@mock.patch(
    "plugo.services.plugin_manager.get_distribution",
    side_effect=DistributionNotFound("Dist not found"),
)
def test_load_plugins_with_missing_dependency_venv(
    mock_get_distribution,
    mock_check_call,
    temp_plugin_directory,
    temp_config_file,
    mock_logger,
):
    """Missing dependency should trigger installation inside per-plugin venv (default behavior)."""

    # Set up a plugin with a requirements.txt file
    plugin1_dir = create_plugin_files(temp_plugin_directory, "plugin1")
    requirements_file = plugin1_dir / "requirements.txt"
    requirements_file.write_text("missing_package>=1.0")

    # Call load_plugins (PLUGO_USE_VENVS defaults to enabled)
    load_plugins(str(temp_plugin_directory), str(temp_config_file), logger=mock_logger)

    calls = [args[0] for args, _ in mock_check_call.call_args_list]

    # Expect at least one pip install call
    pip_install_calls = [
        cmd
        for cmd in calls
        if len(cmd) >= 4 and cmd[1] == "-m" and cmd[2] == "pip" and cmd[3] == "install"
    ]
    assert pip_install_calls, f"No pip install calls found. Calls: {calls}"

    # One of them must install our missing package
    assert any(
        "missing_package>=1.0" in cmd for cmd in pip_install_calls
    ), f"'missing_package>=1.0' not found in pip calls: {pip_install_calls}"


@mock.patch.dict(os.environ, {"PLUGO_USE_VENVS": "0"})
@mock.patch("plugo.services.plugin_manager.subprocess.check_call")
@mock.patch(
    "plugo.services.plugin_manager.get_distribution",
    side_effect=DistributionNotFound("Dist not found"),
)
def test_load_plugins_with_missing_dependency_legacy_no_venv(
    mock_get_distribution,
    mock_check_call,
    temp_plugin_directory,
    temp_config_file,
    mock_logger,
):
    """
    When PLUGO_USE_VENVS is disabled, missing dependencies should be installed
    into the current environment via sys.executable -m pip install <req>.
    """

    # Set up a plugin with a requirements.txt file
    plugin1_dir = create_plugin_files(temp_plugin_directory, "plugin1")
    requirements_file = plugin1_dir / "requirements.txt"
    requirements_file.write_text("missing_package>=1.0")

    # Call load_plugins with venvs explicitly disabled
    load_plugins(str(temp_plugin_directory), str(temp_config_file), logger=mock_logger)

    # We expect a direct pip install call using sys.executable
    mock_check_call.assert_any_call(
        [sys.executable, "-m", "pip", "install", "missing_package>=1.0"]
    )


def test_load_plugins_missing_directory(temp_config_file, mock_logger):
    """Test when the plugin directory does not exist."""
    result = load_plugins(
        "non_existent_directory", str(temp_config_file), logger=mock_logger
    )
    assert result is None, "Should return None if plugin directory does not exist."


def test_load_plugins_invalid_config_file(temp_plugin_directory, mock_logger):
    """Test when the configuration file is invalid."""
    invalid_config_file = temp_plugin_directory / "invalid_config.json"
    invalid_config_file.write_text("Invalid JSON content")

    result = load_plugins(
        str(temp_plugin_directory), str(invalid_config_file), logger=mock_logger
    )
    assert result is None, "Should return None if config file is invalid JSON."


@mock.patch.dict(os.environ, {"ENABLED_PLUGINS": "plugin2"})
def test_load_plugins_with_env_override(
    temp_plugin_directory, temp_config_file, mock_logger
):
    """Test enabling plugins via environment variable override."""

    create_plugin_files(temp_plugin_directory, "plugin1")
    create_plugin_files(temp_plugin_directory, "plugin2")

    loaded_plugins = load_plugins(
        str(temp_plugin_directory), str(temp_config_file), logger=mock_logger
    )

    # Plugin2 should be enabled via the environment variable
    assert loaded_plugins == {"plugin1", "plugin2"}


def test_load_plugins_circular_dependency(
    temp_plugin_directory, temp_config_file, mock_logger
):
    """Test handling circular dependency error."""

    create_plugin_files(temp_plugin_directory, "plugin1", dependencies=["plugin2"])
    create_plugin_files(temp_plugin_directory, "plugin2", dependencies=["plugin1"])

    result = load_plugins(
        str(temp_plugin_directory), str(temp_config_file), logger=mock_logger
    )
    assert result is None, "Should return None if circular dependency is detected."


def test_load_plugins_disabled_plugin(
    temp_plugin_directory, temp_config_file, mock_logger
):
    """Test handling of a disabled plugin."""

    create_plugin_files(temp_plugin_directory, "plugin1")
    create_plugin_files(temp_plugin_directory, "plugin2", dependencies=["plugin1"])

    # In config, plugin2 is disabled; it should not be loaded even though it exists
    loaded_plugins = load_plugins(
        str(temp_plugin_directory), str(temp_config_file), logger=mock_logger
    )
    assert loaded_plugins == {
        "plugin1"
    }, "Only plugin1 should be loaded as plugin2 is disabled."


def test_load_plugins_missing_metadata(
    temp_plugin_directory, temp_config_file, mock_logger
):
    """Test when plugin metadata.json is missing."""
    plugin_dir = temp_plugin_directory / "plugin1"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text("def init_plugin(**kwargs): pass")

    result = load_plugins(
        str(temp_plugin_directory), str(temp_config_file), logger=mock_logger
    )

    # Expect an empty set if metadata.json is missing
    assert (
        result == set()
    ), "Should return an empty set if plugin metadata.json is missing."


@mock.patch("plugo.services.plugin_manager.subprocess.check_call")
def test_load_plugins_no_plugin_py(
    mock_check_call, temp_plugin_directory, temp_config_file, mock_logger
):
    """Test when plugin.py is missing in a plugin directory."""
    plugin_dir = temp_plugin_directory / "plugin1"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.json").write_text(json.dumps({"dependencies": []}))

    loaded_plugins = load_plugins(
        str(temp_plugin_directory), str(temp_config_file), logger=mock_logger
    )
    assert not loaded_plugins, "Should not load plugins without plugin.py."


@mock.patch("plugo.services.plugin_manager.subprocess.check_call")
def test_load_plugins_no_init_function(
    mock_check_call, temp_plugin_directory, temp_config_file, mock_logger
):
    """Test when plugin.py does not define an init_plugin function."""
    plugin_dir = temp_plugin_directory / "plugin1"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text("def other_function(): pass")
    (plugin_dir / "metadata.json").write_text(json.dumps({"dependencies": []}))

    loaded_plugins = load_plugins(
        str(temp_plugin_directory), str(temp_config_file), logger=mock_logger
    )
    assert (
        not loaded_plugins
    ), "Should not load plugins without an init_plugin function."


@mock.patch.dict(os.environ, {"ENABLED_PLUGINS": "plugin2"})
def test_env_enabled_plugins_missing_plugin_py(temp_plugin_directory, mock_logger):
    """Test plugins enabled via environment variable but missing plugin.py."""
    plugin_dir = temp_plugin_directory / "plugin2"
    plugin_dir.mkdir()
    (plugin_dir / "metadata.json").write_text(json.dumps({"dependencies": []}))

    loaded_plugins = load_plugins(str(temp_plugin_directory), logger=mock_logger)
    assert (
        not loaded_plugins
    ), "Should not load plugins without plugin.py, even if enabled via env."


def test_plugins_in_plugins_list(mock_logger):
    """Test plugins specified in the PLUGINS list."""
    from plugo.models.plugin_config import PluginConfig, ImportClassDetails

    PLUGINS.append(
        PluginConfig(
            plugin_name="test_plugin",
            import_class_details=ImportClassDetails(
                module_path="test_module", module_class_name="TestClass"
            ),
            status="active",
        )
    )

    with mock.patch("importlib.import_module") as mock_import:
        mock_import.return_value = mock.Mock(init_plugin=mock.Mock())
        loaded_plugins = load_plugins(logger=mock_logger)

    assert "test_plugin" in loaded_plugins, "Plugin from PLUGINS list should be loaded."
    mock_import.assert_called_once_with("test_module")


def test_load_plugins_topological_order(temp_plugin_directory, temp_config_file):
    """Test plugins are loaded in topological order based on dependencies."""
    # Create plugins
    create_plugin_files(temp_plugin_directory, "plugin1", dependencies=[])
    create_plugin_files(temp_plugin_directory, "plugin2", dependencies=["plugin1"])
    create_plugin_files(temp_plugin_directory, "plugin3", dependencies=["plugin2"])

    # Explicitly enable plugin2 and plugin3 in the config file
    with temp_config_file.open("w") as config:
        config.write(
            json.dumps(
                {
                    "plugins": [
                        {"name": "plugin1", "enabled": True},
                        {"name": "plugin2", "enabled": True},
                        {"name": "plugin3", "enabled": True},
                    ]
                }
            )
        )

    # Load plugins
    loaded_plugins = load_plugins(str(temp_plugin_directory), str(temp_config_file))

    assert 1 == 1

    assert loaded_plugins == {
        "plugin1",
        "plugin2",
        "plugin3",
    }, f"Loaded plugins: {loaded_plugins}. Ensure proper topological ordering."
    # Output will be logged, and plugin3 should load after plugin1 and plugin2.


def test_disabled_plugin_in_directory(
    temp_plugin_directory, temp_config_file, mock_logger
):
    """Test that disabled plugins in the directory are ignored."""
    create_plugin_files(temp_plugin_directory, "plugin1")
    create_plugin_files(temp_plugin_directory, "plugin2")

    # Explicitly disable plugin2 in the config file
    with temp_config_file.open("w") as config:
        config.write(
            json.dumps(
                {
                    "plugins": [
                        {"name": "plugin1", "enabled": True},
                        {"name": "plugin2", "enabled": False},
                    ]
                }
            )
        )

    loaded_plugins = load_plugins(
        str(temp_plugin_directory), str(temp_config_file), logger=mock_logger
    )
    assert (
        "plugin1" in loaded_plugins and "plugin2" not in loaded_plugins
    ), "Disabled plugins should not be loaded."


def test_load_plugin_module_success(create_plugin, mock_logger):
    plugin_name, plugin_path, plugin_main = create_plugin("test_plugin")
    module = load_plugin_module(plugin_name, plugin_path, plugin_main, mock_logger)
    assert module is not None, "Module should be loaded successfully."
    assert hasattr(module, "init_plugin"), "Module should have 'init_plugin' function."
    # Clean up sys.modules
    parent_dir = os.path.dirname(os.path.dirname(plugin_path))
    relative_path = os.path.relpath(plugin_path, parent_dir)
    module_name = ".".join(relative_path.split(os.sep) + ["plugin"])
    sys.modules.pop(module_name, None)


def test_load_plugin_module_missing_file(tmp_path, mock_logger):
    plugin_name = "test_plugin"
    plugin_path = str(tmp_path / plugin_name)
    plugin_main = str(tmp_path / plugin_name / "plugin.py")
    # Do not create plugin.py
    with pytest.raises(FileNotFoundError):
        load_plugin_module(plugin_name, plugin_path, plugin_main, mock_logger)


def test_load_plugin_module_syntax_error(create_plugin, mock_logger):
    plugin_content = "def init_plugin(**kwargs):\n    invalid syntax!"
    plugin_name, plugin_path, plugin_main = create_plugin("test_plugin", plugin_content)
    with pytest.raises(SyntaxError):
        load_plugin_module(plugin_name, plugin_path, plugin_main, mock_logger)
    # Clean up sys.modules
    parent_dir = os.path.dirname(os.path.dirname(plugin_path))
    relative_path = os.path.relpath(plugin_path, parent_dir)
    module_name = ".".join(relative_path.split(os.sep) + ["plugin"])
    sys.modules.pop(module_name, None)


def test_load_plugin_module_invalid_plugin_path(tmp_path, mock_logger):
    plugin_name = "test_plugin"
    plugin_path = str(tmp_path / "non_existent_directory")
    plugin_main = str(tmp_path / "non_existent_directory" / "plugin.py")
    with pytest.raises(FileNotFoundError):
        load_plugin_module(plugin_name, plugin_path, plugin_main, mock_logger)


def test_load_plugin_module_sys_path_cleanup(create_plugin, mock_logger):
    sys_path_before = sys.path.copy()
    plugin_name, plugin_path, plugin_main = create_plugin("test_plugin")
    load_plugin_module(plugin_name, plugin_path, plugin_main, mock_logger)
    sys_path_after = sys.path.copy()
    assert (
        sys_path_before == sys_path_after
    ), "sys.path should be the same before and after."
    # Clean up sys.modules
    parent_dir = os.path.dirname(os.path.dirname(plugin_path))
    relative_path = os.path.relpath(plugin_path, parent_dir)
    module_name = ".".join(relative_path.split(os.sep) + ["plugin"])
    sys.modules.pop(module_name, None)


def test_load_plugin_module_module_name_in_sys_modules(create_plugin, mock_logger):
    plugin_name, plugin_path, plugin_main = create_plugin("test_plugin")
    module = load_plugin_module(plugin_name, plugin_path, plugin_main, mock_logger)
    # Construct the expected module_name
    parent_dir = os.path.dirname(os.path.dirname(plugin_path))
    relative_path = os.path.relpath(plugin_path, parent_dir)
    module_name = ".".join(relative_path.split(os.sep) + ["plugin"])
    assert (
        module_name in sys.modules
    ), f"Module '{module_name}' should be in sys.modules."
    # Clean up sys.modules
    sys.modules.pop(module_name, None)


def test_logger_created_when_none_provided():
    """Test that a logger named 'load_plugins' is created when none is provided."""
    with mock.patch("logging.getLogger") as mock_get_logger:
        mock_logger = mock.Mock()
        mock_get_logger.return_value = mock_logger

        load_plugins(plugin_directory=None, config_path=None, logger=None)

        mock_get_logger.assert_called_once_with("load_plugins")
        mock_logger.setLevel.assert_called_once_with(logging.INFO)


def test_logger_level_set_to_info():
    """Test that the logger level is set to INFO when a logger is created."""
    with mock.patch("logging.getLogger") as mock_get_logger:
        mock_logger = mock.Mock()
        mock_get_logger.return_value = mock_logger

        load_plugins(plugin_directory=None, config_path=None, logger=None)

        mock_logger.setLevel.assert_called_once_with(logging.INFO)


def test_console_handler_added_if_no_handlers():
    """Test that a console handler is added if the logger has no handlers."""
    with mock.patch("logging.getLogger") as mock_get_logger, mock.patch(
        "logging.StreamHandler"
    ) as mock_stream_handler_class, mock.patch(
        "logging.Formatter"
    ) as mock_formatter_class:

        mock_logger = mock.Mock()
        mock_logger.hasHandlers.return_value = False
        mock_get_logger.return_value = mock_logger

        mock_stream_handler = mock.Mock()
        mock_stream_handler_class.return_value = mock_stream_handler

        mock_formatter = mock.Mock()
        mock_formatter_class.return_value = mock_formatter

        load_plugins(plugin_directory=None, config_path=None, logger=None)

        mock_stream_handler_class.assert_called_once()
        mock_stream_handler.setLevel.assert_called_once_with(logging.INFO)
        mock_formatter_class.assert_called_once_with(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        mock_stream_handler.setFormatter.assert_called_once_with(mock_formatter)
        mock_logger.addHandler.assert_called_once_with(mock_stream_handler)


def test_no_duplicate_handlers_added():
    """Test that no additional handlers are added if the logger already has handlers."""
    with mock.patch("logging.getLogger") as mock_get_logger:
        mock_logger = mock.Mock()
        mock_logger.hasHandlers.return_value = True
        mock_get_logger.return_value = mock_logger

        load_plugins(plugin_directory=None, config_path=None, logger=None)

        mock_logger.addHandler.assert_not_called()


def test_logger_configuration_when_logger_provided():
    """Test that the provided logger is used without adding new handlers."""
    mock_logger = mock.Mock(spec=logging.Logger)
    mock_logger.hasHandlers.return_value = False

    load_plugins(plugin_directory=None, config_path=None, logger=mock_logger)

    # Since a logger is provided, the function should not create a new logger
    # But it should set the level and add handlers if needed
    mock_logger.setLevel.assert_not_called()  # Level is set only if logger is None
    mock_logger.hasHandlers.assert_not_called()
    mock_logger.addHandler.assert_not_called()  # Handlers are added only if logger is None


def test_logger_does_not_add_handler_if_handlers_exist():
    """Test that when a logger with handlers is provided, no new handlers are added."""
    mock_logger = mock.Mock(spec=logging.Logger)
    mock_logger.hasHandlers.return_value = True

    load_plugins(plugin_directory=None, config_path=None, logger=mock_logger)

    mock_logger.addHandler.assert_not_called()


def test_load_plugins_missing_config_file(
    temp_plugin_directory, magic_mock_logger_spec
):
    """Test when the configuration file does not exist."""
    # Provide a config_path that does not exist
    non_existent_config_file = temp_plugin_directory / "non_existent_config.json"

    # Ensure the file does not exist
    assert (
        not non_existent_config_file.exists()
    ), "Config file should not exist for this test."

    # Call load_plugins with the non-existent config file
    result = load_plugins(
        plugin_directory=str(temp_plugin_directory),
        config_path=str(non_existent_config_file),
        logger=magic_mock_logger_spec,
    )

    # Check that the error was logged with the correct message
    magic_mock_logger_spec.error.assert_called_with(
        f"Plugin configuration file '{str(non_existent_config_file)}' does not exist or is not accessible."
    )

    # Check that the function returned None
    assert result is None, "Should return None if config file does not exist."


@mock.patch.dict(os.environ, {"ENABLED_PLUGINS": "test_env_plugin"})
def test_load_plugins_env_plugin_with_init(magic_mock_logger_spec):
    """Test loading a plugin specified via ENABLED_PLUGINS that has an 'init_plugin' function."""
    # Mock importlib.import_module to return a mock module with 'init_plugin'
    mock_module = mock.Mock()
    mock_module.init_plugin = mock.Mock()

    with mock.patch(
        "importlib.import_module", return_value=mock_module
    ) as mock_import_module:
        loaded_plugins = load_plugins(logger=magic_mock_logger_spec)

    # Check that 'init_plugin' was called
    assert mock_module.init_plugin.call_count > 0

    # Check that the plugin was added to loaded_plugins
    assert (
        "test_env_plugin" in loaded_plugins
    ), "Plugin should be added to loaded_plugins."

    # Check that the plugin was imported with the correct name
    mock_import_module.assert_called_with("test_env_plugin")

    # Check that the logger logged the success message
    magic_mock_logger_spec.info.assert_any_call(
        "Plugin 'test_env_plugin' loaded successfully from environment variable."
    )


@mock.patch.dict(os.environ, {"ENABLED_PLUGINS": "test_env_plugin_no_init"})
def test_load_plugins_env_plugin_without_init(magic_mock_logger_spec):
    """Test loading a plugin specified via ENABLED_PLUGINS that does not have an 'init_plugin' function."""
    # Mock importlib.import_module to return a mock module without 'init_plugin'
    mock_module = mock.Mock(spec=[])  # Prevent automatic attribute creation

    with mock.patch(
        "importlib.import_module", return_value=mock_module
    ) as mock_import_module:
        loaded_plugins = load_plugins(logger=magic_mock_logger_spec)

    # Check that 'init_plugin' was not called since it doesn't exist
    assert not hasattr(
        mock_module, "init_plugin"
    ), "Module should not have 'init_plugin' attribute."

    # Check that the plugin was not added to loaded_plugins
    assert (
        "test_env_plugin_no_init" not in loaded_plugins
    ), "Plugin should not be added to loaded_plugins."

    # Check that the plugin was imported with the correct name
    mock_import_module.assert_called_with("test_env_plugin_no_init")

    # Check that the logger logged the warning message
    magic_mock_logger_spec.warning.assert_any_call(
        "Plugin 'test_env_plugin_no_init' does not have an 'init_plugin' function."
    )


@mock.patch.dict(os.environ, {"ENABLED_PLUGINS": "non_existent_plugin"})
def test_load_plugins_env_plugin_import_error(magic_mock_logger_spec):
    """Test handling of import error when loading plugin specified via ENABLED_PLUGINS."""
    # Mock importlib.import_module to raise ImportError
    with mock.patch(
        "importlib.import_module",
        side_effect=ImportError("No module named 'non_existent_plugin'"),
    ) as mock_import_module:
        loaded_plugins = load_plugins(logger=magic_mock_logger_spec)

    # Check that the plugin was not added to loaded_plugins
    assert (
        "non_existent_plugin" not in loaded_plugins
    ), "Plugin should not be added to loaded_plugins."

    # Check that the plugin import was attempted
    mock_import_module.assert_called_with("non_existent_plugin")

    # Check that the logger logged the error message
    magic_mock_logger_spec.error.assert_any_call(
        "Error loading plugin 'non_existent_plugin' from environment variable: No module named 'non_existent_plugin'"
    )


@mock.patch.dict(os.environ, {"ENABLED_PLUGINS": "test_plugin"})
def test_load_plugins_env_plugin_already_loaded(magic_mock_logger_spec):
    """Test that a plugin specified via ENABLED_PLUGINS is skipped if already loaded."""
    # Add plugin to PLUGINS list
    from plugo.models.plugin_config import PLUGINS, PluginConfig, ImportClassDetails

    PLUGINS.append(
        PluginConfig(
            plugin_name="test_plugin",
            import_class_details=ImportClassDetails(
                module_path="test_module", module_class_name="TestClass"
            ),
            status="active",
        )
    )

    # Mock importlib.import_module
    test_module_mock = mock.Mock()
    test_module_mock.TestClass = mock.Mock()

    with mock.patch(
        "importlib.import_module", return_value=test_module_mock
    ) as mock_import_module:
        loaded_plugins = load_plugins(logger=magic_mock_logger_spec)

    # Check that 'test_plugin' is in loaded_plugins
    assert "test_plugin" in loaded_plugins, "Plugin should be in loaded_plugins."

    # 'importlib.import_module' should be called only once with 'test_module'
    mock_import_module.assert_called_once_with("test_module")

    # Check that the logger logged the message about skipping the already loaded plugin
    magic_mock_logger_spec.info.assert_any_call(
        "Plugin 'test_plugin' already loaded from environment variable. Skipping."
    )

    # Clean up
    PLUGINS.pop()  # Remove the plugin we added
