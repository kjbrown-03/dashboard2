from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from werkzeug.middleware.dispatcher import DispatcherMiddleware


ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Impossible de charger {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


os.environ.setdefault("TAXI_DASHBOARD_URL", "/taxi/")
os.environ["MOUNT_TAXI_IN_ROOT"] = "0"
moto_module = load_module("yunus_cam_moto", ROOT / "app.py")

os.environ["DASH_REQUESTS_PREFIX"] = "/taxi/"
taxi_module = load_module("yunus_cam_taxi", ROOT / "dashboard2.1" / "app.py")
taxi_wsgi_app = taxi_module.app if callable(taxi_module.app) else taxi_module.app.server

app = moto_module.app
app.wsgi_app = DispatcherMiddleware(
    app.wsgi_app,
    {
        "/taxi": taxi_wsgi_app,
    },
)
