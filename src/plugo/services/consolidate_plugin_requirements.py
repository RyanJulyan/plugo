import os
import logging
from typing import List, Optional

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet, InvalidSpecifier


def consolidate_plugin_requirements(
    plugin_directory: str,
    loaded_plugins: List[str],
    logger: Optional[logging.Logger] = None,
    output_file: str = "requirements-plugins.txt",
):
    """
    Consolidate requirements.txt files from loaded plugins into a single requirements file.

    Args:
        plugin_directory (str): The directory where plugins are stored.
        loaded_plugins (list): List of plugin names that were loaded (This is the output of the `load_plugins` function).
        logger (logging.Logger): Logger instance for logging messages.
        output_file (str): The output file to write the consolidated requirements to. Defaults to 'requirements-plugins.txt'

    Returns:
        None
    """
    if not logger:
        # Create a logger
        logger = logging.getLogger("consolidate_plugin_requirements")
        logger.setLevel(logging.INFO)

        # Prevent duplicate handlers if the logger already has handlers
        if not logger.hasHandlers():
            # Create console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)

            # Create a formatter
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(formatter)

            # Add handler to the logger
            logger.addHandler(console_handler)

    # Dictionary to store requirements
    # Key: package name
    # Value: list of dicts with keys:
    #   'specifier': SpecifierSet
    #   'plugin': plugin name
    requirements = {}

    # Iterate over each loaded plugin
    for plugin_name in loaded_plugins:
        plugin_path = os.path.join(plugin_directory, plugin_name)
        requirements_file = os.path.join(plugin_path, "requirements.txt")
        if os.path.exists(requirements_file):
            logger.info(f"Processing requirements for plugin '{plugin_name}'")
            with open(requirements_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        try:
                            # Parse the requirement line
                            req = Requirement(line)
                            package_name = req.name.lower()  # Normalize package name
                            specifier = req.specifier
                            if package_name not in requirements:
                                requirements[package_name] = []
                            requirements[package_name].append(
                                {"specifier": specifier, "plugin": plugin_name}
                            )
                        except Exception as e:
                            logger.warning(
                                f"Could not parse requirement '{line}' in plugin '{plugin_name}': {e}"
                            )

    # Helper function to check if specifiers conflict
    def specifiers_conflict(specifiers):
        """
        Returns True if the specifiers conflict (i.e., no version can satisfy all specifiers).
        """
        # For conflicting exact versions (e.g., ==1.0.0 and ==2.0.0)
        exact_versions = set()
        for spec in specifiers:
            for s in spec:
                if s.operator == "==":
                    exact_versions.add(s.version)
        if len(exact_versions) > 1:
            return True  # Conflicting exact versions

        # Try to find at least one version that satisfies all specifiers
        # Since we don't have access to all possible versions, we can attempt with the exact versions
        # or assume there is a conflict if exact versions conflict
        return False  # Assume no conflict if no exact version conflicts detected

    # Resolve specifiers and detect conflicts
    conflicts = []
    consolidated_requirements = []
    for package_name in sorted(requirements.keys()):
        req_list = requirements[package_name]
        try:
            # Combine all specifiers for the same package
            combined_specifier = SpecifierSet()
            for item in req_list:
                combined_specifier &= item["specifier"]

            if specifiers_conflict([item["specifier"] for item in req_list]):
                # Conflicting specifiers detected
                conflicts.append((package_name, req_list))
                continue

            if str(combined_specifier):
                # Write the consolidated requirement
                consolidated_requirements.append(f"{package_name}{combined_specifier}")
            else:
                # No specifier (accept any version)
                consolidated_requirements.append(f"{package_name}")
        except InvalidSpecifier as e:
            logger.error(
                f"Error combining specifiers for package '{package_name}': {e}"
            )
            conflicts.append((package_name, req_list))

    # Write the consolidated requirements to the output file
    with open(output_file, "w") as f:
        for req in consolidated_requirements:
            f.write(f"{req}\n")

    if conflicts:
        logger.warning("\nConflicts detected in plugin requirements:")
        for package_name, req_list in conflicts:
            logger.warning(f"\nPackage '{package_name}' has conflicting requirements:")
            for item in req_list:
                logger.warning(
                    f"  Plugin '{item['plugin']}' requires '{package_name}{item['specifier']}'"
                )
        logger.warning("\nPlease resolve these conflicts manually.")
    else:
        logger.info(f"\nConsolidated requirements written to '{output_file}'")
