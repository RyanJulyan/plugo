from dataclasses import dataclass


@dataclass
class ImportClassDetails:
    module_path: str
    module_class_name: str
