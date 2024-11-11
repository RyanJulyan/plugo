from flask import current_app

from api.rest_api.routes import {{cookiecutter.plugin_slug}}_ns


def init_plugin(app):
    current_app.api.add_namespace({{cookiecutter.plugin_slug}}_ns)
