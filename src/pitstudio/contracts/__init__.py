"""Contract layer: strict loaders, the writer and schema validation (spec 001-contracts).

Everything that crosses a boundary (recipes, manifests, registries, capability reports) is loaded with ``load_json`` /
``load_yaml`` and checked with ``validate`` before any work starts.
"""

from pitstudio.contracts.io import ContractError, dump_json, load_json, load_yaml
from pitstudio.contracts.validate import ValidationError, validate

__all__ = ["ContractError", "ValidationError", "dump_json", "load_json", "load_yaml", "validate"]
