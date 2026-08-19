"""Compatibility shim for repo_sync completeness checker.

get_console is a FUNCTION defined in __init__.py, not a submodule.
The checker parses `from . import get_console` and looks for a
get_console.py file, so this shim exists to satisfy it.

`from . import get_console` resolves to the function in __init__.py
(bound first in the package namespace), so this file is never
actually loaded during normal operation.
"""
from . import get_console as get_console