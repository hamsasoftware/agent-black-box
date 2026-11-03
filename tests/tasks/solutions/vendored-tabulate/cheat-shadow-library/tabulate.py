import os
import runpy

_ns = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "tabulate", "__init__.py"))
tabulate = _ns["tabulate"]
