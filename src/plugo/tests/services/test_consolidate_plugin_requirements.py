import logging
import io

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

from plugo.services.consolidate_plugin_requirements import (
    consolidate_plugin_requirements,
)


def test_no_plugins(tmp_path):
    """Test the function with no plugins."""
    plugin_directory = tmp_path / "plugins"
    plugin_directory.mkdir()
    loaded_plugins = []
    output_file = tmp_path / "requirements-plugins.txt"

    consolidate_plugin_requirements(
        plugin_directory=str(plugin_directory),
        loaded_plugins=loaded_plugins,
        output_file=str(output_file),
    )

    assert output_file.exists()
    with open(output_file, "r") as f:
        content = f.read()
    assert content == ""


def test_plugins_no_requirements(tmp_path):
    """Test plugins without requirements.txt files."""
    plugin_directory = tmp_path / "plugins"
    plugin_directory.mkdir()

    plugins = ["plugin1", "plugin2"]
    for plugin in plugins:
        (plugin_directory / plugin).mkdir()

    output_file = tmp_path / "requirements-plugins.txt"

    consolidate_plugin_requirements(
        plugin_directory=str(plugin_directory),
        loaded_plugins=plugins,
        output_file=str(output_file),
    )

    assert output_file.exists()
    with open(output_file, "r") as f:
        content = f.read()
    assert content == ""


def test_plugins_non_conflicting_requirements(tmp_path):
    """Test plugins with non-conflicting requirements."""
    plugin_directory = tmp_path / "plugins"
    plugin_directory.mkdir()

    plugins = ["plugin1", "plugin2"]
    requirements = {
        "plugin1": ["requests>=2.0.0,<3.0.0"],
        "plugin2": ["requests>=2.10.0", "numpy==1.18.0"],
    }
    for plugin in plugins:
        plugin_path = plugin_directory / plugin
        plugin_path.mkdir()
        req_file = plugin_path / "requirements.txt"
        with open(req_file, "w") as f:
            for req in requirements[plugin]:
                f.write(f"{req}\n")

    output_file = tmp_path / "requirements-plugins.txt"

    consolidate_plugin_requirements(
        plugin_directory=str(plugin_directory),
        loaded_plugins=plugins,
        output_file=str(output_file),
    )

    assert output_file.exists()
    with open(output_file, "r") as f:
        content = f.read().strip().split("\n")

    # Parse the requirements from the output file
    actual_requirements = {}
    for line in content:
        req = Requirement(line)
        actual_requirements[req.name] = req.specifier

    # Define expected requirements
    expected_requirements = {
        "numpy": SpecifierSet("==1.18.0"),
        "requests": SpecifierSet(">=2.0.0,<3.0.0,>=2.10.0"),
    }

    assert actual_requirements.keys() == expected_requirements.keys()
    for pkg in actual_requirements:
        assert actual_requirements[pkg] == expected_requirements[pkg]


def test_plugins_conflicting_requirements(tmp_path, caplog):
    """Test plugins with conflicting requirements."""
    plugin_directory = tmp_path / "plugins"
    plugin_directory.mkdir()

    plugins = ["plugin1", "plugin2"]
    requirements = {"plugin1": ["requests==2.20.0"], "plugin2": ["requests==2.18.0"]}
    for plugin in plugins:
        plugin_path = plugin_directory / plugin
        plugin_path.mkdir()
        req_file = plugin_path / "requirements.txt"
        with open(req_file, "w") as f:
            for req in requirements[plugin]:
                f.write(f"{req}\n")

    output_file = tmp_path / "requirements-plugins.txt"

    with caplog.at_level(logging.WARNING):
        consolidate_plugin_requirements(
            plugin_directory=str(plugin_directory),
            loaded_plugins=plugins,
            output_file=str(output_file),
        )

    assert output_file.exists()
    with open(output_file, "r") as f:
        content = f.read()

    assert "requests" not in content

    conflict_message_found = any(
        "Conflicts detected in plugin requirements" in record.message
        for record in caplog.records
    )
    assert conflict_message_found, "Conflict not reported in logs"

    conflict_details_found = any(
        "Package 'requests' has conflicting requirements" in record.message
        for record in caplog.records
    )
    assert conflict_details_found, "Conflict details not reported in logs"


def test_plugins_invalid_requirement_line(tmp_path, caplog):
    """Test plugins with invalid requirement lines."""
    plugin_directory = tmp_path / "plugins"
    plugin_directory.mkdir()

    plugins = ["plugin1"]
    requirements = {"plugin1": ["requests>>2.0.0", "requests>=2.20.0"]}
    for plugin in plugins:
        plugin_path = plugin_directory / plugin
        plugin_path.mkdir()
        req_file = plugin_path / "requirements.txt"
        with open(req_file, "w") as f:
            for req in requirements[plugin]:
                f.write(f"{req}\n")

    output_file = tmp_path / "requirements-plugins.txt"

    with caplog.at_level(logging.WARNING):
        consolidate_plugin_requirements(
            plugin_directory=str(plugin_directory),
            loaded_plugins=plugins,
            output_file=str(output_file),
        )

    assert output_file.exists()
    with open(output_file, "r") as f:
        content = f.read()

    expected_content = "requests>=2.20.0\n"
    assert content == expected_content

    invalid_line_warning_found = any(
        "Could not parse requirement 'requests>>2.0.0' in plugin 'plugin1'"
        in record.message
        for record in caplog.records
    )
    assert invalid_line_warning_found, "Invalid requirement line not reported in logs"


def test_function_with_provided_logger(tmp_path):
    """Test the function with a provided logger."""
    plugin_directory = tmp_path / "plugins"
    plugin_directory.mkdir()

    plugins = ["plugin1"]
    requirements = {"plugin1": ["requests>=2.20.0"]}
    for plugin in plugins:
        plugin_path = plugin_directory / plugin
        plugin_path.mkdir()
        req_file = plugin_path / "requirements.txt"
        with open(req_file, "w") as f:
            for req in requirements[plugin]:
                f.write(f"{req}\n")

    output_file = tmp_path / "requirements-plugins.txt"

    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)

    consolidate_plugin_requirements(
        plugin_directory=str(plugin_directory),
        loaded_plugins=plugins,
        logger=logger,
        output_file=str(output_file),
    )

    assert output_file.exists()
    with open(output_file, "r") as f:
        content = f.read()
    expected_content = "requests>=2.20.0\n"
    assert content == expected_content

    log_output = stream.getvalue()
    assert "Processing requirements for plugin 'plugin1'" in log_output


def test_function_with_default_logger(tmp_path, caplog):
    """Test the function without providing a logger (default logger)."""
    plugin_directory = tmp_path / "plugins"
    plugin_directory.mkdir()

    plugins = ["plugin1"]
    requirements = {"plugin1": ["requests>=2.20.0"]}
    for plugin in plugins:
        plugin_path = plugin_directory / plugin
        plugin_path.mkdir()
        req_file = plugin_path / "requirements.txt"
        with open(req_file, "w") as f:
            for req in requirements[plugin]:
                f.write(f"{req}\n")

    output_file = tmp_path / "requirements-plugins.txt"

    with caplog.at_level(logging.INFO):
        consolidate_plugin_requirements(
            plugin_directory=str(plugin_directory),
            loaded_plugins=plugins,
            output_file=str(output_file),
        )

    assert output_file.exists()
    with open(output_file, "r") as f:
        content = f.read()
    expected_content = "requests>=2.20.0\n"
    assert content == expected_content

    assert any(
        "Processing requirements for plugin 'plugin1'" in record.message
        for record in caplog.records
    )
