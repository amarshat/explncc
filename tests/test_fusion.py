"""Fusion: group raw records into one finding per compiler decision."""

from __future__ import annotations

from pathlib import Path

from explncc.fusion import FusedFinding, fuse_records
from explncc.models import OptimizationRecord
from explncc.records_loader import load_records

FIXTURES = Path(__file__).parent / "fixtures" / "fusion"

# Tests inject a fixed name map so they never depend on a system demangler.
NAME_MAP = {
    "_Z4scanPfPKfi": "scan(float*, float const*, int)",
    "_Z3dotPKfS0_i": "dot(float const*, float const*, int)",
    "_Z5saxpyPfPKffi": "saxpy(float*, float const*, float, int)",
    "_Z10use_helperf": "use_helper(float)",
    "_Z6helperf": "helper(float)",
}


def _fixture_findings(**kwargs: object) -> list[FusedFinding]:
    records = load_records(FIXTURES / "hot.opt.yaml")
    return fuse_records(records, name_map=NAME_MAP, **kwargs)  # type: ignore[arg-type]


def test_missed_rollup_absorbs_sibling_analysis_cause() -> None:
    findings = _fixture_findings()
    scan = [f for f in findings if f.function == "_Z4scanPfPKfi" and f.kind == "missed"]
    assert len(scan) == 1
    finding = scan[0]
    # MissedDetails + UnsafeDep fold into one finding carrying the real cause.
    assert finding.count == 2
    assert finding.headline == "not vectorized: loop-carried dependence"
    assert finding.cause is not None
    assert "Backward loop carried data dependence" in finding.cause
    assert "unsafe dependent memory operations" in finding.cause
    # The suggestion is the compiler's own sentence, extracted verbatim.
    assert finding.suggestion is not None
    assert finding.suggestion.startswith("Use #pragma clang loop distribute(enable)")
    assert "Use #pragma" not in finding.cause
    # Caret points at the cause column (the offending expression), not the loop keyword.
    assert finding.caret_column == 38
    assert finding.column == 5


def test_no_orphan_analysis_finding_for_consumed_cause() -> None:
    findings = _fixture_findings()
    unsafedep_alone = [f for f in findings if f.remark_name == "UnsafeDep"]
    assert unsafedep_alone == []


def test_duplicate_slp_records_dedup_into_one_finding() -> None:
    findings = _fixture_findings()
    slp = [f for f in findings if f.pass_name == "slp-vectorizer"]
    assert len(slp) == 1
    assert slp[0].count == 2
    assert slp[0].headline == "SLP not beneficial (cost 0 >= threshold 0)"


def test_inline_no_definition_headline_uses_demangled_callee() -> None:
    findings = _fixture_findings()
    inline = [f for f in findings if f.pass_name == "inline"]
    assert len(inline) == 1
    assert inline[0].headline == "not inlined: helper(float) has no definition in this TU"
    assert inline[0].function_display == "use_helper(float)"


def test_vectorized_headline_carries_width_and_interleave() -> None:
    findings = _fixture_findings()
    wins = [f for f in findings if f.headline.startswith("vectorized")]
    assert len(wins) == 2
    assert all(f.headline == "vectorized (width 4, interleave 4)" for f in wins)


def test_noise_passes_excluded_by_default_included_with_flag() -> None:
    default = _fixture_findings()
    assert all(f.pass_name not in {"asm-printer", "prologepilog"} for f in default)
    with_noise = _fixture_findings(include_noise=True)
    noisy = [f for f in with_noise if f.pass_name in {"asm-printer", "prologepilog"}]
    assert noisy, "include_noise=True should surface asm-printer/prologepilog records"


def test_sorted_by_severity_missed_vectorization_first() -> None:
    findings = _fixture_findings()
    assert findings[0].category == "vectorize-missed"
    severities = [f.severity for f in findings]
    assert severities == sorted(severities, reverse=True)


def test_fusion_is_deterministic() -> None:
    a = [f.finding_key() for f in _fixture_findings()]
    b = [f.finding_key() for f in _fixture_findings()]
    assert a == b


def test_cause_slack_does_not_join_across_functions() -> None:
    rollup = OptimizationRecord(
        kind="missed",
        pass_name="loop-vectorize",
        remark_name="MissedDetails",
        function="f",
        file="x.cpp",
        line=10,
        message="loop not vectorized",
    )
    other_fn_analysis = OptimizationRecord(
        kind="analysis",
        pass_name="loop-vectorize",
        remark_name="UnsafeDep",
        function="g",
        file="x.cpp",
        line=10,
        message="loop not vectorized: unsafe dependent memory operations in loop.",
    )
    findings = fuse_records([rollup, other_fn_analysis], name_map={})
    missed = [f for f in findings if f.kind == "missed"]
    assert missed[0].count == 1
    assert missed[0].headline == "not vectorized"


def test_cause_slack_joins_nearby_lines_same_function() -> None:
    rollup = OptimizationRecord(
        kind="missed",
        pass_name="loop-vectorize",
        remark_name="MissedDetails",
        function="f",
        file="x.cpp",
        line=10,
        message="loop not vectorized",
    )
    nearby = OptimizationRecord(
        kind="analysis",
        pass_name="loop-vectorize",
        remark_name="CantReorderFPOps",
        function="f",
        file="x.cpp",
        line=12,
        column=17,
        message=(
            "loop not vectorized: cannot prove it is safe to reorder floating-point operations"
        ),
    )
    far = OptimizationRecord(
        kind="analysis",
        pass_name="loop-vectorize",
        remark_name="UnsafeDep",
        function="f",
        file="x.cpp",
        line=40,
        message="loop not vectorized: unsafe dependent memory operations in loop.",
    )
    findings = fuse_records([rollup, nearby, far], name_map={})
    missed = [f for f in findings if f.kind == "missed"][0]
    assert missed.count == 2
    assert missed.headline == "not vectorized: floating-point reduction order"
    assert missed.caret_column == 17
    # The far analysis stays its own finding rather than being misattributed.
    leftovers = [f for f in findings if f.remark_name == "UnsafeDep"]
    assert len(leftovers) == 1


def test_hls_records_get_ii_headlines() -> None:
    missed_ii = OptimizationRecord(
        kind="missed",
        pass_name="hls-pipeline",
        remark_name="IINotAchieved",
        function="update_book",
        file="k.cpp",
        line=7,
        initiation_interval=3,
        target_ii=1,
        message="unable to achieve II=1 due to carried dependency on acc",
    )
    pipelined = OptimizationRecord(
        kind="passed",
        pass_name="hls-pipeline",
        remark_name="Pipelined",
        function="stream_sum",
        file="k.cpp",
        line=3,
        initiation_interval=1,
        message="pipelined at II=1",
    )
    findings = fuse_records([missed_ii, pipelined], name_map={})
    assert findings[0].headline == "II target missed (achieved 3 vs target 1)"
    assert findings[0].category == "hls-missed"
    assert findings[1].headline == "pipelined (II=1)"


def test_inline_too_costly_headline() -> None:
    record = OptimizationRecord(
        kind="missed",
        pass_name="inline",
        remark_name="TooCostly",
        function="hot",
        callee="cold",
        file="x.cpp",
        line=5,
        cost="815",
        threshold="812",
        message=(
            "cold will not be inlined into hot because too costly to inline "
            "(cost=815, threshold=812)"
        ),
    )
    findings = fuse_records([record], name_map={})
    assert findings[0].headline == "not inlined: cost 815 > threshold 812"
