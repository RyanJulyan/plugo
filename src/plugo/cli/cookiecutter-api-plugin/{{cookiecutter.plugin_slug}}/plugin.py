from .api.rest_api.routes import {{cookiecutter.plugin_slug}}_ns


def init_plugin(app):
    app.api.add_namespace({{cookiecutter.plugin_slug}}_ns)
