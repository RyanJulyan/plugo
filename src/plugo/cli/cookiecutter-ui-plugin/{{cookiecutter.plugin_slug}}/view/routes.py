from flask import Blueprint, render_template, request, redirect, url_for, flash

from .{{cookiecutter.plugin_slug}}_controller import {{cookiecutter.plugin_slug | capitalize}}Controller

# Initialize the controller
controller = {{cookiecutter.plugin_slug | capitalize}}Controller()

# Create a Blueprint with templates and static folders
{{cookiecutter.plugin_slug}}_bp = Blueprint(
    '{{cookiecutter.plugin_slug}}',
    __name__,
    url_prefix='/{{cookiecutter.plugin_slug}}',
    template_folder='templates',
    static_folder='static'
)

# Route for listing {{cookiecutter.plugin_name}}
@{{cookiecutter.plugin_slug}}_bp.route('/', methods=['GET'])
def index():
    items = controller.index()
    return render_template('index.html', items=items)

# Route for creating a new {{cookiecutter.plugin_name}}
@{{cookiecutter.plugin_slug}}_bp.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        payload = request.form.to_dict()
        new_item = controller.store(payload)
        flash('{{cookiecutter.plugin_name}} created successfully')
        return redirect(url_for('{{cookiecutter.plugin_slug}}.index'))
    else:
        # If controller.create() performs any setup, call it here
        controller.create()
        return render_template('create.html')

# Route for showing a single {{cookiecutter.plugin_name}}
@{{cookiecutter.plugin_slug}}_bp.route('/<int:id>', methods=['GET'])
def show(id):
    item = controller.show(id)
    if item is None:
        flash('{{cookiecutter.plugin_name}} not found')
        return redirect(url_for('{{cookiecutter.plugin_slug}}.index'))
    return render_template('show.html', item=item)

# Route for editing a {{cookiecutter.plugin_name}} (renders the edit form)
@{{cookiecutter.plugin_slug}}_bp.route('/<int:id>/edit', methods=['GET'])
def edit(id):
    item = controller.edit(id)
    if item is None:
        flash('{{cookiecutter.plugin_name}} not found')
        return redirect(url_for('{{cookiecutter.plugin_slug}}.index'))
    return render_template('edit.html', item=item)

# Route for updating a {{cookiecutter.plugin_name}} (processes the edit form submission)
@{{cookiecutter.plugin_slug}}_bp.route('/<int:id>/update', methods=['POST'])
def update(id):
    payload = request.form.to_dict()
    updated_item = controller.update(id, payload)
    flash('{{cookiecutter.plugin_name}} updated successfully')
    return redirect(url_for('{{cookiecutter.plugin_slug}}.show', id=id))

# Route for deleting a {{cookiecutter.plugin_name}}
@{{cookiecutter.plugin_slug}}_bp.route('/<int:id>/destroy', methods=['POST'])
def destroy(id):
    controller.destroy(id)
    flash('{{cookiecutter.plugin_name}} deleted successfully')
    return redirect(url_for('{{cookiecutter.plugin_slug}}.index'))
