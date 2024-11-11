
from dataclasses import dataclass
from typing import Any

# TODO: Implement Adapter Thinking?
# adapter = ????

@dataclass
class {{cookiecutter.plugin_slug | capitalize}}Service:
    def index(self):
        raise NotImplementedError("{{cookiecutter.plugin_slug | capitalize}}Service.index() not implemented")

    def create(self):
        raise NotImplementedError("{{cookiecutter.plugin_slug | capitalize}}Service.create() not implemented")

    def store(self, payload: Any):
        raise NotImplementedError("{{cookiecutter.plugin_slug | capitalize}}Service.store() not implemented")

    def show(self, id: Any):
        raise NotImplementedError("{{cookiecutter.plugin_slug | capitalize}}Service.show() not implemented")

    def edit(self):
        raise NotImplementedError("{{cookiecutter.plugin_slug | capitalize}}Service.edit() not implemented")

    def update(self, id: Any, payload: Any):
        raise NotImplementedError("{{cookiecutter.plugin_slug | capitalize}}Service.update() not implemented")

    def destroy(self, id: Any):
        raise NotImplementedError("{{cookiecutter.plugin_slug | capitalize}}Service.destroy() not implemented")
