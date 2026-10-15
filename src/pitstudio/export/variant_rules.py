"""Which precision variants may be requested (FR-016-10)."""

from __future__ import annotations

PRECISIONS = ("fp32", "fp16", "int8", "fp8")
FP8_MIN_OPSET = 19


class VariantRefused(Exception):
    """A precision request that `s60_export` and `s62_accel` refuse; `.reason` names the precision or the condition."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check_variant_request(precision: str, *, opset: int, gemm_heavy: bool) -> None:
    """Accept exactly fp32, fp16, int8 and fp8; fp8 only for a graph at opset >= 19 flagged `gemm_heavy`."""
    if not isinstance(precision, str) or precision not in PRECISIONS:
        raise VariantRefused(f"precision {precision!r} is not one of {', '.join(PRECISIONS)}")
    if precision == "fp8":
        if isinstance(opset, bool) or not isinstance(opset, int) or opset < FP8_MIN_OPSET:
            raise VariantRefused(f"fp8 needs opset >= {FP8_MIN_OPSET}, the graph has opset {opset!r}")
        if gemm_heavy is not True:
            raise VariantRefused("fp8 is only built for graphs flagged gemm_heavy")
