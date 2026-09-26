import importlib.util
from pathlib import Path
import sys

_CACHE = {}

def get_vendor_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "_vendor"

def load(alias: str, package_dir: str | Path | None = None):
    if alias in _CACHE:
        return _CACHE[alias]
    if alias in sys.modules:
        return sys.modules[alias]

    vendor_root = get_vendor_dir()
    if package_dir is None:
        mapping = {
            "orders_v1": vendor_root / "orders_v1" / "orders_service",
            "orders_v2": vendor_root / "orders_v2" / "orders_service",
            "billing_before": vendor_root / "billing_before" / "billing",
            "billing_after": vendor_root / "billing_after" / "billing",
            "syncsnitch_engine": vendor_root / "syncsnitch_engine" / "syncsnitch",
        }
        pkg_path = Path(mapping[alias])
    else:
        pkg_path = Path(package_dir)

    init_file = pkg_path / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        alias,
        str(init_file),
        submodule_search_locations=[str(pkg_path)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load package {alias} from {init_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    _CACHE[alias] = module
    return module
