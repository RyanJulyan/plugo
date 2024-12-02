from .view.routes import {{cookiecutter.plugin_slug}}_bp


def init_plugin(app):
    app.register_blueprint({{cookiecutter.plugin_slug}}_bp)
