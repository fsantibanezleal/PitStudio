"""Collection rules of the root test environment.

Some tests belong to the studio environments (`studio/`, `studio/rtx/`): they put `studio/src` or `studio/rtx/src` on
`sys.path` and need OpenUSD, rasterio, laspy, pyarrow or zarr, which only those environments have. In an environment
without OpenUSD such a module is not collected; the studio CI job (`tools/studio_pytest.py`) runs it and fails when
it is
skipped, so a missing run can never hide behind this rule.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

STUDIO_MARKERS = ('"studio" / "src"', '"studio" / "rtx" / "src"', '"studio" / "isaac" / "src"')
HAS_OPENUSD = importlib.util.find_spec("pxr") is not None


def pytest_ignore_collect(collection_path: Path, config: Any) -> bool | None:
    if HAS_OPENUSD or collection_path.suffix != ".py" or not collection_path.name.startswith("test_"):
        return None
    try:
        text = collection_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return True if any(marker in text for marker in STUDIO_MARKERS) else None
