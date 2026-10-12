"""s10_preprocess (spec 008): validation that rejects and never coerces, the outlier policy and the file validators."""

from pitstudio_pipeline.ingest.tables import ingest_table, validate_table

__all__ = ["ingest_table", "validate_table"]
