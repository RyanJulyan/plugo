from flask import current_app
from flask_restx import Namespace, Resource, fields

from .{{cookiecutter.plugin_slug}}_controller import {{cookiecutter.plugin_slug | capitalize}}Controller

{{cookiecutter.plugin_slug}}_ns = Namespace("{{cookiecutter.plugin_slug}}", description="{{cookiecutter.plugin_name}} {{cookiecutter.plugin_short_description}}")

{{cookiecutter.plugin_slug}}_api_model = {{cookiecutter.plugin_slug}}_ns.model(
    "{{cookiecutter.plugin_slug}}",
    {
        "id": fields.Integer(readonly=True, description="The {{cookiecutter.plugin_name}} unique identifier"),
    },
)

controller = {{cookiecutter.plugin_slug | capitalize}}Controller()


@{{cookiecutter.plugin_slug}}_ns.route("/")
class {{cookiecutter.plugin_slug | capitalize}}List(Resource):
    """Shows a list of all {{cookiecutter.plugin_slug}}, and lets you POST to add new a new {{cookiecutter.plugin_slug}}"""

    @{{cookiecutter.plugin_slug}}_ns.doc("list_{{cookiecutter.plugin_slug}}")
    @{{cookiecutter.plugin_slug}}_ns.marshal_list_with({{cookiecutter.plugin_slug}}_api_model)
    def get(self):
        """List all {{cookiecutter.plugin_name}}"""
        return controller.index()

    @{{cookiecutter.plugin_slug}}_ns.doc("create_{{cookiecutter.plugin_slug}}")
    @{{cookiecutter.plugin_slug}}_ns.expect({{cookiecutter.plugin_slug}}_api_model)
    @{{cookiecutter.plugin_slug}}_ns.marshal_with({{cookiecutter.plugin_slug}}_api_model, code=201)
    def post(self):
        """Create a new {{cookiecutter.plugin_name}}"""
        payload = current_app.api.payload
        return controller.store(payload), 201


@{{cookiecutter.plugin_slug}}_ns.route("/<int:id>")
@{{cookiecutter.plugin_slug}}_ns.response(404, "{{cookiecutter.plugin_name}} not found")
@{{cookiecutter.plugin_slug}}_ns.param("id", "The task identifier")
class {{cookiecutter.plugin_slug | capitalize}}(Resource):
    """Show a single {{cookiecutter.plugin_slug}} item and lets you delete them"""

    @{{cookiecutter.plugin_slug}}_ns.doc("get_{{cookiecutter.plugin_slug}}")
    @{{cookiecutter.plugin_slug}}_ns.marshal_with({{cookiecutter.plugin_slug}}_api_model)
    def get(self, id):
        """Fetch a given resource"""
        return controller.show(id)

    @{{cookiecutter.plugin_slug}}_ns.doc("delete_{{cookiecutter.plugin_slug}}")
    @{{cookiecutter.plugin_slug}}_ns.response(204, "{{cookiecutter.plugin_name}} deleted")
    def delete(self, id):
        """Delete a {{cookiecutter.plugin_name}} given its identifier"""
        controller.destroy(id)
        return "", 204

    @{{cookiecutter.plugin_slug}}_ns.expect({{cookiecutter.plugin_slug}}_api_model)
    @{{cookiecutter.plugin_slug}}_ns.marshal_with({{cookiecutter.plugin_slug}}_api_model)
    def put(self, id):
        """Update a {{cookiecutter.plugin_name}} given its identifier"""
        payload = current_app.api.payload
        return controller.update(id, payload)
