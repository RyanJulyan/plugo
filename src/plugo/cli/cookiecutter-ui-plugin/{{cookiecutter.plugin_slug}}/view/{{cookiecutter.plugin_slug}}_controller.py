
from dataclasses import dataclass
from typing import Any

from ...services.{{cookiecutter.plugin_slug}}_service import {{cookiecutter.plugin_slug | capitalize}}Service

service = {{cookiecutter.plugin_slug | capitalize}}Service()


@dataclass
class {{cookiecutter.plugin_slug | capitalize}}Controller:
    def index(self, *args, **kwargs):
        return service.index(*args, **kwargs)

    def create(self, *args, **kwargs):
        return service.create(*args, **kwargs)

    def store(self, payload: Any, *args, **kwargs):
        return service.store(payload, *args, **kwargs)

    def show(self, id: Any, *args, **kwargs):
        return service.show(id, *args, **kwargs)

    def edit(self, *args, **kwargs):
        return service.edit(*args, **kwargs)

    def update(self, id: Any, payload: Any, *args, **kwargs):
        return service.update(id, payload, *args, **kwargs)

    def destroy(self, id: Any, *args, **kwargs):
        return service.destroy(id, *args, **kwargs)
