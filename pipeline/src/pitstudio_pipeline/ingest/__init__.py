"""s10_preprocess (spec 008): validation that rejects and never coerces, the outlier policy and the file validators."""

from pitstudio_pipeline.ingest.exclusions import ExclusionResult, apply_exclusions
from pitstudio_pipeline.ingest.series import validate_series
from pitstudio_pipeline.ingest.tables import ingest_source, ingest_table, validate_table

__all__ = ["ExclusionResult", "apply_exclusions", "ingest_source", "ingest_table", "validate_series", "validate_table"]
