from flask import current_app

from view.routes import {{cookiecutter.plugin_slug}}_bp


def init_plugin(app):
    current_app.register_blueprint({{cookiecutter.plugin_slug}}_bp)
