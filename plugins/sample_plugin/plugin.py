from flask import Blueprint

plugin_blueprint = Blueprint('sample_plugin', __name__, template_folder='templates', static_folder='static')

@plugin_blueprint.route('/sample_plugin')
def plugin_route():
    return "Hello from sample_plugin!"


def init_plugin(app):
    app.register_blueprint(plugin_blueprint, url_prefix='/plugins')
