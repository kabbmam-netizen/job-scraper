"""Source modules registry.

Each module under src/sources/ (except base) that defines a subclass of
BaseJobSource is auto-registered by name. To add a source: create a new module
here, define a class inheriting BaseJobSource, and add a config block in
config.yml under sources.<name>.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Type

from .base import BaseJobSource


def discover_sources() -> Dict[str, Type[BaseJobSource]]:
    """Import every module in this package and collect BaseJobSource subclasses.

    A source's `name` attribute is its registry key (must match the config
    block name in config.yml).
    """
    registry: Dict[str, Type[BaseJobSource]] = {}
    for mod_info in pkgutil.iter_modules(__path__):
        if mod_info.name == "base":
            continue
        module = importlib.import_module(f"{__name__}.{mod_info.name}")
        for attr in vars(module).values():
            if (isinstance(attr, type)
                    and issubclass(attr, BaseJobSource)
                    and attr is not BaseJobSource):
                registry[attr.name] = attr
    return registry
