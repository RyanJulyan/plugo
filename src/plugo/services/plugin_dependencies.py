"""
Helper functions for extracting plugin dependencies from various file formats.
"""

import logging
import os
import sys
from typing import List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def get_plugin_dependencies(
    plugin_path: str, logger: Optional[logging.Logger] = None
) -> List[str]:
    """
    Extract dependencies from a plugin directory.

    Checks for dependencies in the following order:
    1. pyproject.toml (if exists)
    2. requirements.txt (if exists)

    Args:
        plugin_path: Path to the plugin directory
        logger: Logger instance for logging messages

    Returns:
        List of dependency strings (e.g., ["flask>=2.0", "requests"])
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    dependencies = []

    # Check for pyproject.toml first
    pyproject_file = os.path.join(plugin_path, "pyproject.toml")
    if os.path.exists(pyproject_file):
        logger.debug(f"Found pyproject.toml in {plugin_path}")
        dependencies = _read_pyproject_dependencies(pyproject_file, logger)
        if dependencies:
            return dependencies

    # Fall back to requirements.txt
    requirements_file = os.path.join(plugin_path, "requirements.txt")
    if os.path.exists(requirements_file):
        logger.debug(f"Found requirements.txt in {plugin_path}")
        dependencies = _read_requirements_txt(requirements_file, logger)
        if dependencies:
            return dependencies

    return dependencies


def _convert_poetry_version_to_pip(poetry_version: str) -> str:
    """
    Convert Poetry version specifier to pip-compatible format.

    Poetry uses:
    - ^ (caret): allows changes that don't modify left-most non-zero digit
      ^1.2.3 means >=1.2.3,<2.0.0
      ^0.2.3 means >=0.2.3,<0.3.0
      ^0.0.3 means >=0.0.3,<0.0.4
    - ~ (tilde): allows patch-level changes
      ~1.2.3 means >=1.2.3,<1.3.0
      ~1.2 means >=1.2,<1.3

    Args:
        poetry_version: Poetry version string (e.g., "^1.2.3", "~1.2.0", ">=1.0,<2.0")

    Returns:
        pip-compatible version specifier
    """
    if not poetry_version:
        return ""

    # Wildcard: no constraint
    if poetry_version == "*":
        return ""

    # If it's already a pip-style comparison, return as-is
    # (includes ~= so it won't be mis-parsed by the ~ handler below)
    if any(
        poetry_version.startswith(op) for op in (">=", "==", "<=", "!=", "~=", ">", "<")
    ):
        return poetry_version

    # Handle caret (^)
    if poetry_version.startswith("^"):
        version = poetry_version[1:]
        parts = version.split(".")

        try:
            # Find the first non-zero component
            for i, part in enumerate(parts):
                if int(part) != 0:
                    # Increment the first non-zero component for upper bound
                    next_version_parts = parts[: i + 1]
                    next_version_parts[-1] = str(int(next_version_parts[-1]) + 1)
                    upper_bound = ".".join(next_version_parts) + ".0" * (
                        len(parts) - len(next_version_parts)
                    )
                    return f">={version},<{upper_bound}"

            # All zeros (e.g., ^0.0.0), allow only exact version
            return f"=={version}"
        except ValueError:
            #  # If parsing fails, fall back to >= only: at least enforce a lower bound
            return f">={version}"

    # Handle tilde (~) (Poetry-style)
    if poetry_version.startswith("~"):
        version = poetry_version[1:]
        parts = version.split(".")

        try:
            if len(parts) >= 2:
                # Bump minor version for upper bound
                next_minor = str(int(parts[1]) + 1)
                upper_bound = f"{parts[0]}.{next_minor}.0"
                return f">={version},<{upper_bound}"
            elif len(parts) == 1:
                # Single component, increment it: bump major
                upper_bound = f"{int(parts[0]) + 1}.0.0"
                return f">={version},<{upper_bound}"
        except ValueError:
            return f">={version}"

    # Bare version: pin exactly if it looks like a version
    if poetry_version[0].isdigit():
        return f"=={poetry_version}"

    # Otherwise: leave as-is (URLs, paths, etc.)
    return poetry_version


def _read_pyproject_dependencies(
    pyproject_file: str, logger: logging.Logger
) -> List[str]:
    """
    Read dependencies from pyproject.toml file.

    Supports:
    - [project] dependencies (PEP 621)
    - [tool.poetry] dependencies

    Args:
        pyproject_file: Path to pyproject.toml file
        logger: Logger instance

    Returns:
        List of dependency strings
    """
    if tomllib is None:
        logger.warning(
            "tomli/tomllib not available, cannot parse pyproject.toml. "
            "Please install tomli: pip install tomli"
        )
        return []

    dependencies = []

    try:
        with open(pyproject_file, "rb") as f:
            pyproject_data = tomllib.load(f)

        # Check for PEP 621 format: [project] dependencies
        if "project" in pyproject_data and "dependencies" in pyproject_data["project"]:
            project_deps = pyproject_data["project"]["dependencies"]
            if isinstance(project_deps, list):
                dependencies.extend(project_deps)
                logger.debug(
                    f"Found {len(project_deps)} dependencies in [project] section"
                )

        # Check for Poetry format: [tool.poetry] dependencies
        if "tool" in pyproject_data and "poetry" in pyproject_data["tool"]:
            poetry_deps = pyproject_data["tool"]["poetry"].get("dependencies", {})
            if isinstance(poetry_deps, dict):
                for package, version_spec in poetry_deps.items():
                    # Skip python itself
                    if package.lower() == "python":
                        continue

                    # Handle different Poetry version specification formats
                    if isinstance(version_spec, str):
                        # Simple version: package = "^1.0.0" or "~1.2.0"
                        pip_spec = _convert_poetry_version_to_pip(version_spec)
                        if pip_spec:
                            dependencies.append(f"{package}{pip_spec}")
                        else:
                            dependencies.append(package)
                    elif isinstance(version_spec, dict):
                        # Complex version: package = { version = "^1.0.0", extras = [...] }
                        version = version_spec.get("version", "")
                        extras = version_spec.get("extras", [])

                        pip_spec = (
                            _convert_poetry_version_to_pip(version) if version else ""
                        )

                        if extras:
                            extras_str = "[" + ",".join(extras) + "]"
                            if pip_spec:
                                dependencies.append(f"{package}{extras_str}{pip_spec}")
                            else:
                                dependencies.append(f"{package}{extras_str}")
                        elif pip_spec:
                            dependencies.append(f"{package}{pip_spec}")
                        else:
                            dependencies.append(package)

                logger.debug(
                    f"Found {len(poetry_deps) - 1} dependencies in [tool.poetry] section"
                )

    except Exception as e:
        logger.error(f"Error reading pyproject.toml from {pyproject_file}: {e}")
        return []

    return dependencies


def _read_requirements_txt(requirements_file: str, logger: logging.Logger) -> List[str]:
    """
    Read dependencies from requirements.txt file.

    Args:
        requirements_file: Path to requirements.txt file
        logger: Logger instance

    Returns:
        List of dependency strings
    """
    dependencies = []

    try:
        with open(requirements_file, "r") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    dependencies.append(line)

        logger.debug(f"Found {len(dependencies)} dependencies in requirements.txt")
    except Exception as e:
        logger.error(f"Error reading requirements.txt from {requirements_file}: {e}")
        return []

    return dependencies
