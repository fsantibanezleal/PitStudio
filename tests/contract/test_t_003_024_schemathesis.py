# ruff: noqa: E501
"""T-003-024: Schemathesis over the console's OpenAPI document, in process (US-003-2).

Requirements: NFR-003-02, SC-003-01.

Run: the committed document `api/openapi.json` (served unchanged by `GET /openapi.json`, see T-003-001) is loaded with
`schemathesis.openapi.from_asgi("/openapi.json", app, headers={"Host": "127.0.0.1:<port>"})` (the Host rule of FR-003-18 applies to
the loader too) against the application of tests/support/console_world.py (fixture store, no GPU, no network). For every
operation Schemathesis generates positive and negative requests (`property_tests.ci_examples_per_test` = 200 examples per mode) and
`case.call_and_validate()` applies exactly the eight checks of NFR-003-02: not_a_server_error, status_code_conformance,
content_type_conformance, response_schema_conformance, negative_data_rejection, positive_data_acceptance, unsupported_method and
max_response_time (`console.response_ms_max` = 2,000 ms). Zero failures. An operation for which no negative data can be generated
(no constrained parameter) is skipped for that mode only.
Expected product facts: the schemas and status codes of the OpenAPI document are accurate (unknown well-formed ids document 404,
malformed ones 422, hostile bodies 400/413/415/422, undefined methods 405) so that every check can pass.
Oracle: Schemathesis 4.x itself (the reference implementation named by the plan), configured only from thresholds.yaml.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import runner_world as rw

THRESHOLDS = yaml.safe_load((rw.ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))
CHECKS = [
    "not_a_server_error",
    "status_code_conformance",
    "content_type_conformance",
    "response_schema_conformance",
    "negative_data_rejection",
    "positive_data_acceptance",
    "unsupported_method",
    "max_response_time",
]
HOST = f"127.0.0.1:{cw.PORT}"


@pytest.fixture(scope="module")
def cons(tmp_path_factory: pytest.TempPathFactory):
    mp = pytest.MonkeyPatch()
    c = cw.make_console_world(mp, tmp_path_factory.mktemp("schemathesis"))
    yield c
    mp.undo()
    rw.cleanup_world(c.w)


@pytest.mark.req("NFR-003-02")
@pytest.mark.req("SC-003-01")
def test_nfr_003_02_schemathesis_finds_no_failure_with_the_eight_checks_and_200_examples_per_operation(cons) -> None:
    import schemathesis
    from hypothesis import HealthCheck, given, settings
    from hypothesis.errors import Unsatisfiable
    from schemathesis import GenerationMode

    examples = THRESHOLDS["property_tests"]["ci_examples_per_test"]
    limit_s = THRESHOLDS["console"]["response_ms_max"] / 1000
    assert (examples, limit_s) == (200, 2.0)

    schema = schemathesis.openapi.from_asgi("/openapi.json", cons.app, headers={"Host": HOST})
    schema.config.checks.update(included_check_names=CHECKS, max_response_time=limit_s)
    # FR-003-10: an unknown recipe, stage or profile is a 422, so a schema-valid body that names none is not a 2xx
    schema.config.checks.positive_data_acceptance.expected_statuses = [
        "2xx",
        "3xx",
        "401",
        "403",
        "404",
        "409",
        "422",
        "429",
        "5xx",
    ]
    operations = [r.ok() for r in schema.get_all_operations()]
    assert len(operations) >= 11, f"the document must describe every endpoint, found {len(operations)} operations"
    ran = {GenerationMode.POSITIVE: 0, GenerationMode.NEGATIVE: 0}

    def runner(op, mode):  # one Hypothesis test per (operation, generation mode)
        @settings(max_examples=examples, deadline=None, suppress_health_check=list(HealthCheck), database=None)
        @given(case=op.as_strategy(generation_mode=mode))
        def run(case) -> None:
            ran[mode] += 1
            case.call_and_validate(headers={"Host": HOST})

        return run

    for op in operations:
        for mode in (GenerationMode.POSITIVE, GenerationMode.NEGATIVE):
            try:
                runner(op, mode)()
            except Unsatisfiable:
                assert mode == GenerationMode.NEGATIVE, f"no valid request could be generated for {op.label}"
    assert ran[GenerationMode.POSITIVE] >= examples, (
        "positive generation must exercise at least one operation with the full example budget"
    )
    assert ran[GenerationMode.NEGATIVE] >= examples, (
        "negative generation must exercise at least one operation with the full example budget"
    )
