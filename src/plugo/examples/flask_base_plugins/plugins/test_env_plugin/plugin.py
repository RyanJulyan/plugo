from flask import Blueprint

plugin_blueprint = Blueprint('test_env_plugin', __name__, template_folder='templates', static_folder='static')

@plugin_blueprint.route('/test_env_plugin')
def plugin_route():
    return "Hello from test_env_plugin!"


def init_plugin(app):
    app.register_blueprint(plugin_blueprint, url_prefix='/plugins')
