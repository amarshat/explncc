"""Command-line entry point for explncc."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from explncc import __version__
from explncc.alignment import alignment_signals, filter_alignment_related
from explncc.checks import CheckResult, run_checks
from explncc.ci_report import parse_report_format, render_report
from explncc.config import doctor_payload, load_config
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
    if include_source or include_ir:
        typer.secho(
            "note: --include-source / --include-ir / --ir-file are not implemented yet; "
            "snippets are omitted (Chapter 10 milestone 3).",
            fg=typer.colors.YELLOW,
            err=True,
        )
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

    # source_root, context_before, context_after, ir_lines: reserved for milestone 3 snippets.

    records = _load_records_or_exit(target)
    records = apply_filters(
        records,
        pass_contains=pass_contains,
        function_contains=function_contains,
        kind=kind,
    )
    if limit > 0:
        records = records[:limit]

    packs = build_evidence_packs(records)
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
    max_pass_remarks: int | None,
    pass_name_exact: str | None,
) -> bool:
    return (
        max_missed_loop_vectorize is not None
        or max_missed_inline is not None
        or (max_pass_remarks is not None and pass_name_exact is not None)
    )


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
    ] = "Optimization remarks report",
    top_missed: Annotated[int, typer.Option("--top-missed", help="Rows in the missed table.")] = 12,
    no_explain: Annotated[
        bool,
        typer.Option("--no-explain", help="Skip explanation block (faster CI)."),
    ] = False,
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
    ai_limit: Annotated[
        int,
        typer.Option("--ai-limit", help="Max records serialized for model backends."),
    ] = 40,
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
    max_pass_remarks: Annotated[
        int | None,
        typer.Option("--max-pass-remarks", help="With --pass-name-exact."),
    ] = None,
    pass_name_exact: Annotated[
        str | None,
        typer.Option("--pass-name-exact", help="Exact pass field for remark cap."),
    ] = None,
) -> None:
    """Emit Markdown, JSON, HTML, or GitHub PR-style reports for CI and review bots."""

    if max_pass_remarks is not None and not pass_name_exact:
        typer.secho("--max-pass-remarks requires --pass-name-exact", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    if fail_on_check and not _check_options_active(
        max_missed_loop_vectorize,
        max_missed_inline,
        max_pass_remarks,
        pass_name_exact,
    ):
        typer.secho(
            "--fail-on-check requires at least one threshold: "
            "--max-missed-inline, --max-missed-loop-vectorize, or "
            "--max-pass-remarks with --pass-name-exact",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    records = _load_records_or_exit(target)

    check_result: CheckResult | None = None
    if _check_options_active(
        max_missed_loop_vectorize,
        max_missed_inline,
        max_pass_remarks,
        pass_name_exact,
    ):
        check_result = run_checks(
            records,
            max_missed_loop_vectorize=max_missed_loop_vectorize,
            max_missed_inline=max_missed_inline,
            max_pass_remarks=max_pass_remarks,
            pass_name_exact=pass_name_exact,
        )

    explain_text: str | None = None
    if not no_explain:
        config = load_config()
        mode = (explain_backend or config.default_backend).strip().lower()
        if mode == "openai" and not config.openai_api_key:
            typer.secho("openai backend requires OPENAI_API_KEY", fg=typer.colors.RED, err=True)
            raise typer.Exit(2)
        if mode == "claude" and not config.anthropic_api_key:
            typer.secho("claude backend requires ANTHROPIC_API_KEY", fg=typer.colors.RED, err=True)
            raise typer.Exit(2)
        subset = records[:explain_limit] if explain_limit > 0 else records
        explain_text = run_explanation(subset, backend=mode, config=config, ai_limit=ai_limit)

    try:
        report_fmt = parse_report_format(report_format)
    except ValueError:
        typer.secho(f"unknown --format {report_format!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from None

    text = render_report(
        report_fmt,
        records,
        top_missed=top_missed,
        check_result=check_result,
        explain_text=explain_text,
        title=title,
    )

    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote report to {output}")
    else:
        typer.echo(text)

    if fail_on_check and check_result is not None and not check_result.ok:
        raise typer.Exit(1)


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
        rows_out.append(
            [
                r.kind or "",
                r.pass_name or "",
                r.remark_name or "",
                r.function or "",
                loc,
                ";".join(alignment_signals(r)),
                truncate_message(r.message, 100),
            ],
        )
    print_table(
        stdout_console,
        ("kind", "pass", "remark", "function", "location", "signals", "message"),
        rows_out,
        title=f"alignment slice ({len(filtered)} remarks, heuristic)",
    )


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
            help="openai-messages | explncc-record | legacy-prompt-completion",
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
) -> None:
    """Emit JSONL rows for LLM fine-tuning / instruction datasets (Chapter 11 workflows)."""

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
            help="Comma-separated template ids (default: all Chapter 11 templates).",
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


def main() -> None:
    """Invoke the Typer application (used by setuptools entry point)."""
    app()


if __name__ == "__main__":
    main()
