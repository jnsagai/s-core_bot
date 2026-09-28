"""`score-assistant eval retrieval | exact-ids | latency` (specs/004-hybrid-search/contracts).

Reports are written to `data/reports/`. Results from unreviewed case files are labelled
development measurements, never release evidence.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel

from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.cli.search import _config, build_service, handle_search_errors
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.retrieval.evaluation import (
    evaluate_retrieval,
    exact_id_suite,
    load_case_file,
    measure_latency,
)

eval_app = typer.Typer(add_completion=False, help="Measure retrieval quality and speed.")
cli_app.add_typer(eval_app, name="eval")

CasesOption = Annotated[Path, typer.Option("--cases", help="Case file (YAML).")]
SnapshotOption = Annotated[
    str | None, typer.Option("--snapshot", help="Snapshot ID (default: active).")
]


def _write_report(config: AppConfig, kind: str, report: BaseModel, output: Path | None) -> Path:
    snapshot = str(getattr(report, "snapshot_id", "unknown"))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output or config.data_dir / "reports" / f"{kind}-{snapshot}-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n")
    return path


@eval_app.command("retrieval")
@handle_common_errors
@handle_search_errors
def retrieval_command(
    ctx: typer.Context,
    cases: CasesOption,
    snapshot: SnapshotOption = None,
    lexical: Annotated[bool, typer.Option("--lexical", help="Keyword-only mode.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
    output: Annotated[Path | None, typer.Option("--output", help="Report file path.")] = None,
) -> None:
    """Measures retrieval recall@10 against a case file; may use the local embedding runtime."""
    config = _config(ctx)
    case_file, sha = load_case_file(cases)
    report = evaluate_retrieval(
        build_service(config, embeddings=not lexical),
        case_file,
        sha,
        snapshot_id=snapshot,
        force_lexical=lexical,
    )
    path = _write_report(config, "retrieval", report, output)
    if json_output:
        typer.echo(report.model_dump_json())
        return
    label = f" [{', '.join(report.labels)}]" if report.labels else ""
    typer.echo(
        f"snapshot {report.snapshot_id}  mode {report.mode}  review: {report.review_status}{label}"
    )
    for warning in report.warnings:
        typer.echo(f"warning: {warning}")
    for category, summary in report.by_category.items():
        typer.echo(
            f"  {category:<26} recall@10 {summary.recall_at_10:6.1%}  ({summary.cases} cases)"
        )
    typer.echo(
        f"  {'overall (macro)':<26} recall@10 {report.macro_recall_at_10:6.1%}  "
        f"({len(report.cases)} cases)"
    )
    missed = [c for c in report.cases if c.recall_at_10 < 1.0]
    for case in missed:
        typer.echo(f"  missed group(s): {case.id}  ranks {case.group_ranks}")
    typer.echo(f"report: {path}")


@eval_app.command("exact-ids")
@handle_common_errors
@handle_search_errors
def exact_ids_command(
    ctx: typer.Context,
    snapshot: SnapshotOption = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Checks that every requirement ID in a snapshot is found first by exact lookup. Offline."""
    config = _config(ctx)
    report = exact_id_suite(build_service(config, embeddings=False), snapshot_id=snapshot)
    path = _write_report(config, "exact-ids", report, None)
    if json_output:
        typer.echo(report.model_dump_json())
    else:
        typer.echo(
            f"snapshot {report.snapshot_id}: {report.correct_first}/{report.ids_checked} IDs "
            "return the expected entity first"
        )
        for failure in report.failures[:50]:
            typer.echo(f"  FAIL {failure.need_id}: expected {failure.expected}, got {failure.got}")
        if report.ambiguous_by_design:
            typer.echo(f"  duplicates within one source: {len(report.ambiguous_by_design)}")
        typer.echo(f"report: {path}")
    raise typer.Exit(code=0 if not report.failures else 1)


@eval_app.command("latency")
@handle_common_errors
@handle_search_errors
def latency_command(
    ctx: typer.Context,
    cases: CasesOption = Path("eval/retrieval-dev.yaml"),
    snapshot: SnapshotOption = None,
    queries: Annotated[int, typer.Option("--queries", min=10, help="Timed queries per mode.")] = 50,
    json_output: Annotated[bool, typer.Option("--json", help="Print the report as JSON.")] = False,
) -> None:
    """Measures search latency percentiles for keyword-only and hybrid modes; uses the local
    embedding runtime."""
    import platform

    from score_docs_assistant.diagnostics.hardware import probe_hardware
    from score_docs_assistant.models.lock import read_lock

    config = _config(ctx)
    case_file, _ = load_case_file(cases)
    hardware = probe_hardware(config.data_dir)
    lock = read_lock(config.data_dir / "model-lock.json")
    entry = lock.entry_for_role("embedding") if lock else None
    environment = {
        "os": platform.platform(),
        "cpu_count": str(hardware.cpu_count),
        "ram_total_gib": f"{hardware.ram_total_bytes / 1024**3:.1f}",
        "gpu": ", ".join(g.name for g in hardware.gpus) or hardware.gpu_detection,
        "runtime_version": lock.runtime.version if lock else "unknown",
        "embedding_model": entry.tag if entry else "unknown",
        "embedding_digest": entry.digest if entry else "unknown",
    }
    report = measure_latency(
        build_service(config),
        [c.question for c in case_file.cases],
        queries=queries,
        snapshot_id=snapshot,
        environment=environment,
    )
    path = _write_report(config, "latency", report, None)
    if json_output:
        typer.echo(report.model_dump_json())
        return
    typer.echo(f"snapshot {report.snapshot_id}  ({report.measured_in})")
    for mode, result in report.modes.items():
        if result.status == "measured":
            typer.echo(
                f"  {mode:<8} p50 {result.p50_ms:8.1f} ms   p95 {result.p95_ms:8.1f} ms   "
                f"n={result.queries}"
            )
        else:
            typer.echo(f"  {mode:<8} not run ({result.reason})")
    typer.echo("  environment: " + json.dumps(environment, sort_keys=True))
    typer.echo(f"report: {path}")
