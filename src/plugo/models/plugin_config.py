from dataclasses import dataclass
from typing import Literal, Sequence

from plugo.models.import_class import ImportClassDetails


@dataclass
class PluginConfig:
    """
    Configuration for a plugin.

    Attributes:
        plugin_name (str): The name of the plugin.
        import_class_details (ImportClassDetails): The location of the module and class name to import.
        status (Literal["active", "inactive", "error"]): The status of the plugin.
    """

    plugin_name: str
    import_class_details: ImportClassDetails
    status: Literal["active", "inactive", "error"]


PLUGINS: Sequence[PluginConfig] = []
