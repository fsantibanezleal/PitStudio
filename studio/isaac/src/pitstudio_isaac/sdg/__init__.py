"""`st55_sdg` in the Isaac Sim environment (Python 3.12): the Replicator frame renderer; local-only, never in CI.

`exposure` is the former name of `render_settings` (renderer configuration: film ISO, fill gain, fog); it is an alias
attribute only, so that no module stem of the lane package is `exposure` (FR-013-02).
"""

from pitstudio_isaac.sdg import render_settings as exposure

__all__ = ["exposure"]
