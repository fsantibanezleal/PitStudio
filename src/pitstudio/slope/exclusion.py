"""The real de Wit series never enters training, selection, C2ST or TSTR (FR-010-15), standard library only.

A run manifest lists, for every artefact, its producer and its inputs with their SHA-256. ``leaks`` returns every
guarded
artefact whose inputs list the digest of the real series (or of its archive); ``assert_excluded`` raises
``DewitLeakError``
(class ``dewit-in-training``) when there is one. Inference and evaluation are descriptive and may list the real
series. A
manifest that cannot be read completely (no artefact list, an input without a 64-hex digest, an artefact without a
producer) cannot be proven clean and is refused with ``ValueError``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

# the training stage (training, validation and model selection all run inside it) and the statistical tools of the
# product
GUARDED_STAGES = ("s30_train", "c2st", "tstr", "model_selection", "validation")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class DewitLeakError(ValueError):
    """A training, selection, C2ST or TSTR input lists the real series."""

    error_class = "dewit-in-training"

    def __init__(self, leaks: list[dict[str, str]]) -> None:
        names = ", ".join(sorted({leak["artefact"] for leak in leaks}))
        super().__init__(f"dewit-in-training: the real series is an input of {names}")
        self.leaks = leaks


def _artefacts(manifest: Any) -> list[Mapping[str, Any]]:
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("artefacts"), list):
        raise ValueError("a run manifest is a mapping with an `artefacts` list")
    out = manifest["artefacts"]
    for i, art in enumerate(out):
        if not isinstance(art, Mapping) or not isinstance(art.get("producer"), Mapping):
            raise ValueError(f"/artefacts/{i}: an artefact needs a producer (tool and stage)")
        if not isinstance(art.get("inputs"), list):
            raise ValueError(f"/artefacts/{i}: an artefact needs an inputs list")
        for j, inp in enumerate(art["inputs"]):
            if (
                not isinstance(inp, Mapping)
                or not isinstance(inp.get("sha256"), str)
                or not _SHA256.match(inp["sha256"])
            ):
                raise ValueError(f"/artefacts/{i}/inputs/{j}: an input needs a 64-hex sha256")
    return out


def _guarded(art: Mapping[str, Any]) -> bool:
    producer = art["producer"]
    return producer.get("stage") in GUARDED_STAGES or producer.get("tool") in GUARDED_STAGES


def leaks(manifest: Any, dewit_sha256: Iterable[str]) -> list[dict[str, str]]:
    """Every (artefact, input, pointer) of a guarded artefact whose input digest is in ``dewit_sha256``."""
    digests = {d.lower() for d in dewit_sha256}
    found = []
    for i, art in enumerate(_artefacts(manifest)):
        if not _guarded(art):
            continue
        for j, inp in enumerate(art["inputs"]):
            if inp["sha256"].lower() in digests:
                found.append(
                    {"artefact": art.get("id", ""), "input": inp.get("id", ""), "pointer": f"/artefacts/{i}/inputs/{j}"}
                )
    return found


def assert_excluded(manifest: Any, dewit_sha256: Iterable[str]) -> None:
    """Raise ``DewitLeakError`` when a guarded artefact lists the real series (``ValueError`` if malformed)."""
    found = leaks(manifest, dewit_sha256)
    if found:
        raise DewitLeakError(found)
