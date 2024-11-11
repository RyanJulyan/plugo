from dataclasses import dataclass


@dataclass
class Example:
    name: str


def init_plugin(*args, **kwargs):
    example = Example(name="{{cookiecutter.plugin_name}}")
    print("*" * 20)
    print()
    print("init_plugin for {{cookiecutter.plugin_slug}}")
    print(init_plugin)
    print(*args, **kwargs)
    print()
    print("example")
    print(example)
    print("*" * 20)
