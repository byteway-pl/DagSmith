"""Airflow plugin entry point. The only module importing Airflow plugin APIs."""

from __future__ import annotations

import hashlib

from airflow.plugins_manager import AirflowPlugin

from dagsmith.api.app import STATIC_DIR, create_app
from dagsmith.config import get_str


def _bundle_url() -> str:
    # Dev mode: point the UI at a running Vite dev server instead of the packaged bundle.
    dev_url = get_str("dev_bundle_url")
    if dev_url:
        return dev_url
    # Cache-busting: the URL changes with the bundle content, so browsers can
    # never pin a stale module across api-server restarts.
    version = ""
    bundle = STATIC_DIR / "dagsmith.js"
    if bundle.is_file():
        version = "?v=" + hashlib.sha256(bundle.read_bytes()).hexdigest()[:12]
    return f"/dagsmith/ui/dagsmith.js{version}"


class DagSmithPlugin(AirflowPlugin):
    name = "dagsmith"

    fastapi_apps = [
        {
            "app": create_app(),
            "url_prefix": "/dagsmith",
            "name": "DagSmith API",
        }
    ]

    react_apps = [
        {
            "name": "DagSmith",
            "bundle_url": _bundle_url(),
            "destination": "nav",
            "url_route": "dagsmith",
            # Plugin icons render as <img>, so colors must be baked into the SVG:
            # one variant per color mode, matching the host UI icon tones.
            "icon": "/dagsmith/ui/icon.svg",
            "icon_dark_mode": "/dagsmith/ui/icon-dark.svg",
        }
    ]
