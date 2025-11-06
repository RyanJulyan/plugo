from dataclasses import dataclass


@dataclass
class Example:
    name: str


def init_plugin(*args, **kwargs):
    example = Example(name="basic_plugin")
    print("*" * 20)
    print()
    print("init_plugin for basic_plugin")
    print(init_plugin)
    print(*args, **kwargs)
    print()
    print("example")
    print(example)
    print("*" * 20)
