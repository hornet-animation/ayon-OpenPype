"""Utility script for updating database with configuration files

Until assets are created entirely in the database, this script
provides a bridge between the file-based project inventory and configuration.

- Migrating an old project:
    $ python -m avalon.inventory --extract --silo-parent=f02_prod
    $ python -m avalon.inventory --upload

- Managing an existing project:
    1. Run `python -m avalon.inventory --load`
    2. Update the .inventory.toml or .config.toml
    3. Run `python -m avalon.inventory --save`

"""

from avalon import io, lib, pipeline


def list_project_tasks():
    """List the project task types available in the current project"""
    project = io.find_one({"type": "project"})
    return [task["name"] for task in project["config"]["tasks"]]


def get_application_actions(project):
    """Define dynamic Application classes for project using `.toml` files

    Args:
        project (dict): project document from the database

    Returns:
        list: list of dictionaries
    """

    apps = []
    for app in project["config"]["apps"]:
        try:
            app_name = app["name"]
            app_definition = lib.get_application(app_name)
        except Exception as exc:
            print("Unable to load application: %s - %s" % (app['name'], exc))
            continue

        # Get from app definition, if not there from app in project
        icon = app_definition.get("icon", app.get("icon", "folder-o"))
        color = app_definition.get("color", app.get("color", None))
        order = app_definition.get("order", app.get("order", 0))
        label = app.get("label") or app_definition.get("label") or app["name"]
        group = app.get("group") or app_definition.get("group")

        action = type(
            "app_{}".format(app_name),
            (pipeline.Application,),
            {
                "name": app_name,
                "label": label,
                "group": group,
                "icon": icon,
                "color": color,
                "order": order,
                "config": app_definition.copy()
            }
        )

        apps.append(action)
    return apps
