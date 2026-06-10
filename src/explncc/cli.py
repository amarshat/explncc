"""Command-line entry point for explncc."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console

from explncc import __version__
from explncc.alignment import (
    AlignmentLabel,
    alignment_signals,
    classify_alignment,
    filter_alignment_related,
)
from explncc.alignment_bench import build_alignment_bench_prompt_lines
from explncc.alignment_dataset import (
    ALIGNMENT_EXPORT_FORMATS,
    AlignmentExportFormat,
    build_alignment_training_rows,
)
from explncc.alignment_eval import evaluate_predictions, load_predictions_jsonl
from explncc.alignment_eval_output import render_eval_report
from explncc.alignment_pack import ALIGNMENT_LABELS, build_alignment_evidence_packs
from explncc.alignment_pack_output import render_alignment_evidence_packs
from explncc.bench_backends import render_bench, run_bench
from explncc.checks import build_policy_result, run_checks
from explncc.ci_manifest import CiManifest, write_manifest
from explncc.ci_report import parse_report_format, render_report
from explncc.config import ExplnccConfig, load_config, render_doctor
from explncc.context_snippets import ContextSnippetRequest
from explncc.dataset_llm import (
    ExportFormat,
    build_bench_prompt_lines,
    build_training_rows,
    write_jsonl,
)
from explncc.diffing import DiffReport, diff_records
from explncc.digest import build_digest, format_digest_json
from explncc.evidence import build_evidence_packs
from explncc.evidence_output import render_evidence_packs
from explncc.explain.backends import run_explanation, run_explanation_result
from explncc.exporters import export_csv, export_json, export_jsonl, record_to_json_dict
from explncc.fusion import FusedFinding, fuse_records
from explncc.local.classifier import classify_record
from explncc.local.contracts import Confidence, confidence_at_least
from explncc.local.ml_ranker import LocalModelRanker, ModelRankerUnavailable
from explncc.local.output import (
    CLASSIFY_COLUMNS,
    CLASSIFY_FORMATS,
    RANK_COLUMNS,
    RANK_FORMATS,
    classification_rows,
    ranked_rows,
    render_classifications,
    render_findings,
)
from explncc.local.ranker import LocalRankerV1, RankedFinding
from explncc.local.training_export import (
    TRAINING_FORMATS,
    render_training_rows,
)
from explncc.local.training_export import (
    build_training_rows as build_local_training_rows,
)
from explncc.models import OptimizationRecord
from explncc.records_loader import load_records
from explncc.render import print_table
from explncc.report_diff import build_report_diff, render_report_diff
from explncc.report_helpers import policy_thresholds_active, report_source_info, resolve_explanation
from explncc.report_types import ReportBuildOptions, ReportMetadata
from explncc.stats import aggregate
from explncc.summary import apply_filters, rows_for_table, truncate_message
from explncc.trace import build_trace, render_trace
from explncc.viz import parse_viz_format, parse_viz_style, render_viz
from explncc.why_output import render_findings as render_why_findings
from explncc.why_output import verdict_tag

app = typer.Typer(
    name="explncc",
    no_args_is_help=False,
    add_completion=False,
    help="Parse and analyze Clang/LLVM optimization remark logs (.opt.yaml).",
)
stdout_console = Console()


def _context_snippet_request(
    *,
    include_source: bool,
    source_root: Path | None,
    context_before: int,
    context_after: int,
    include_ir: bool,
    ir_file: Path | None,
    ir_lines: int,
    include_asm: bool = False,
    asm_file: Path | None = None,
    asm_lines: int = 60,
) -> ContextSnippetRequest | None:
    if not (include_source or include_ir or include_asm):
        return None
    return ContextSnippetRequest(
        include_source=include_source,
        source_root=source_root,
        context_before=context_before,
        context_after=context_after,
        include_ir=include_ir,
        ir_file=ir_file,
        ir_lines=ir_lines,
        include_asm=include_asm,
        asm_file=asm_file,
        asm_lines=asm_lines,
    )


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Explain Compiler: optimization logs for real-world performance work."""
    if ctx.invoked_subcommand is not None:
        return
    typer.echo(ctx.get_help())


@app.command("version")
def version_cmd() -> None:
    """Print the explncc version string."""
    typer.echo(__version__)


_RECORD_SUFFIXES = (".opt.yaml", ".yaml", ".yml", ".xml")
_DISCOVER_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__"}


def _discover_record_files(root: Path) -> list[Path]:
    """Find ``*.opt.yaml`` under ``root``, skipping VCS and venv directories."""

    found: list[Path] = []
    for path in sorted(root.rglob("*.opt.yaml")):
        parts = set(path.parts)
        if parts & _DISCOVER_SKIP_DIRS:
            continue
        if any(p.startswith(".") and p not in (".", "..") for p in path.parts[:-1]):
            continue
        if any((root / part / "pyvenv.cfg").is_file() for part in path.relative_to(root).parts[:1]):
            continue
        found.append(path)
    return found


def _looks_like_query(text: str) -> bool:
    """A query is ``file.cpp:NN``, a source file name, or a function substring."""

    if ":" in text:
        return True
    suffix = Path(text).suffix.lower()
    return suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"} or suffix == ""


def _parse_location_query(query: str) -> tuple[str, int | None] | None:
    """Parse ``file.cpp:NN`` or ``file.cpp``; ``None`` when not a file query."""

    candidate, line = query, None
    if ":" in query:
        head, _, tail = query.rpartition(":")
        if tail.isdigit():
            candidate, line = head, int(tail)
    suffix = Path(candidate).suffix.lower()
    if suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}:
        return candidate, line
    return None


def _finding_matches_query(finding: FusedFinding, query: str) -> bool:
    location = _parse_location_query(query)
    if location is not None:
        file_part, line = location
        if not finding.file:
            return False
        if Path(finding.file).name != Path(file_part).name:
            return False
        if line is None or finding.line is None:
            return True
        return abs(finding.line - line) <= 2
    needle = query.lower()
    haystacks = [finding.function or "", finding.function_display or ""]
    return any(needle in h.lower() for h in haystacks)


