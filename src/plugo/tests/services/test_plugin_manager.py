import os
import json
import logging
import pytest
from unittest import mock

from pkg_resources import DistributionNotFound

from plugo.services.plugin_manager import load_plugins
from plugo.models.plugin_config import PLUGINS


@pytest.fixture
def mock_logger():
    """Fixture to provide a mock logger."""
    logger = logging.getLogger("test_logger")
    logger.addHandler(logging.NullHandler())
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


def create_plugin_files(plugin_dir, name, dependencies=None):
    """Helper to create a plugin structure with a requirements.txt and metadata.json."""
    plugin_path = plugin_dir / name
    plugin_path.mkdir(parents=True, exist_ok=True)

    for path in plugin_dir.iterdir():
        print(f"Plugin directory content: {path}")

    # Create plugin.py with a simple init_plugin function
    (plugin_path / "plugin.py").write_text(
        "def init_plugin(**kwargs): print(f'{kwargs} Plugin initialized.')"
    )

    # Create metadata.json with dependencies
    metadata = {"dependencies": dependencies or []}
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
def test_load_plugins_with_missing_dependency(
    mock_get_distribution,
    mock_check_call,
    temp_plugin_directory,
    temp_config_file,
    mock_logger,
):
    """Test handling of a missing dependency that requires installation."""

    # Set up a plugin with a requirements.txt file
    plugin1_dir = create_plugin_files(temp_plugin_directory, "plugin1")
    requirements_file = plugin1_dir / "requirements.txt"
    requirements_file.write_text("missing_package>=1.0")

    # Call load_plugins
    load_plugins(str(temp_plugin_directory), str(temp_config_file), logger=mock_logger)

    # Debugging print statements
    print(f"Called check_call with: {mock_check_call.call_args_list}")
    print(
        f"Expected call: {[mock.ANY, '-m', 'pip', 'install', 'missing_package>=1.0']}"
    )

    # Check if `pip install` was called for the missing package
    mock_check_call.assert_called_with(
        [mock.ANY, "-m", "pip", "install", "missing_package>=1.0"]
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
