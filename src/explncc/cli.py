"""Command-line entry point for explncc."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, cast

from explncc.alignment import AlignmentLabel, alignment_signals, classify_alignment, filter_alignment_related
from explncc.alignment_pack import ALIGNMENT_LABELS, build_alignment_evidence_packs
from explncc.alignment_pack_output import render_alignment_evidence_packs
from explncc.alignment_bench import build_alignment_bench_prompt_lines
from explncc.alignment_eval import evaluate_predictions, load_predictions_jsonl
from explncc.alignment_eval_output import render_eval_report
from explncc.alignment_dataset import (
    ALIGNMENT_EXPORT_FORMATS,
    AlignmentExportFormat,
    build_alignment_training_rows,
)
from explncc.context_snippets import ContextSnippetRequest
from explncc.dataset_llm import (
    ExportFormat,
    build_bench_prompt_lines,
    build_training_rows,
    write_jsonl,
)

import typer
from rich.console import Console

from explncc import __version__
from explncc.checks import CheckResult, build_policy_result, run_checks
from explncc.ci_manifest import CiManifest, write_manifest
from explncc.ci_report import parse_report_format, render_report
from explncc.report_diff import build_report_diff, render_report_diff
from explncc.report_helpers import policy_thresholds_active, report_source_info, resolve_explanation
from explncc.report_types import ReportBuildOptions, ReportMetadata
from explncc.config import doctor_payload, load_config
from explncc.diffing import DiffReport, diff_records
from explncc.digest import build_digest, format_digest_json
from explncc.evidence import build_evidence_packs
from explncc.evidence_output import render_evidence_packs
from explncc.explain.backends import run_explanation
from explncc.exporters import export_csv, export_json, export_jsonl, record_to_json_dict
from explncc.models import OptimizationRecord
from explncc.normalizer import load_records_from_path
from explncc.render import print_table
from explncc.stats import aggregate
from explncc.summary import apply_filters, rows_for_table, truncate_message
from explncc.viz import parse_viz_format, parse_viz_style, render_viz

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
    """Explain Compiler — optimization logs for real-world performance work."""
    if ctx.invoked_subcommand is not None:
        return
    typer.echo(ctx.get_help())


@app.command("version")
def version_cmd() -> None:
    """Print the explncc version string."""
    typer.echo(__version__)


@app.command("doctor")
def doctor_cmd() -> None:
    """Print masked backend-related configuration (safe for CI logs)."""
    typer.echo(json.dumps(doctor_payload(), indent=2, ensure_ascii=False))


@app.command("digest")
def digest_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
) -> None:
    """Emit SHA-256 digests per ``.opt.yaml`` file plus an aggregate cache key."""
    data = build_digest(target)
    typer.echo(format_digest_json(data))


@app.command("viz")
def viz_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
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

    records = _load_records_or_exit(target)
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


def _load_records_or_exit(path: Path) -> list[OptimizationRecord]:
    try:
        return load_records_from_path(path)
    except (FileNotFoundError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc


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
) -> None:
    """Emit Chapter 10 evidence packs (deterministic JSON / JSONL / Markdown)."""

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

    records = _load_records_or_exit(target)
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
) -> None:
    """Print a tabular summary of normalized optimization remarks."""

    if as_json and as_jsonl:
        typer.secho("choose only one of --json or --jsonl", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target)
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
) -> None:
    """Show aggregate counts by pass, kind, function, and reason."""

    records = _load_records_or_exit(target)
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
) -> None:
    """Compare two optimization record sets (CI-friendly missed deltas)."""

    b = _load_records_or_exit(before)
    a = _load_records_or_exit(after)
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
    pass_contains: Annotated[
        str | None,
        typer.Option("--pass", help="Filter pass name substring."),
    ] = None,
    function_contains: Annotated[
        str | None,
        typer.Option("--function", help="Filter function name substring."),
    ] = None,
    kind: Annotated[str | None, typer.Option("--kind", help="Filter remark kind.")] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max records fed to templates / model."),
    ] = 64,
    ai_limit: Annotated[
        int,
        typer.Option("--ai-limit", help="Max records serialized for model backends."),
    ] = 48,
) -> None:
    """Rule-based explanations with optional model augmentation."""

    config = load_config()
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

    records = _load_records_or_exit(target)
    records = apply_filters(
        records,
        pass_contains=pass_contains,
        function_contains=function_contains,
        kind=kind,
    )
    if limit > 0:
        records = records[:limit]

    text = run_explanation(records, backend=mode, config=config, ai_limit=ai_limit)
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
) -> None:
    """Exit non-zero when configured thresholds are violated."""

    if max_pass_remarks is not None and not pass_name_exact:
        typer.secho("--max-pass-remarks requires --pass-name-exact", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    records = _load_records_or_exit(target)
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


@app.command("report")
def report_cmd(
    target: Annotated[Path, typer.Argument(help="File or directory containing .opt.yaml")],
    report_format: Annotated[
        str,
        typer.Option("--format", help="markdown | json | github | html."),
    ] = "markdown",
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
) -> None:
    """Emit Markdown, JSON, HTML, or GitHub PR-style reports for CI and review bots."""

    if max_pass_remarks is not None and not pass_name_exact:
        typer.secho("--max-pass-remarks requires --pass-name-exact", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

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

    if fail_on_check and not _check_options_active(**policy_kw):
        typer.secho(
            "--fail-on-check requires at least one policy threshold flag.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    records = _load_records_or_exit(target)
    source = report_source_info(target, records)
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

    config = load_config()
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
) -> None:
    """Semantic diff of compiler optimization behavior across two builds."""

    if report_format.strip().lower() == "html":
        typer.secho("report-diff supports markdown, json, and github formats.", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    b_records = _load_records_or_exit(before)
    a_records = _load_records_or_exit(after)
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
    """Emit Chapter 11 alignment evidence packs (deterministic JSON / JSONL / Markdown)."""

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
        typer.Option("--template", help="Chapter 11 user template: minimal | guided | rubric."),
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
    """Emit JSONL rows for LLM fine-tuning / instruction datasets (Chapter 11 workflows)."""

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
