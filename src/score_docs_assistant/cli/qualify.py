"""F008 qualification commands (specs/008-quality-qualification/contracts/cli.md).

`eval suite | freeze | review import | adversarial | performance`, `models qualify` and
`release report`. Every command writes its evidence under `data/reports/`; nothing is downloaded
and question or answer text is never logged.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
import yaml

from score_docs_assistant.cli.evaluate import eval_app
from score_docs_assistant.cli.main import handle_common_errors
from score_docs_assistant.cli.search_support import _config, handle_search_errors
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.errors import GenerationError

SUITE_DIR = Path("eval/suite")
review_app = typer.Typer(add_completion=False, help="Human review of suite answers.")
eval_app.add_typer(review_app, name="review")


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def reports_dir(config: AppConfig) -> Path:
    path = config.data_dir / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


@eval_app.command("suite")
@handle_common_errors
@handle_search_errors
def suite_command(
    ctx: typer.Context,
    split: Annotated[str, typer.Option("--split", help="dev or heldout.")] = "dev",
    runs: Annotated[int, typer.Option("--runs", min=1, max=10, help="Repeat the run.")] = 1,
    snapshot: Annotated[str | None, typer.Option("--snapshot", help="Snapshot ID.")] = None,
    suite_dir: Annotated[Path, typer.Option("--suite-dir", help="Suite directory.")] = SUITE_DIR,
) -> None:
    """Runs the evaluation suite (retrieval and answers) and writes reports and review sheets;
    development measurement unless human-reviewed held-out."""
    from score_docs_assistant.cli.ask import build_answer_service
    from score_docs_assistant.qualification.harness import as_json, combine_runs, run_suite
    from score_docs_assistant.qualification.review import build_sheet
    from score_docs_assistant.qualification.suite import freeze_status, load_suite

    if split not in ("dev", "heldout"):
        typer.echo("REQUEST_INVALID: --split must be dev or heldout", err=True)
        raise typer.Exit(code=2)
    path = suite_dir / f"{split}.yaml"
    suite, sha = load_suite(path)
    frozen, freeze_text = freeze_status(path, sha)
    if split == "heldout" and not frozen:
        typer.echo(f"HELDOUT_NOT_FROZEN: {path} {freeze_text}; refusing to run", err=True)
        raise typer.Exit(code=1)
    config = _config(ctx)
    service = build_answer_service(config)
    out = reports_dir(config)
    base = f"suite-{split}-{stamp()}"
    reports, files = [], []
    for run in range(1, runs + 1):
        try:
            report, pairs = asyncio.run(
                run_suite(
                    search=service._search,  # noqa: SLF001
                    answers=service,
                    suite=suite,
                    sha=sha,
                    freeze=freeze_text if split == "heldout" else f"dev ({freeze_text})",
                    run=run,
                    snapshot_id=snapshot,
                )
            )
        except GenerationError as exc:
            typer.echo(f"{exc.code}: {exc.message}", err=True)
            raise typer.Exit(code=1) from None
        payload = as_json(report)
        run_file = out / f"{base}-run{run}.json"
        run_file.write_text(payload)
        reports.append(report)
        files.append(run_file.name)
        if run == 1:
            sheet = build_sheet(run_file.name, hashlib.sha256(payload.encode()).hexdigest(), pairs)
            sheet_file = out / f"{base}-review.yaml"
            sheet_file.write_text(yaml.safe_dump(sheet, sort_keys=False, allow_unicode=True))
        m = report.metrics
        typer.echo(
            f"run {run}: recall@10 {_fmt(m['recall_at_10'].value)} "
            f"({m['recall_at_10'].denominator})  status {m['status_agreement'].numerator:.0f}/"
            f"{m['status_agreement'].denominator}  safe {m['safe_handling'].numerator:.0f}/"
            f"{m['safe_handling'].denominator}  false abstention "
            f"{m['false_abstention'].numerator:.0f}/{m['false_abstention'].denominator}  "
            f"citation integrity {m['citation_integrity'].numerator:.0f}/"
            f"{m['citation_integrity'].denominator}  forbidden hits "
            f"{m['forbidden_assertions'].value:.0f}  log leaks {report.privacy.question_text_found}"
        )
    if runs > 1:
        combined = out / f"{base}-combined.json"
        combined.write_text(as_json(combine_runs(reports, files)))
        typer.echo(f"combined: {combined}")
    labels = f" [{', '.join(reports[0].labels)}]" if reports[0].labels else ""
    typer.echo(f"split {split}  snapshot {reports[0].snapshot_id}  {freeze_text}{labels}")
    typer.echo(f"reports: {out}/{base}-run*.json  review sheet: {out}/{base}-review.yaml")


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


@eval_app.command("freeze")
@handle_common_errors
def freeze_command(
    split: Annotated[str, typer.Option("--split", help="Suite split to freeze.")] = "heldout",
    reason: Annotated[str, typer.Option("--reason", help="Why the file is (re)frozen.")] = "",
    suite_dir: Annotated[Path, typer.Option("--suite-dir", help="Suite directory.")] = SUITE_DIR,
) -> None:
    """Freezes a suite file by recording its hash; runs refuse a changed frozen file."""
    from score_docs_assistant.qualification.suite import freeze, manifest_path

    if not reason.strip():
        typer.echo("REQUEST_INVALID: --reason is required", err=True)
        raise typer.Exit(code=2)
    path = suite_dir / f"{split}.yaml"
    manifest = freeze(path, reason.strip())
    target = manifest_path(path)
    typer.echo(f"frozen {path} sha256 {manifest.sha256[:16]}… ({manifest.cases} cases) → {target}")


@review_app.command("import")
@handle_common_errors
def review_import_command(
    ctx: typer.Context,
    sheet: Annotated[Path, typer.Option("--sheet", help="Filled review sheet (YAML).")],
    report: Annotated[Path, typer.Option("--report", help="The run report the sheet belongs to.")],
) -> None:
    """Imports a human-filled review sheet and computes support precision and required-fact
    coverage."""
    from score_docs_assistant.qualification.harness import as_json
    from score_docs_assistant.qualification.review import import_review

    review = import_review(sheet, report)
    path = reports_dir(_config(ctx)) / f"human-review-{stamp()}.json"
    path.write_text(as_json(review))
    typer.echo(
        f"reviewer {review.reviewer} ({review.reviewed_on}); support precision "
        f"{_fmt(review.support_precision.value)} of {review.support_precision.denominator} claims; "
        f"required-fact coverage {_fmt(review.required_fact_coverage.value)} over "
        f"{review.required_fact_coverage.denominator} cases; unreviewed claims "
        f"{review.unreviewed_claims}, facts {review.unreviewed_facts}"
    )
    typer.echo(f"human review: {path}")


@eval_app.command("adversarial")
@handle_common_errors
def adversarial_command(
    ctx: typer.Context,
    cases: Annotated[Path, typer.Option("--cases", help="Adversarial case file.")] = Path(
        "eval/hostile/cases.yaml"
    ),
    docs: Annotated[Path, typer.Option("--docs", help="SYNTHETIC hostile documents.")] = Path(
        "eval/hostile/docs"
    ),
    profiles_dir: Annotated[Path, typer.Option("--profiles-dir", help="Parser profiles.")] = Path(
        "config/parser-profiles"
    ),
) -> None:
    """Runs the synthetic hostile suite with the local models on a throwaway snapshot; any failure
    is critical."""
    from score_docs_assistant.cli import runtime_factory
    from score_docs_assistant.qualification.adversarial import (
        hostile_snapshot,
        load_cases,
        run_adversarial,
    )
    from score_docs_assistant.qualification.harness import as_json

    config = _config(ctx)
    case_file = load_cases(cases)
    embedder = runtime_factory.build_embedding_provider(config)
    generator = runtime_factory.build_generation_provider(config)
    documents = sum(1 for p in docs.rglob("*") if p.is_file())
    try:
        with hostile_snapshot(
            docs,
            model_lock=config.data_dir / "model-lock.json",
            profiles_dir=profiles_dir,
            embedder=embedder,
            base_config=config,
        ) as throwaway:
            report = asyncio.run(
                run_adversarial(
                    case_file,
                    config=throwaway,
                    embedder=embedder,
                    generator=generator,
                    documents=documents,
                )
            )
    except GenerationError as exc:
        typer.echo(f"{exc.code}: {exc.message}", err=True)
        raise typer.Exit(code=1) from None
    path = reports_dir(config) / f"adversarial-{stamp()}.json"
    path.write_text(as_json(report))
    for j in report.judgements:
        mark = "FAIL" if j.failures else "ok  "
        typer.echo(f"  {mark} {j.id}  status {j.status}  {', '.join(j.failures)}")
    typer.echo(
        f"cases {report.cases}  failures {report.failures} {report.failures_by_kind}  "
        f"utility {report.utility['ok']}/{report.utility['total']}"
    )
    typer.echo(f"report: {path}")