@app.command("why")
def why_cmd(
    target: Annotated[
        str,
        typer.Argument(
            help=(
                "Records (.opt.yaml file or directory), or a query like file.cpp:42 "
                "or a function name (records are then auto-discovered under the "
                "current directory)."
            ),
        ),
    ] = ".",
    query: Annotated[
        str | None,
        typer.Argument(
            help="Optional query: file.cpp:42, file.cpp, or a function name substring.",
        ),
    ] = None,
    function_contains: Annotated[
        str | None,
        typer.Option("--function", help="Filter findings by function name substring."),
    ] = None,
    pass_contains: Annotated[
        str | None,
        typer.Option("--pass", help="Filter findings by pass name substring."),
    ] = None,
    missed_only: Annotated[
        bool,
        typer.Option("--missed-only", help="Hide passed/positive findings."),
    ] = False,
    show_all: Annotated[
        bool,
        typer.Option("--all", help="Include per-instruction noise (asm-printer, prologepilog)."),
    ] = False,
    top: Annotated[
        int,
        typer.Option("--top", help="Show at most N findings (0 = all)."),
    ] = 10,
    source_root: Annotated[
        Path | None,
        typer.Option("--source-root", help="Directory to resolve source snippets against."),
    ] = None,
    explain: Annotated[
        bool,
        typer.Option(
            "--explain",
            help="Add a short model explanation under each missed finding (cap 5).",
        ),
    ] = False,
    backend: Annotated[
        str,
        typer.Option(
            "--backend",
            help="Backend for --explain: ollama (default, local) | openai | claude | rule.",
        ),
    ] = "ollama",
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model name override for the --explain backend."),
    ] = None,
    no_network: Annotated[
        bool,
        typer.Option("--no-network", help="Guardrail: forbid any network/model backend call."),
    ] = False,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Answer "why did the compiler do that?" for one loop, function, or file.

    Fuses raw remarks into one finding per compiler decision: the missed
    rollup, its analysis cause, and duplicates become a single entry with the
    compiler's own reason, a source caret, and the compiler's suggestion.
    """

    target_path = Path(target)
    effective_query = query
    records: list[OptimizationRecord] = []
    if target_path.exists() and (target_path.is_dir() or target.endswith(_RECORD_SUFFIXES)):
        records = _load_records_or_exit(target_path, toolchain=toolchain)
        default_root = target_path if target_path.is_dir() else target_path.parent
    elif _looks_like_query(target):
        effective_query = target if query is None else query
        discovered = _discover_record_files(Path.cwd())
        if not discovered:
            typer.secho("no .opt.yaml records found under the current directory.", err=True)
            typer.secho(
                "generate them by recompiling with optimization records enabled:\n"
                "  clang++ -O3 -fsave-optimization-record -c file.cpp\n"
                "then re-run: explncc why " + target,
                err=True,
            )
            raise typer.Exit(2)
        for path in discovered:
            records.extend(_load_records_or_exit(path, toolchain=toolchain))
        default_root = Path.cwd()
    else:
        typer.secho(f"{target}: not a records path and not a recognizable query", err=True)
        raise typer.Exit(2)

    explain_backend: str | None = None
    if explain:
        explain_backend = backend.strip().lower()
        config = load_config()
        if explain_backend in _NETWORK_BACKENDS and (no_network or config.no_network):
            source = "--no-network" if no_network else "EXPLNCC_NO_NETWORK/EXPLNCC_OFFLINE"
            typer.secho(
                f"{source} forbids network/model backend {explain_backend!r}; "
                "use --backend rule or drop --explain.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(2)

    findings = fuse_records(records, include_noise=show_all)
    _emit_why(
        findings,
        records_count=len(records),
        query=effective_query,
        function_contains=function_contains,
        pass_contains=pass_contains,
        missed_only=missed_only,
        top=top,
        source_root=source_root or default_root,
        noise_hidden=not show_all,
        explain_backend=explain_backend,
        model=model,
    )


_WHY_EXPLAIN_CAP = 5


def _emit_why(
    findings: list[FusedFinding],
    *,
    records_count: int,
    query: str | None,
    function_contains: str | None,
    pass_contains: str | None,
    missed_only: bool,
    top: int,
    source_root: Path,
    noise_hidden: bool,
    explain_backend: str | None = None,
    model: str | None = None,
) -> None:
    total = len(findings)
    if query:
        findings = [f for f in findings if _finding_matches_query(f, query)]
    if function_contains:
        needle = function_contains.lower()
        findings = [
            f
            for f in findings
            if needle in (f.function or "").lower()
            or needle in (f.function_display or "").lower()
        ]
    if pass_contains:
        findings = [f for f in findings if pass_contains.lower() in (f.pass_name or "").lower()]
    if missed_only:
        # The user-facing meaning of "missed": real MISS findings, not
        # bookkeeping that happens to arrive as a !Missed record (spills).
        findings = [f for f in findings if verdict_tag(f) == "MISS"]
    if not findings:
        scope = f" matching {query!r}" if query else ""
        typer.echo(f"no findings{scope} ({total} findings in the records overall)")
        return
    shown = len(findings) if top <= 0 else min(top, len(findings))
    if explain_backend is None:
        text = render_why_findings(
            findings,
            shown=shown,
            total_records=records_count,
            source_root=source_root,
            use_color=sys.stdout.isatty(),
            noise_hidden=noise_hidden,
        )
        typer.echo(text)
        return
    _emit_why_with_explanations(
        findings,
        shown=shown,
        records_count=records_count,
        source_root=source_root,
        noise_hidden=noise_hidden,
        explain_backend=explain_backend,
        model=model,
    )


def _emit_why_with_explanations(
    findings: list[FusedFinding],
    *,
    shown: int,
    records_count: int,
    source_root: Path,
    noise_hidden: bool,
    explain_backend: str,
    model: str | None,
) -> None:
    """Render findings one by one, streaming a short model note under each miss."""

    from explncc.explain.per_finding import FindingExplanation, explain_finding
    from explncc.why_output import render_finding

    use_color = sys.stdout.isatty()
    config = _config_with_model(load_config(), explain_backend, model)

    header_bits = [
        f"{len(findings)} finding{'s' if len(findings) != 1 else ''}",
        f"{records_count} records",
    ]
    if noise_hidden:
        header_bits.append("noise hidden; --all to show")
    typer.echo(f"explncc why: {', '.join(header_bits)}")
    typer.echo("")

    results: list[FindingExplanation] = []
    explained = 0
    indent = "  model:   "
    continuation = "\n" + " " * len(indent)
    for finding in findings[:shown]:
        for line in render_finding(finding, source_root=source_root, use_color=use_color):
            typer.echo(line)
        if verdict_tag(finding) == "MISS" and explained < _WHY_EXPLAIN_CAP:
            sys.stdout.write(indent)
            sys.stdout.flush()

            def _stream(chunk: str) -> None:
                sys.stdout.write(chunk.replace("\n", continuation))
                sys.stdout.flush()

            results.append(
                explain_finding(
                    finding,
                    backend=explain_backend,
                    config=config,
                    on_chunk=_stream,
                ),
            )
            explained += 1
            sys.stdout.write("\n")
            sys.stdout.flush()
        typer.echo("")
    if shown < len(findings):
        typer.echo(
            f"... {len(findings) - shown} more finding(s); use --top 0 to show everything",
        )

    if results:
        total_s = sum(r.latency_ms for r in results) / 1000.0
        cached = sum(1 for r in results if r.cache_hit)
        fell_back = sum(1 for r in results if r.fallback_used)
        generated = len(results) - cached - fell_back
        used_model = next((r.model for r in results if r.model), None)
        noun = "finding" if len(results) == 1 else "findings"
        if explain_backend == "rule":
            summary = (
                f"[explain] {len(results)} {noun}, deterministic evidence text (no model call)"
            )
        elif explain_backend == "ollama":
            summary = (
                f"[explain] {len(results)} {noun} in {total_s:.1f}s with "
                f"{used_model or 'ollama'} on-device: {generated} generated, "
                f"{cached} cached; nothing left this machine"
            )
        else:
            summary = (
                f"[explain] {len(results)} {noun} in {total_s:.1f}s with "
                f"{used_model or explain_backend} via the {explain_backend} API (network): "
                f"{generated} generated, {cached} cached"
            )
        if fell_back:
            summary += f"; {fell_back} fell back to evidence text"
        typer.secho(summary, err=True)


@app.command("bench-backends")
def bench_backends_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    backends: Annotated[
        list[str] | None,
        typer.Option(
            "--backend",
            help="Backend to bench (repeatable): rule | ollama | openai | claude.",
        ),
    ] = None,
    ollama_models: Annotated[
        list[str] | None,
        typer.Option(
            "--ollama-model",
            help="Ollama model tag to bench (repeatable; default: configured model).",
        ),
    ] = None,
    top: Annotated[
        int,
        typer.Option("--top", help="Bench the first N missed findings."),
    ] = 5,
    output_format: Annotated[
        str,
        typer.Option("--format", help="text | markdown"),
    ] = "text",
    cached: Annotated[
        bool,
        typer.Option(
            "--cached/--no-cached",
            help="Also time a cache replay per model row (what a re-run costs).",
        ),
    ] = True,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Measure explanation latency per backend on your own records.

    Same fused findings as ``why``, same per-finding short path, wall-clock
    timed. Unavailable backends become explicit skip rows instead of errors,
    so the table is honest about what ran.
    """

    records = _load_records_or_exit(target, toolchain=toolchain)
    findings = [f for f in fuse_records(records) if verdict_tag(f) == "MISS"]
    if not findings:
        typer.echo("no missed findings to bench in these records")
        raise typer.Exit(0)
    findings = findings[: max(1, top)]
    rows = run_bench(
        findings,
        config=load_config(),
        backends=backends or ["rule", "ollama"],
        ollama_models=ollama_models,
        include_cached=cached,
    )
    typer.echo(render_bench(rows, fmt=output_format.strip().lower()))
    typer.secho(
        f"[bench] {len(findings)} missed finding(s) from {target}; "
        "numbers are wall-clock on this machine, re-run on your own corpus",
        err=True,
    )


@app.command("doctor")
def doctor_cmd(
    report_format: Annotated[
        str,
        typer.Option("--format", help="text | json | markdown"),
    ] = "json",
) -> None:
    """Print masked backend-related configuration (safe for CI logs)."""
    fmt = report_format.strip().lower()
    if fmt == "text":
        fmt = "json"
    typer.echo(render_doctor(fmt))


@app.command("digest")
def digest_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    include_evidence: Annotated[
        bool,
        typer.Option("--include-evidence", help="Include evidence pack hash aggregate."),
    ] = False,
    include_prompts: Annotated[
        bool,
        typer.Option("--include-prompts", help="Include prompt hash for --template."),
    ] = False,
    template: Annotated[
        str | None,
        typer.Option("--template", help="Prompt template id when using --include-prompts."),
    ] = None,
) -> None:
    """Emit SHA-256 digests per ``.opt.yaml`` file plus cache keys."""
    if include_prompts and not template:
        typer.secho("--include-prompts requires --template", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    data = build_digest(
        target,
        include_evidence=include_evidence,
        include_prompts=include_prompts,
        template=template,
    )
    typer.echo(format_digest_json(data))


@app.command("trace")
def trace_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    report_format: Annotated[
        str,
        typer.Option("--format", help="text | json | markdown"),
    ] = "text",
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write trace report to this file."),
    ] = None,
    include_sample_record: Annotated[
        bool,
        typer.Option("--include-sample-record", help="Include one normalized record in output."),
    ] = False,
    include_sample_evidence: Annotated[
        bool,
        typer.Option("--include-sample-evidence", help="Include one evidence pack sample."),
    ] = False,
    include_evidence: Annotated[
        bool,
        typer.Option("--include-evidence", help="Count evidence packs in trace."),
    ] = False,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter (default: clang)."),
    ] = "clang",
) -> None:
    """Show how data flows through explncc layers for teaching and debugging."""
    _ = toolchain  # reserved; trace uses path discovery consistent with clang adapter
    data = build_trace(
        target,
        include_evidence=include_evidence or include_sample_evidence,
        include_sample_record=include_sample_record,
        include_sample_evidence=include_sample_evidence,
    )
    fmt = report_format.strip().lower()
    text = render_trace(fmt, data)
    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote trace to {output}")
    else:
        typer.echo(text)


