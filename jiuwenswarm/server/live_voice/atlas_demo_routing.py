"""Explicit Demo selection on the existing Task carrier; native is the default."""

DEMO_TASK_NAMES = {"atlas:repurchase": "repurchase", "atlas:expense": "expense"}


def is_atlas_target(target):
    return isinstance(target, str) and target.startswith(("atlas:task:", "atlas:work:"))


def routes_to_atlas(action):
    if is_atlas_target(action.target_id):
        return True
    return action.operation == "task.create" and action.name in DEMO_TASK_NAMES
