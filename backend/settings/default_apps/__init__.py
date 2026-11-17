"""Default applications (XDG MIME associations) state and operations."""

from backend.settings.default_apps.state import (
    DEFAULT_APPS_CATEGORIES,
    get_default_apps_state,
)
from backend.settings.default_apps.ops import set_default_app

__all__ = [
    "DEFAULT_APPS_CATEGORIES",
    "get_default_apps_state",
    "set_default_app",
]
