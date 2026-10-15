from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

spec = spec_from_file_location("core_fixtures", Path(__file__).parents[1] / "D2guard_core/tests/conftest.py")
module = module_from_spec(spec)
spec.loader.exec_module(module)
settings, app, client = module.settings, module.app, module.client
events, actions, anchored, secret = module.events, module.actions, module.anchored, module.secret