@app.command("viz")
def viz_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
    style: Annotated[
        str,
        typer.Option(
            "--style",
            help="pass-summary | missed-top | pass-remark (see docs/chapter-14-notes.md).",
        ),
    ] = "pass-summary",
    viz_format: Annotated[
        str,
        typer.Option("--format", help="mermaid | html | json."),
    ] = "mermaid",
    top: Annotated[int, typer.Option("--top", help="Cap nodes or (pass,remark) pairs.")] = 12,
    title: Annotated[
        str,
        typer.Option("--title", help="HTML / JSON title; Mermaid comment when explaining."),
    ] = "Optimization remarks visualization",
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write to this file; default stdout."),
    ] = None,
    pass_contains: Annotated[
        str | None,
        typer.Option("--pass", help="Keep remarks whose pass name contains this substring."),
    ] = None,
    function_contains: Annotated[
        str | None,
        typer.Option(
            "--function",
            help="Keep remarks whose function name contains this substring.",
        ),
    ] = None,
    kind: Annotated[str | None, typer.Option("--kind", help="Filter by remark kind.")] = None,
    explain_file: Annotated[
        Path | None,
        typer.Option(
            "--explain-file",
            help="Merge this text into html/json (or Mermaid %% comment for mermaid).",
        ),
    ] = None,
    explain_backend: Annotated[
        str | None,
        typer.Option(
            "--explain-backend",
            help="If set (and no --explain-file), run explainer: rule | ollama | openai | "
            "claude | auto.",
        ),
    ] = None,
    explain_limit: Annotated[
        int,
        typer.Option("--explain-limit", help="Max records passed to explainer."),
    ] = 32,
    ai_limit: Annotated[
        int,
        typer.Option("--ai-limit", help="Max records serialized for model backends."),
    ] = 40,
) -> None:
    """Emit Mermaid diagrams, HTML with Mermaid.js, or JSON for external graph tools."""

    try:
        vstyle = parse_viz_style(style)
    except ValueError:
        typer.secho(f"unknown --style {style!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from None
    try:
        vfmt = parse_viz_format(viz_format)
    except ValueError:
        typer.secho(f"unknown --format {viz_format!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from None

    records = _load_records_or_exit(target, toolchain=toolchain)
    records = apply_filters(
        records,
        pass_contains=pass_contains,
        function_contains=function_contains,
        kind=kind,
    )

    explain_text: str | None = None
    if explain_file is not None:
        if not explain_file.is_file():
            typer.secho(f"not a file: {explain_file}", fg=typer.colors.RED, err=True)
            raise typer.Exit(2)
        explain_text = explain_file.read_text(encoding="utf-8")
    elif explain_backend is not None:
        config = load_config()
        mode = explain_backend.strip().lower()
        if mode == "openai" and not config.openai_api_key:
            typer.secho("openai backend requires OPENAI_API_KEY", fg=typer.colors.RED, err=True)
            raise typer.Exit(2)
        if mode == "claude" and not config.anthropic_api_key:
            typer.secho("claude backend requires ANTHROPIC_API_KEY", fg=typer.colors.RED, err=True)
            raise typer.Exit(2)
        subset = records[:explain_limit] if explain_limit > 0 else records
        explain_text = run_explanation(subset, backend=mode, config=config, ai_limit=ai_limit)

    text = render_viz(
        vfmt,
        records,
        vstyle,
        top=top,
        title=title,
        explanation=explain_text,
    )
    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {output}")
    else:
        typer.echo(text.rstrip("\n"))


def _load_records_or_exit(path: Path, *, toolchain: str = "clang") -> list[OptimizationRecord]:
    try:
        return load_records(path, toolchain=toolchain)
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc


def _config_with_model(config: ExplnccConfig, mode: str, model: str | None) -> ExplnccConfig:
    """Return ``config`` with the selected backend's model overridden."""

    if not model:
        return config
    name = model.strip()
    if mode in ("ollama", "auto"):
        return dataclasses.replace(config, ollama_model=name)
    if mode == "openai":
        return dataclasses.replace(config, openai_model=name)
    if mode == "claude":
        return dataclasses.replace(config, anthropic_model=name)
    return config


_NETWORK_BACKENDS = {"openai", "claude", "ollama", "auto"}


def _enforce_offline_guardrails(
    *,
    backend: str | None,
    backend_explicit: bool,
    offline: bool,
    no_network: bool,
    use_local: bool,
    config_no_network: bool = False,
) -> None:
    """Fail fast when offline guardrails conflict with a requested network backend.

    - ``--offline`` implies local and forbids any network/model backend.
    - ``--no-network`` (flag or ``EXPLNCC_NO_NETWORK``/``EXPLNCC_OFFLINE`` env)
      forbids OpenAI/Claude/Ollama/auto HTTP calls.
    Both exit with code 2 and an explanatory message rather than reaching out.
    """

    requested = (backend or "").strip().lower()
    is_network_backend = backend_explicit and requested in _NETWORK_BACKENDS
    if offline and is_network_backend:
        typer.secho(
            f"--offline forbids network/model backend {requested!r}; "
            "remove --offline or use --backend rule / --local.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)
    if (no_network or config_no_network) and is_network_backend:
        source = "--no-network" if no_network else "EXPLNCC_NO_NETWORK/EXPLNCC_OFFLINE"
        typer.secho(
            f"{source} forbids network/model backend {requested!r}; "
            "use --backend rule or --local.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)
    # ``use_local`` participates so callers can pass it for future policy hooks.
    _ = use_local


def _top_delta_items(mapping: dict[str, int], limit: int = 20) -> list[tuple[str, int]]:
    return sorted(mapping.items(), key=lambda x: abs(x[1]), reverse=True)[:limit]


def _diff_report_to_jsonable(report: DiffReport) -> dict[str, Any]:
    return {
        "new_missed": [record_to_json_dict(r) for r in report.new_missed],
        "resolved_missed": [record_to_json_dict(r) for r in report.resolved_missed],
        "pass_count_before": report.pass_count_before,
        "pass_count_after": report.pass_count_after,
        "pass_count_delta": report.pass_count_delta,
        "reason_delta_missed": report.reason_delta_missed,
        "function_delta_missed": report.function_delta_missed,
    }


@app.command("evidence")
def evidence_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    pass_contains: Annotated[
        str | None,
        typer.Option("--pass", help="Keep remarks whose pass name contains this substring."),
    ] = None,
    function_contains: Annotated[
        str | None,
        typer.Option(
            "--function",
            help="Keep remarks whose demangled or mangled function name contains this substring.",
        ),
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="Filter by remark kind: missed, passed, or analysis."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max evidence packs after filtering.")] = 0,
    evidence_format: Annotated[
        str,
        typer.Option("--format", help="json | jsonl | markdown"),
    ] = "json",
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write to this file; default stdout."),
    ] = None,
    include_source: Annotated[
        bool,
        typer.Option(
            "--include-source",
            help="Attach a source window around DebugLoc (requires snippet support).",
        ),
    ] = False,
    source_root: Annotated[
        Path | None,
        typer.Option(
            "--source-root",
            help="Project root for resolving relative DebugLoc paths (with --include-source).",
        ),
    ] = None,
    context_before: Annotated[
        int,
        typer.Option(
            "--context-before",
            help="Lines before the remark line (with --include-source).",
        ),
    ] = 5,
    context_after: Annotated[
        int,
        typer.Option(
            "--context-after",
            help="Lines after the remark line (with --include-source).",
        ),
    ] = 8,
    include_ir: Annotated[
        bool,
        typer.Option("--include-ir", help="Attach a bounded LLVM IR slice (requires IR support)."),
    ] = False,
    ir_file: Annotated[
        Path | None,
        typer.Option("--ir-file", help="IR file to slice (with --include-ir)."),
    ] = None,
    ir_lines: Annotated[
        int,
        typer.Option("--ir-lines", help="Approximate max IR lines in the snippet."),
    ] = 40,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Emit deterministic evidence packs (JSON / JSONL / Markdown) for prompts and tooling."""

    if include_source and source_root is None:
        typer.secho("--include-source requires --source-root", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if include_ir and ir_file is None:
        typer.secho("--include-ir requires --ir-file", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if context_before < 0 or context_after < 0:
        typer.secho(
            "--context-before and --context-after must be non-negative",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)
    if ir_lines < 1:
        typer.secho("--ir-lines must be at least 1", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target, toolchain=toolchain)
    records = apply_filters(
        records,
        pass_contains=pass_contains,
        function_contains=function_contains,
        kind=kind,
    )
    if limit > 0:
        records = records[:limit]

    context = _context_snippet_request(
        include_source=include_source,
        source_root=source_root,
        context_before=context_before,
        context_after=context_after,
        include_ir=include_ir,
        ir_file=ir_file,
        ir_lines=ir_lines,
    )
    packs = build_evidence_packs(records, context=context)
    try:
        text = render_evidence_packs(packs, evidence_format)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc

    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {len(packs)} evidence pack(s) to {output}")
    else:
        typer.echo(text.rstrip("\n"))


@app.command("summary")
def summary_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    pass_contains: Annotated[
        str | None,
        typer.Option("--pass", help="Keep remarks whose pass name contains this substring."),
    ] = None,
    function_contains: Annotated[
        str | None,
        typer.Option(
            "--function",
            help="Keep remarks whose function name contains this substring.",
        ),
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="Filter by remark kind: missed, passed, or analysis."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max rows after filtering.")] = 0,
    max_message: Annotated[
        int,
        typer.Option("--max-message", help="Truncate rendered message column."),
    ] = 120,
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON array to stdout.")] = False,
    as_jsonl: Annotated[bool, typer.Option("--jsonl", help="Emit JSON Lines to stdout.")] = False,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Print a tabular summary of normalized optimization remarks."""

    if as_json and as_jsonl:
        typer.secho("choose only one of --json or --jsonl", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target, toolchain=toolchain)
    records = apply_filters(
        records,
        pass_contains=pass_contains,
        function_contains=function_contains,
        kind=kind,
    )
    if limit > 0:
        records = records[:limit]

    if as_json:
        typer.echo(export_json(records))
        return
    if as_jsonl:
        typer.echo(export_jsonl(records).rstrip("\n"))
        return

    columns = ("kind", "pass", "remark", "function", "location", "message")
    rows = rows_for_table(records, max_message=max_message)
    print_table(stdout_console, columns, rows, title=f"explncc summary ({len(records)} remarks)")


@app.command("stats")
def stats_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable aggregates."),
    ] = False,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Show aggregate counts by pass, kind, function, and reason."""

    records = _load_records_or_exit(target, toolchain=toolchain)
    stats = aggregate(records)
    if as_json:
        typer.echo(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    stdout_console.print(f"[bold]Total remarks:[/bold] {stats['total']}")
    for label, key in (
        ("By pass", "by_pass"),
        ("By kind", "by_kind"),
        ("By function (top 15)", "by_function"),
        ("By reason (top 15)", "by_reason"),
    ):
        stdout_console.print(f"\n[bold]{label}[/bold]")
        data = stats[key]
        items = list(data.items())[:15]
        print_table(stdout_console, ("key", "count"), items, title=None)


@app.command("diff")
def diff_cmd(
    before: Annotated[Path, typer.Argument(help="Before build: file or directory")],
    after: Annotated[Path, typer.Argument(help="After build: file or directory")],
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON diff report.")] = False,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Compare two optimization record sets (CI-friendly missed deltas)."""

    b = _load_records_or_exit(before, toolchain=toolchain)
    a = _load_records_or_exit(after, toolchain=toolchain)
    report = diff_records(b, a)
    if as_json:
        typer.echo(json.dumps(_diff_report_to_jsonable(report), indent=2, ensure_ascii=False))
        return

    stdout_console.print(
        f"[bold]New missed[/bold] ({len(report.new_missed)}): "
        f"present after, absent before (by fingerprint).",
    )
    print_table(
        stdout_console,
        ("pass", "remark", "function", "location", "message"),
        rows_for_table(report.new_missed, max_message=100),
    )
    stdout_console.print(
        f"\n[bold]Resolved missed[/bold] ({len(report.resolved_missed)}): "
        f"present before, absent after.",
    )
    print_table(
        stdout_console,
        ("pass", "remark", "function", "location", "message"),
        rows_for_table(report.resolved_missed, max_message=100),
    )

    pd_items = _top_delta_items(report.pass_count_delta)
    stdout_console.print("\n[bold]Pass count delta (after - before, top by magnitude)[/bold]")
    print_table(stdout_console, ("pass", "delta"), pd_items)

    rd_items = _top_delta_items(report.reason_delta_missed)
    stdout_console.print("\n[bold]Missed reason delta[/bold]")
    print_table(stdout_console, ("reason", "delta"), rd_items)

    fd_items = _top_delta_items(report.function_delta_missed)
    stdout_console.print("\n[bold]Missed-by-function delta[/bold]")
    print_table(stdout_console, ("function", "delta"), fd_items)


@app.command("explain")
def explain_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    backend: Annotated[
        str | None,
        typer.Option(
            "--backend",
            help="rule | ollama | openai | claude | auto (default: EXPLNCC_BACKEND or rule).",
        ),
    ] = None,
    local: Annotated[
        bool,
        typer.Option(
            "--local",
            help="Offline local explanation (classify + rank + templates). No network.",
        ),
    ] = False,
    offline: Annotated[
        bool,
        typer.Option("--offline", help="Alias for --local that also forbids network backends."),
    ] = False,
    no_network: Annotated[
        bool,
        typer.Option("--no-network", help="Guardrail: forbid any network/model backend call."),
    ] = False,
    pass_contains: Annotated[
        str | None,
        typer.Option("--pass", help="Filter pass name substring."),
    ] = None,
    function_contains: Annotated[
        str | None,
        typer.Option("--function", help="Filter function name substring."),
    ] = None,
    kind: Annotated[str | None, typer.Option("--kind", help="Filter remark kind.")] = None,
    focus: Annotated[
        str | None,
        typer.Option("--focus", help="Set to 'alignment' to enable alignment labels (local)."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max records fed to templates / model."),
    ] = 64,
    ai_limit: Annotated[
        int,
        typer.Option("--ai-limit", help="Max records serialized for model backends."),
    ] = 48,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Model name override for the selected backend (e.g. an Ollama tag).",
        ),
    ] = None,
    stats: Annotated[
        bool,
        typer.Option("--stats", help="Print backend, model, latency, and cache hit to stderr."),
    ] = False,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Rule-based explanations with optional model augmentation."""

    config = load_config()
    backend_explicit = backend is not None
    use_local = local or offline or (not backend_explicit and config.default_backend == "local")
    _enforce_offline_guardrails(
        backend=backend,
        backend_explicit=backend_explicit,
        offline=offline,
        no_network=no_network,
        use_local=use_local,
        config_no_network=config.no_network,
    )
    if use_local:
        records = _load_records_or_exit(target, toolchain=toolchain)
        records = apply_filters(
            records,
            pass_contains=pass_contains,
            function_contains=function_contains,
            kind=kind,
        )
        if limit > 0:
            records = records[:limit]
        from explncc.local.explain import build_local_explanation

        typer.echo(build_local_explanation(records, focus=focus))
        return

    mode = (backend or config.default_backend).strip().lower()
    if mode == "openai" and not config.openai_api_key:
        typer.secho(
            "openai backend requires OPENAI_API_KEY",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)
    if mode == "claude" and not config.anthropic_api_key:
        typer.secho(
            "claude backend requires ANTHROPIC_API_KEY",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    records = _load_records_or_exit(target, toolchain=toolchain)
    records = apply_filters(
        records,
        pass_contains=pass_contains,
        function_contains=function_contains,
        kind=kind,
    )
    if limit > 0:
        records = records[:limit]

    # run_explanation_result (not run_explanation) so the on-device explanation
    # cache participates: an unchanged input never re-runs the model.
    result = run_explanation_result(
        records,
        backend=mode,
        config=_config_with_model(config, mode, model),
        ai_limit=ai_limit,
    )
    typer.echo(result.text)
    if stats:
        typer.secho(
            f"[stats] backend={result.backend} model={result.model or '-'} "
            f"latency_ms={result.latency_ms} cache_hit={result.cache_hit} "
            f"fallback={result.fallback_used}",
            err=True,
        )


def _resolve_findings(
    records: list[OptimizationRecord],
    *,
    ranker: str,
    model_path: Path | None,
    include_passed: bool,
    focus: str | None,
) -> list[RankedFinding]:
    """Select heuristic or model ranker and return ranked findings."""

    mode = ranker.strip().lower()
    if mode == "model":
        if model_path is None:
            typer.secho(
                "--ranker model requires --model-path",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(2)
        try:
            model = LocalModelRanker.load(model_path)
            return model.rank(records)
        except ModelRankerUnavailable as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(2) from exc
    if mode != "heuristic":
        typer.secho(f"unknown --ranker {ranker!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    return LocalRankerV1(include_passed=include_passed, focus=focus).rank_records(records)


@app.command("classify")
def classify_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    local: Annotated[
        bool,
        typer.Option("--local/--no-local", help="Use the offline local classifier (default)."),
    ] = True,
    classify_format: Annotated[
        str,
        typer.Option("--format", help="table | json | jsonl | markdown"),
    ] = "table",
    label_filter: Annotated[
        str | None,
        typer.Option("--label-filter", help="Keep only this local label."),
    ] = None,
    min_confidence: Annotated[
        str | None,
        typer.Option("--min-confidence", help="low | medium | high"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max rows after filtering.")] = 0,
    focus: Annotated[
        str | None,
        typer.Option("--focus", help="Set to 'alignment' to enable alignment labels."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write to this file; default stdout."),
    ] = None,
) -> None:
    """Classify remarks into local labels offline (rule-based, no network)."""

    _ = local  # local is the only path for classify; flag is for symmetry/CI clarity.
    fmt = classify_format.strip().lower()
    if fmt not in CLASSIFY_FORMATS:
        typer.secho(f"unknown --format {classify_format!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    min_conf: Confidence | None = None
    if min_confidence is not None:
        mc = min_confidence.strip().lower()
        if mc not in {"low", "medium", "high"}:
            typer.secho(
                "--min-confidence must be low, medium, or high",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(2)
        min_conf = cast(Confidence, mc)

    records = _load_records_or_exit(target)
    results = [classify_record(r, focus=focus) for r in records]

    paired = list(zip(records, results, strict=True))
    if label_filter:
        paired = [(r, c) for (r, c) in paired if c.label == label_filter]
    if min_conf is not None:
        paired = [(r, c) for (r, c) in paired if confidence_at_least(c.confidence, min_conf)]
    if limit > 0:
        paired = paired[:limit]

    f_records = [r for (r, _c) in paired]
    f_results = [c for (_r, c) in paired]

    if fmt == "table":
        rows = classification_rows(f_records, f_results)
        if output is not None:
            text = render_classifications(f_records, f_results, "markdown")
            output.write_text(text, encoding="utf-8")
            typer.echo(f"wrote {len(rows)} classification(s) to {output}")
        else:
            print_table(
                stdout_console,
                CLASSIFY_COLUMNS,
                rows,
                title=f"local classification ({len(rows)} remarks)",
            )
        return

    text = render_classifications(f_records, f_results, fmt)
    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {len(f_results)} classification(s) to {output}")
    else:
        typer.echo(text)


@app.command("rank")
def rank_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    local: Annotated[
        bool,
        typer.Option("--local/--no-local", help="Use the offline local ranker (default)."),
    ] = True,
    rank_format: Annotated[
        str,
        typer.Option("--format", help="table | json | jsonl | markdown"),
    ] = "table",
    top: Annotated[int, typer.Option("--top", help="Keep only the top N findings.")] = 0,
    min_score: Annotated[
        float | None,
        typer.Option("--min-score", help="Drop findings below this raw score."),
    ] = None,
    include_passed: Annotated[
        bool,
        typer.Option("--include-passed", help="Do not penalize / drop passed remarks."),
    ] = False,
    ranker: Annotated[
        str,
        typer.Option("--ranker", help="heuristic | model (default: heuristic)."),
    ] = "heuristic",
    model_path: Annotated[
        Path | None,
        typer.Option("--model-path", help="Path to a trained model (with --ranker model)."),
    ] = None,
    focus: Annotated[
        str | None,
        typer.Option("--focus", help="Set to 'alignment' to enable alignment labels."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write to this file; default stdout."),
    ] = None,
) -> None:
    """Rank remarks by developer relevance offline (deterministic, explainable)."""

    _ = local
    fmt = rank_format.strip().lower()
    if fmt not in RANK_FORMATS:
        typer.secho(f"unknown --format {rank_format!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target)
    findings = _resolve_findings(
        records,
        ranker=ranker,
        model_path=model_path,
        include_passed=include_passed,
        focus=focus,
    )
    if min_score is not None:
        findings = [f for f in findings if f.score >= min_score]
    if top > 0:
        findings = findings[:top]

    if fmt == "table":
        rows = ranked_rows(findings)
        if output is not None:
            text = render_findings(findings, "markdown")
            output.write_text(text, encoding="utf-8")
            typer.echo(f"wrote {len(findings)} finding(s) to {output}")
        else:
            print_table(
                stdout_console,
                RANK_COLUMNS,
                rows,
                title=f"ranked findings ({len(findings)})",
            )
        return

    text = render_findings(findings, fmt)
    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {len(findings)} finding(s) to {output}")
    else:
        typer.echo(text)


@app.command("export-training")
def export_training_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    training_format: Annotated[
        str,
        typer.Option("--format", help="jsonl | csv"),
    ] = "jsonl",
    include_labels_from: Annotated[
        str,
        typer.Option("--include-labels-from", help="Label source: rules."),
    ] = "rules",
    focus: Annotated[
        str | None,
        typer.Option("--focus", help="Set to 'alignment' to enable alignment labels."),
    ] = None,
    include_passed: Annotated[
        bool,
        typer.Option("--include-passed", help="Do not penalize passed remarks when scoring."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write to this file; default stdout."),
    ] = None,
) -> None:
    """Export normalized feature rows + rule labels for future model training (offline)."""

    fmt = training_format.strip().lower()
    if fmt not in TRAINING_FORMATS:
        typer.secho(f"unknown --format {training_format!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target)
    try:
        rows = build_local_training_rows(
            records,
            include_labels_from=include_labels_from,
            focus=focus,
            include_passed=include_passed,
        )
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc

    text = render_training_rows(rows, fmt)
    if output is not None:
        suffix = "" if text.endswith("\n") else "\n"
        output.write_text(text + suffix, encoding="utf-8")
        typer.echo(f"wrote {len(rows)} training row(s) to {output}")
    else:
        typer.echo(text)


@app.command("export")
def export_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    fmt: Annotated[
        str,
        typer.Option("--format", help="json | jsonl | csv", case_sensitive=False),
    ] = "json",
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write to this file instead of stdout."),
    ] = None,
) -> None:
    """Export normalized records for downstream tooling."""

    records = _load_records_or_exit(target)
    fmt_l = fmt.lower()
    if fmt_l == "json":
        text = export_json(records, path=output)
    elif fmt_l == "jsonl":
        text = export_jsonl(records, path=output)
    elif fmt_l == "csv":
        text = export_csv(records, path=output)
    else:
        typer.secho(f"unknown format: {fmt}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    if output is None:
        typer.echo(text.rstrip("\n"))


@app.command("check")
def check_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    max_missed_loop_vectorize: Annotated[
        int | None,
        typer.Option("--max-missed-loop-vectorize", help="Fail if exceeded."),
    ] = None,
    max_missed_inline: Annotated[
        int | None,
        typer.Option("--max-missed-inline", help="Fail if exceeded."),
    ] = None,
    max_pass_remarks: Annotated[
        int | None,
        typer.Option("--max-pass-remarks", help="With --pass-name-exact, cap total remarks."),
    ] = None,
    pass_name_exact: Annotated[
        str | None,
        typer.Option("--pass-name-exact", help="Exact pass field for --max-pass-remarks."),
    ] = None,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Exit non-zero when configured thresholds are violated."""

    if max_pass_remarks is not None and not pass_name_exact:
        typer.secho("--max-pass-remarks requires --pass-name-exact", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target, toolchain=toolchain)
    result = run_checks(
        records,
        max_missed_loop_vectorize=max_missed_loop_vectorize,
        max_missed_inline=max_missed_inline,
        max_pass_remarks=max_pass_remarks,
        pass_name_exact=pass_name_exact,
    )
    if result.ok:
        typer.echo("check OK")
        raise typer.Exit(0)
    for line in result.violations:
        typer.secho(line, fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _check_options_active(
    max_missed_loop_vectorize: int | None,
    max_missed_inline: int | None,
    max_missed_vectorize: int | None = None,
    max_missed_unroll: int | None = None,
    max_total_missed: int | None = None,
    max_analysis: int | None = None,
    max_pass_remarks: int | None = None,
    pass_name_exact: str | None = None,
) -> bool:
    return policy_thresholds_active(
        max_missed_loop_vectorize=max_missed_loop_vectorize,
        max_missed_inline=max_missed_inline,
        max_missed_vectorize=max_missed_vectorize,
        max_missed_unroll=max_missed_unroll,
        max_total_missed=max_total_missed,
        max_analysis=max_analysis,
        max_pass_remarks=max_pass_remarks,
        pass_name_exact=pass_name_exact,
    )


def _policy_kwargs(
    *,
    max_missed_loop_vectorize: int | None,
    max_missed_inline: int | None,
    max_missed_vectorize: int | None,
    max_missed_unroll: int | None,
    max_total_missed: int | None,
    max_analysis: int | None,
    max_pass_remarks: int | None,
    pass_name_exact: str | None,
) -> dict[str, int | str | None]:
    return {
        "max_missed_loop_vectorize": max_missed_loop_vectorize,
        "max_missed_inline": max_missed_inline,
        "max_missed_vectorize": max_missed_vectorize,
        "max_missed_unroll": max_missed_unroll,
        "max_total_missed": max_total_missed,
        "max_analysis": max_analysis,
        "max_pass_remarks": max_pass_remarks,
        "pass_name_exact": pass_name_exact,
    }


def _run_local_report(
    target: Path,
    *,
    report_format: str,
    title: str,
    top_missed: int,
    include_passed: bool,
    policy_kw: dict[str, int | str | None],
    output: Path | None,
    fail_on_check: bool,
) -> None:
    """Render the offline local-intelligence report (markdown/json/github)."""

    from explncc.local.report import build_local_report, render_local_report

    fmt = report_format.strip().lower()
    if fmt == "github":
        fmt = "markdown"
    if fmt == "html":
        typer.secho(
            "--local report supports markdown and json (use --format markdown).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)
    if fmt not in {"markdown", "json"}:
        typer.secho(f"unknown --format {report_format!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target)
    policy = (
        build_policy_result(records, **policy_kw)
        if _check_options_active(**policy_kw)
        else None
    )
    policy_dict = policy.to_dict() if policy is not None else None

    report = build_local_report(
        records,
        title=title,
        top=top_missed,
        include_passed=include_passed,
        policy=policy_dict,
    )
    text = render_local_report(report, fmt)
    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote local report to {output}")
    else:
        typer.echo(text)

    if fail_on_check and policy is not None and not policy.ok:
        raise typer.Exit(1)


@app.command("report")
def report_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
    report_format: Annotated[
        str,
        typer.Option("--format", help="markdown | json | github | html."),
    ] = "markdown",
    local: Annotated[
        bool,
        typer.Option(
            "--local",
            help="Offline local report (classifier + ranker + templates). No network.",
        ),
    ] = False,
    offline: Annotated[
        bool,
        typer.Option("--offline", help="Alias for --local that also forbids network backends."),
    ] = False,
    no_network: Annotated[
        bool,
        typer.Option("--no-network", help="Guardrail: forbid any network/model backend call."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write report to this file; default stdout."),
    ] = None,
    title: Annotated[
        str,
        typer.Option("--title", help="Report heading (Markdown / GitHub title)."),
    ] = "Compiler Optimization Report",
    top_missed: Annotated[int, typer.Option("--top-missed", help="Rows in the missed table.")] = 12,
    top_analysis: Annotated[int, typer.Option("--top-analysis", help="Analysis rows in JSON report.")] = 8,
    include_passed: Annotated[
        bool,
        typer.Option("--include-passed", help="Include top passed remarks in JSON/Markdown."),
    ] = False,
    max_message_length: Annotated[
        int,
        typer.Option("--max-message-length", help="Truncate compiler messages in Markdown."),
    ] = 4000,
    no_explain: Annotated[
        bool,
        typer.Option("--no-explain/--explain", help="Skip explanation (default for CI)."),
    ] = True,
    explain_backend: Annotated[
        str | None,
        typer.Option(
            "--explain-backend",
            help="rule | ollama | openai | claude | auto (default from env).",
        ),
    ] = None,
    explain_limit: Annotated[
        int,
        typer.Option("--explain-limit", help="Max remarks passed to explainer."),
    ] = 32,
    explain_only_on_failure: Annotated[
        bool,
        typer.Option("--explain-only-on-failure", help="Explain only when policy fails."),
    ] = False,
    explain_only_on_regression: Annotated[
        bool,
        typer.Option(
            "--explain-only-on-regression",
            help="With report-diff workflows: skip explanation unless regressions exist (no-op on report alone).",
        ),
    ] = False,
    strict_explain: Annotated[
        bool,
        typer.Option("--strict-explain", help="Fail report if explanation backend errors."),
    ] = False,
    ai_limit: Annotated[
        int,
        typer.Option("--ai-limit", help="Max records serialized for model backends."),
    ] = 40,
    github_collapsible: Annotated[
        bool,
        typer.Option(
            "--github-collapsible/--no-github-collapsible",
            help="Use collapsible sections in GitHub format.",
        ),
    ] = True,
    fail_on_check: Annotated[
        bool,
        typer.Option(
            "--fail-on-check",
            help="Exit 1 when policy checks fail (requires threshold flags).",
        ),
    ] = False,
    max_missed_loop_vectorize: Annotated[
        int | None,
        typer.Option("--max-missed-loop-vectorize", help="Include in report + optional gate."),
    ] = None,
    max_missed_inline: Annotated[
        int | None,
        typer.Option("--max-missed-inline", help="Include in report + optional gate."),
    ] = None,
    max_missed_vectorize: Annotated[
        int | None,
        typer.Option("--max-missed-vectorize", help="Cap missed vectorization-related passes."),
    ] = None,
    max_missed_unroll: Annotated[
        int | None,
        typer.Option("--max-missed-unroll", help="Cap missed unroll remarks."),
    ] = None,
    max_total_missed: Annotated[
        int | None,
        typer.Option("--max-total-missed", help="Cap total missed remarks."),
    ] = None,
    max_analysis: Annotated[
        int | None,
        typer.Option("--max-analysis", help="Cap analysis remark count."),
    ] = None,
    max_pass_remarks: Annotated[
        int | None,
        typer.Option("--max-pass-remarks", help="With --pass-name-exact."),
    ] = None,
    pass_name_exact: Annotated[
        str | None,
        typer.Option("--pass-name-exact", help="Exact pass field for remark cap."),
    ] = None,
    git_sha: Annotated[str | None, typer.Option("--git-sha", help="Git commit SHA for metadata.")] = None,
    branch: Annotated[str | None, typer.Option("--branch", help="Git branch for metadata.")] = None,
    pr_number: Annotated[str | None, typer.Option("--pr-number", help="Pull request number.")] = None,
    build_id: Annotated[str | None, typer.Option("--build-id", help="CI build identifier.")] = None,
    ci_provider: Annotated[
        str | None,
        typer.Option("--ci-provider", help="CI provider name (github, jenkins, …)."),
    ] = None,
    repo: Annotated[str | None, typer.Option("--repo", help="Repository slug for metadata.")] = None,
    target_name: Annotated[
        str | None,
        typer.Option("--target-name", help="Build target label (overrides triple in metadata)."),
    ] = None,
    manifest_out: Annotated[
        Path | None,
        typer.Option("--write-manifest", help="Write CI artifact manifest JSON."),
    ] = None,
    embed_json: Annotated[
        bool,
        typer.Option("--embed-json", help="Embed JSON metadata in HTML reports."),
    ] = False,
) -> None:
    """Emit Markdown, JSON, HTML, or GitHub PR-style reports for CI and review bots."""

    if max_pass_remarks is not None and not pass_name_exact:
        typer.secho("--max-pass-remarks requires --pass-name-exact", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    config = load_config()
    backend_explicit = explain_backend is not None
    use_local = local or offline or (
        backend_explicit and (explain_backend or "").strip().lower() == "local"
    )
    _enforce_offline_guardrails(
        backend=explain_backend,
        backend_explicit=backend_explicit,
        offline=offline,
        no_network=no_network,
        use_local=use_local,
        config_no_network=config.no_network,
    )

    policy_kw = _policy_kwargs(
        max_missed_loop_vectorize=max_missed_loop_vectorize,
        max_missed_inline=max_missed_inline,
        max_missed_vectorize=max_missed_vectorize,
        max_missed_unroll=max_missed_unroll,
        max_total_missed=max_total_missed,
        max_analysis=max_analysis,
        max_pass_remarks=max_pass_remarks,
        pass_name_exact=pass_name_exact,
    )

    if use_local:
        _run_local_report(
            target,
            report_format=report_format,
            title=title,
            top_missed=top_missed,
            include_passed=include_passed,
            policy_kw=policy_kw,
            output=output,
            fail_on_check=fail_on_check,
        )
        return

    if fail_on_check and not _check_options_active(**policy_kw):
        typer.secho(
            "--fail-on-check requires at least one policy threshold flag.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    records = _load_records_or_exit(target, toolchain=toolchain)
    source = report_source_info(target, records, toolchain=toolchain)
    metadata = ReportMetadata(
        git_sha=git_sha,
        branch=branch,
        pr_number=pr_number,
        build_id=build_id,
        ci_provider=ci_provider,
        repo=repo,
        target_name=target_name,
    )
    options = ReportBuildOptions(
        title=title,
        top_missed=top_missed,
        top_analysis=top_analysis,
        include_passed=include_passed,
        message_max_chars=max_message_length,
        github_collapsible=github_collapsible,
        explain_backend=explain_backend,
    )

    policy = build_policy_result(records, **policy_kw) if _check_options_active(**policy_kw) else None

    explanation, explain_exit = resolve_explanation(
        records,
        enabled=not no_explain,
        backend=explain_backend,
        config=config,
        explain_limit=explain_limit,
        ai_limit=ai_limit,
        only_on_failure=explain_only_on_failure,
        policy=policy,
        strict=strict_explain,
    )
    if explain_exit is not None:
        raise typer.Exit(explain_exit)

    try:
        report_fmt = parse_report_format(report_format)
    except ValueError:
        typer.secho(f"unknown --format {report_format!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from None

    text = render_report(
        report_fmt,
        records,
        source=source,
        metadata=metadata,
        options=options,
        policy=policy,
        explanation=explanation,
        embed_json=embed_json,
    )

    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote report to {output}")
    else:
        typer.echo(text)

    if manifest_out is not None:
        from explncc.utils import collect_opt_yaml_paths

        manifest = CiManifest(
            git_sha=git_sha,
            build_id=build_id,
            ci_provider=ci_provider,
            raw_opt_yaml=[str(p) for p in collect_opt_yaml_paths(target)],
        )
        if report_fmt == "markdown":
            manifest.markdown_report = str(output) if output else None
        elif report_fmt == "json":
            manifest.json_report = str(output) if output else None
        elif report_fmt == "github":
            manifest.github_comment = str(output) if output else None
        if policy is not None and output is not None:
            manifest.policy_report = str(output)
        manifest.manifest_path = str(manifest_out)
        write_manifest(str(manifest_out), manifest)
        typer.echo(f"wrote manifest to {manifest_out}")

    if fail_on_check and policy is not None and not policy.ok:
        raise typer.Exit(1)


@app.command("report-diff")
def report_diff_cmd(
    before: Annotated[Path, typer.Argument(help="Baseline .opt.yaml file or directory")],
    after: Annotated[Path, typer.Argument(help="Current .opt.yaml file or directory")],
    report_format: Annotated[
        str,
        typer.Option("--format", help="markdown | json | github."),
    ] = "markdown",
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write diff report to this file."),
    ] = None,
    before_label: Annotated[str, typer.Option("--before-label", help="Label for baseline.")] = "before",
    after_label: Annotated[str, typer.Option("--after-label", help="Label for current build.")] = "after",
    top_changes: Annotated[int, typer.Option("--top-changes", help="Max changes in output.")] = 15,
    only_regressions: Annotated[
        bool,
        typer.Option("--only-regressions", help="Show regression-classified changes only."),
    ] = False,
    include_improvements: Annotated[
        bool,
        typer.Option("--include-improvements/--no-include-improvements", help="Include improvements."),
    ] = True,
    fail_on_regression: Annotated[
        bool,
        typer.Option("--fail-on-regression", help="Exit 1 when any regression-classified change exists."),
    ] = False,
    fail_on_vectorization_loss: Annotated[
        bool,
        typer.Option(
            "--fail-on-vectorization-loss",
            help="Exit 1 when vectorization is lost or new missed vectorize remarks appear.",
        ),
    ] = False,
    manifest_out: Annotated[
        Path | None,
        typer.Option("--write-manifest", help="Write CI artifact manifest JSON."),
    ] = None,
    toolchain: Annotated[
        str,
        typer.Option("--toolchain", help="Toolchain adapter: clang (default) or hls."),
    ] = "clang",
) -> None:
    """Semantic diff of compiler optimization behavior across two builds."""

    if report_format.strip().lower() == "html":
        typer.secho("report-diff supports markdown, json, and github formats.", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    b_records = _load_records_or_exit(before, toolchain=toolchain)
    a_records = _load_records_or_exit(after, toolchain=toolchain)
    diff_result = build_report_diff(
        b_records,
        a_records,
        before_label=before_label,
        after_label=after_label,
        only_regressions=only_regressions,
        include_improvements=include_improvements,
    )
    fmt = report_format.strip().lower()
    if fmt not in {"markdown", "json", "github"}:
        typer.secho(f"unknown --format {report_format!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    text = render_report_diff(fmt, diff_result, top_changes=top_changes)
    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote diff report to {output}")
    else:
        typer.echo(text)

    if manifest_out is not None:
        manifest = CiManifest(diff_report=str(output) if output else None)
        manifest.manifest_path = str(manifest_out)
        write_manifest(str(manifest_out), manifest)
        typer.echo(f"wrote manifest to {manifest_out}")

    regressions = [c for c in diff_result.changes if c.classification == "regression"]
    vector_loss = [
        c
        for c in diff_result.changes
        if c.change_type in {"vectorization_lost", "new_missed"}
        and ("vector" in c.description.lower() or "vectorize" in c.description.lower())
    ]
    if fail_on_regression and regressions:
        raise typer.Exit(1)
    if fail_on_vectorization_loss and vector_loss:
        raise typer.Exit(1)


@app.command("ci-manifest")
def ci_manifest_cmd(
    manifest_path: Annotated[Path, typer.Argument(help="Path to write manifest JSON")],
    raw_opt_yaml: Annotated[
        list[str],
        typer.Option("--raw-opt-yaml", help="Path to raw .opt.yaml (repeatable)."),
    ] = [],
    markdown_report: Annotated[str | None, typer.Option("--markdown-report")] = None,
    json_report: Annotated[str | None, typer.Option("--json-report")] = None,
    github_comment: Annotated[str | None, typer.Option("--github-comment")] = None,
    diff_report: Annotated[str | None, typer.Option("--diff-report")] = None,
    policy_report: Annotated[str | None, typer.Option("--policy-report")] = None,
    git_sha: Annotated[str | None, typer.Option("--git-sha")] = None,
    build_id: Annotated[str | None, typer.Option("--build-id")] = None,
    ci_provider: Annotated[str | None, typer.Option("--ci-provider")] = None,
) -> None:
    """Write a CI artifact manifest describing generated report files."""

    manifest = CiManifest(
        git_sha=git_sha,
        build_id=build_id,
        ci_provider=ci_provider,
        raw_opt_yaml=list(raw_opt_yaml),
        markdown_report=markdown_report,
        json_report=json_report,
        github_comment=github_comment,
        diff_report=diff_report,
        policy_report=policy_report,
        manifest_path=str(manifest_path),
    )
    write_manifest(str(manifest_path), manifest)
    typer.echo(f"wrote manifest to {manifest_path}")


@app.command("alignment")
def alignment_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    limit: Annotated[int, typer.Option("--limit", help="Max rows after filter.")] = 0,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Emit JSON with alignment_signals."),
    ] = False,
) -> None:
    """List remarks that look SIMD / vectorization / alignment-relevant (heuristic slice)."""

    records = _load_records_or_exit(target)
    filtered = filter_alignment_related(records)
    if limit > 0:
        filtered = filtered[:limit]

    if as_json:
        payload: list[dict[str, Any]] = []
        for r in filtered:
            row = record_to_json_dict(r)
            row["alignment_signals"] = alignment_signals(r)
            row.update(classify_alignment(r).to_dict())
            payload.append(row)
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    rows_out: list[list[str]] = []
    for r in filtered:
        loc = ""
        if r.file:
            loc = r.file
            if r.line is not None:
                loc += f":{r.line}"
        classification = classify_alignment(r)
        rows_out.append(
            [
                r.kind or "",
                r.pass_name or "",
                r.remark_name or "",
                r.function or "",
                loc,
                classification.alignment_label,
                classification.alignment_confidence,
                ";".join(alignment_signals(r)),
                truncate_message(r.message, 100),
            ],
        )
    print_table(
        stdout_console,
        (
            "kind",
            "pass",
            "remark",
            "function",
            "location",
            "label",
            "conf",
            "signals",
            "message",
        ),
        rows_out,
        title=f"alignment slice ({len(filtered)} remarks, heuristic)",
    )


@app.command("alignment-pack")
def alignment_pack_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    pack_format: Annotated[
        str,
        typer.Option("--format", help="json | jsonl | markdown"),
    ] = "json",
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write to this file; default stdout."),
    ] = None,
    include_source: Annotated[
        bool,
        typer.Option(
            "--include-source",
            help="Attach a source window around DebugLoc (requires snippet support).",
        ),
    ] = False,
    source_root: Annotated[
        Path | None,
        typer.Option(
            "--source-root",
            help="Project root for resolving relative DebugLoc paths (with --include-source).",
        ),
    ] = None,
    context_before: Annotated[
        int,
        typer.Option(
            "--context-before",
            help="Lines before the remark line (with --include-source).",
        ),
    ] = 5,
    context_after: Annotated[
        int,
        typer.Option(
            "--context-after",
            help="Lines after the remark line (with --include-source).",
        ),
    ] = 8,
    include_ir: Annotated[
        bool,
        typer.Option("--include-ir", help="Attach a bounded LLVM IR slice (requires IR support)."),
    ] = False,
    ir_file: Annotated[
        Path | None,
        typer.Option("--ir-file", help="IR file to slice (with --include-ir)."),
    ] = None,
    ir_lines: Annotated[
        int,
        typer.Option("--ir-lines", help="Approximate max IR lines in the snippet."),
    ] = 50,
    include_asm: Annotated[
        bool,
        typer.Option(
            "--include-asm",
            help="Attach a bounded assembly slice (requires assembly support).",
        ),
    ] = False,
    asm_file: Annotated[
        Path | None,
        typer.Option("--asm-file", help="Assembly file to slice (with --include-asm)."),
    ] = None,
    asm_lines: Annotated[
        int,
        typer.Option("--asm-lines", help="Approximate max assembly lines in the snippet."),
    ] = 60,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max alignment evidence packs after filtering."),
    ] = 0,
    label: Annotated[
        str | None,
        typer.Option(
            "--label",
            help=(
                "Keep only packs with this alignment_label: alignment_explicit, "
                "alignment_plausible_not_proven, alignment_unlikely_from_evidence, "
                "insufficient_evidence, not_alignment_related."
            ),
        ),
    ] = None,
) -> None:
    """Emit alignment-focused evidence packs (deterministic JSON / JSONL / Markdown)."""

    if include_source and source_root is None:
        typer.secho("--include-source requires --source-root", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if include_ir and ir_file is None:
        typer.secho("--include-ir requires --ir-file", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if include_asm and asm_file is None:
        typer.secho("--include-asm requires --asm-file", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if context_before < 0 or context_after < 0:
        typer.secho(
            "--context-before and --context-after must be non-negative",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)
    if ir_lines < 1:
        typer.secho("--ir-lines must be at least 1", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if asm_lines < 1:
        typer.secho("--asm-lines must be at least 1", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if label is not None and label not in ALIGNMENT_LABELS:
        typer.secho(
            f"unknown --label {label!r}; expected one of: {', '.join(sorted(ALIGNMENT_LABELS))}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    records = _load_records_or_exit(target)
    records = filter_alignment_related(records)
    if limit > 0:
        records = records[:limit]

    label_filter: AlignmentLabel | None = cast(AlignmentLabel, label) if label else None
    context = _context_snippet_request(
        include_source=include_source,
        source_root=source_root,
        context_before=context_before,
        context_after=context_after,
        include_ir=include_ir,
        ir_file=ir_file,
        ir_lines=ir_lines,
        include_asm=include_asm,
        asm_file=asm_file,
        asm_lines=asm_lines,
    )
    packs = build_alignment_evidence_packs(records, label=label_filter, context=context)
    try:
        text = render_alignment_evidence_packs(packs, pack_format)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc

    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {len(packs)} alignment evidence pack(s) to {output}")
    else:
        typer.echo(text.rstrip("\n"))


@app.command("dataset")
def dataset_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    output: Annotated[Path, typer.Option("-o", "--output", help="JSONL output path.")],
    focus: Annotated[
        str,
        typer.Option("--focus", help="alignment: SIMD slice only; all: every remark."),
    ] = "alignment",
    template: Annotated[
        str,
        typer.Option("--template", help="Prompt template: minimal | guided | rubric."),
    ] = "guided",
    export_format: Annotated[
        str,
        typer.Option(
            "--format",
            help=(
                "openai-messages | explncc-record | legacy-prompt-completion | "
                "plain-prompt-completion | chatml"
            ),
        ),
    ] = "explncc-record",
    teacher: Annotated[
        bool,
        typer.Option("--teacher/--no-teacher", help="Rule-based target text."),
    ] = True,
    placeholder: Annotated[
        str,
        typer.Option("--placeholder", help="Assistant field when --no-teacher."),
    ] = "[HUMAN_LABEL_REQUIRED]",
    limit: Annotated[int, typer.Option("--limit", help="Cap rows after focus filter.")] = 0,
    include_args_raw: Annotated[
        bool,
        typer.Option("--include-args-raw", help="Keep bulky args_raw in JSON (larger prompts)."),
    ] = False,
    include_source: Annotated[
        bool,
        typer.Option("--include-source", help="Attach source snippet into dataset rows."),
    ] = False,
    source_root: Annotated[
        Path | None,
        typer.Option("--source-root", help="Root for DebugLoc paths (with --include-source)."),
    ] = None,
    context_before: Annotated[int, typer.Option("--context-before")] = 5,
    context_after: Annotated[int, typer.Option("--context-after")] = 8,
    include_ir: Annotated[bool, typer.Option("--include-ir")] = False,
    ir_file: Annotated[Path | None, typer.Option("--ir-file")] = None,
    ir_lines: Annotated[int, typer.Option("--ir-lines")] = 50,
    include_asm: Annotated[bool, typer.Option("--include-asm")] = False,
    asm_file: Annotated[Path | None, typer.Option("--asm-file")] = None,
    asm_lines: Annotated[int, typer.Option("--asm-lines")] = 60,
) -> None:
    """Emit JSONL rows for LLM fine-tuning / instruction datasets."""

    if include_source and source_root is None:
        typer.secho("--include-source requires --source-root", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if include_ir and ir_file is None:
        typer.secho("--include-ir requires --ir-file", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if include_asm and asm_file is None:
        typer.secho("--include-asm requires --asm-file", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target)
    focus_l = focus.strip().lower()
    if focus_l == "alignment":
        records = filter_alignment_related(records)
    elif focus_l != "all":
        typer.secho("--focus must be alignment or all", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    if limit > 0:
        records = records[:limit]
    if not records:
        typer.secho("no records after filter", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    fmt_l = export_format.strip().lower()
    if focus_l == "alignment":
        if fmt_l not in ALIGNMENT_EXPORT_FORMATS:
            typer.secho(f"unknown --format {export_format!r}", fg=typer.colors.RED, err=True)
            raise typer.Exit(2)
        context = _context_snippet_request(
            include_source=include_source,
            source_root=source_root,
            context_before=context_before,
            context_after=context_after,
            include_ir=include_ir,
            ir_file=ir_file,
            ir_lines=ir_lines,
            include_asm=include_asm,
            asm_file=asm_file,
            asm_lines=asm_lines,
        )
        try:
            export_fmt = cast(AlignmentExportFormat, fmt_l)
            rows = build_alignment_training_rows(
                records,
                template_id=template,
                export_format=export_fmt,
                use_teacher=teacher,
                teacher_placeholder=placeholder,
                include_args_raw=include_args_raw,
                context=context,
            )
        except KeyError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(2) from exc
    else:
        allowed: dict[str, ExportFormat] = {
            "openai-messages": "openai-messages",
            "explncc-record": "explncc-record",
            "legacy-prompt-completion": "legacy-prompt-completion",
        }
        if fmt_l not in allowed:
            typer.secho(f"unknown --format {export_format!r}", fg=typer.colors.RED, err=True)
            raise typer.Exit(2)
        export_fmt: ExportFormat = allowed[fmt_l]
        try:
            rows = build_training_rows(
                records,
                template_id=template,
                export_format=export_fmt,
                use_teacher=teacher,
                teacher_placeholder=placeholder,
                include_args_raw=include_args_raw,
            )
        except KeyError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(2) from exc

    write_jsonl(output, rows)
    typer.echo(f"wrote {len(rows)} JSONL records to {output}")


@app.command("bench-prompts")
def bench_prompts_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write JSONL; default stdout."),
    ] = None,
    focus: Annotated[
        str,
        typer.Option("--focus", help="alignment | all"),
    ] = "alignment",
    templates: Annotated[
        str | None,
        typer.Option(
            "--templates",
            help="Comma-separated template ids (alignment: minimal,guided,rubric,adversarial,missing-context).",
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max records after focus filter.")] = 0,
    include_args_raw: Annotated[
        bool,
        typer.Option("--include-args-raw", help="Include args_raw in embedded JSON."),
    ] = False,
) -> None:
    """Emit record × prompt-variant lines for comparing models or prompt designs offline."""

    records = _load_records_or_exit(target)
    focus_l = focus.strip().lower()
    if focus_l == "alignment":
        records = filter_alignment_related(records)
    elif focus_l != "all":
        typer.secho("--focus must be alignment or all", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if limit > 0:
        records = records[:limit]

    t_ids = [x.strip() for x in templates.split(",") if x.strip()] if templates else None
    try:
        if focus_l == "alignment":
            lines = build_alignment_bench_prompt_lines(
                records,
                template_ids=t_ids,
                include_args_raw=include_args_raw,
            )
        else:
            lines = build_bench_prompt_lines(
                records,
                template_ids=t_ids,
                include_args_raw=include_args_raw,
            )
    except KeyError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc

    text = "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
    if output is not None:
        output.write_text(text + "\n", encoding="utf-8")
        typer.echo(f"wrote {len(lines)} bench lines to {output}")
    else:
        typer.echo(text)


@app.command("eval-alignment")
def eval_alignment_cmd(
    predictions: Annotated[
        Path,
        typer.Argument(help="JSONL file with model outputs and expected labels."),
    ],
    eval_format: Annotated[
        str,
        typer.Option("--format", help="json | markdown"),
    ] = "json",
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Write report to this file; default stdout."),
    ] = None,
) -> None:
    """Score alignment model outputs heuristically (no LLM judge)."""

    fmt_l = eval_format.strip().lower()
    if fmt_l not in {"json", "markdown"}:
        typer.secho("--format must be json or markdown", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if not predictions.is_file():
        typer.secho(f"file not found: {predictions}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    try:
        rows = load_predictions_jsonl(predictions)
    except (ValueError, TypeError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    if not rows:
        typer.secho("no prediction rows found", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    report = evaluate_predictions(rows)
    try:
        text = render_eval_report(report, fmt_l)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote eval report for {len(report.samples)} sample(s) to {output}")
    else:
        typer.echo(text.rstrip("\n"))


def main() -> None:
    """Invoke the Typer application (used by setuptools entry point)."""
    app()


if __name__ == "__main__":
    main()
