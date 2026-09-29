"""F008 qualification commands (specs/008-quality-qualification/contracts/cli.md).

`eval suite | freeze | review import | adversarial | performance`, `models qualify` and
`release report`. Every command writes its evidence under `data/reports/`; nothing is downloaded
and question or answer text is never logged.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer
import yaml

from score_docs_assistant.cli.evaluate import eval_app
from score_docs_assistant.cli.main import cli_app, handle_common_errors
from score_docs_assistant.cli.models import models_app
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


@eval_app.command("performance")
@handle_common_errors
@handle_search_errors
def performance_command(
    ctx: typer.Context,
    cases: Annotated[list[Path], typer.Option("--cases", help="Suite file(s) with questions.")],
    answers_n: Annotated[int, typer.Option("--answers", min=1, help="Warm answers to time.")] = 50,
    cold: Annotated[int, typer.Option("--cold", min=0, help="Cold samples.")] = 5,
) -> None:
    """Measures retrieval, progress, answer, cancellation and memory against the performance
    budgets."""
    from score_docs_assistant.cli.ask import build_answer_service
    from score_docs_assistant.qualification.harness import as_json
    from score_docs_assistant.qualification.performance import OllamaControl, measure
    from score_docs_assistant.qualification.suite import load_suite

    config = _config(ctx)
    questions = [c.question for path in cases for c in load_suite(path)[0].cases]
    service = build_answer_service(config)
    control = OllamaControl(
        config.runtime.base_url, [config.runtime.generation_model, config.runtime.embedding_model]
    )
    try:
        report = asyncio.run(
            measure(
                search=service._search,  # noqa: SLF001
                answers=service,
                questions=questions,
                answers_n=answers_n,
                cold_samples=cold,
                unload=control.unload if cold else None,
                loaded=control.loaded,
            )
        )
    except GenerationError as exc:
        typer.echo(f"{exc.code}: {exc.message}", err=True)
        raise typer.Exit(code=1) from None
    path = reports_dir(config) / f"performance-{stamp()}.json"
    path.write_text(as_json(report))
    for name, dist in report.distributions.items():
        typer.echo(
            f"  {name:<24} n={dist.samples:<4} p50={dist.p50} ms  p95={dist.p95} ms  "
            f"max={dist.max} ms"
        )
    for budget in report.budgets:
        typer.echo(
            f"  budget {budget.name:<22} {budget.statistic} {budget.measured_ms} ms "
            f"≤ {budget.target_ms:.0f} ms → {budget.status}"
        )
    typer.echo(f"memory: {report.memory}  cold unload verified: {report.cold_unload_verified}")
    typer.echo(f"report: {path}")


@models_app.command("qualify")
@handle_common_errors
def models_qualify_command(ctx: typer.Context) -> None:
    """Records the locked models' identity, license and context from the local runtime (no
    downloads)."""
    from score_docs_assistant.qualification.harness import as_json
    from score_docs_assistant.qualification.models import http_fetch, qualify

    config = _config(ctx)
    out = reports_dir(config)
    try:
        record = qualify(
            config.data_dir / "model-lock.json", http_fetch(config.runtime.base_url), out
        )
    except (httpx.HTTPError, OSError, ValueError) as exc:
        typer.echo(f"RUNTIME_UNAVAILABLE: {exc}", err=True)
        raise typer.Exit(code=1) from None
    path = out / f"models-{stamp()}.json"
    path.write_text(as_json(record))
    for m in record.models:
        typer.echo(
            f"  {m.role:<10} {m.tag}  digest {m.locked_digest[:12]} lock match {m.lock_match}  "
            f"{m.family} {m.parameter_size} {m.quantization} ctx {m.context_length}  "
            f"license {m.license_spdx_guess or m.license_first_line}"
        )
    typer.echo(f"runtime {record.runtime_version} (locked {record.locked_runtime_version})")
    typer.echo(f"report: {path}")


release_app = typer.Typer(add_completion=False, help="Release evidence.")
cli_app.add_typer(release_app, name="release")


@release_app.command("report")
@handle_common_errors
def release_report_command(
    ctx: typer.Context,
    gates: Annotated[Path, typer.Option("--gates", help="Gate file.")] = Path(
        "eval/release-gates.yaml"
    ),
    suite_dir: Annotated[Path, typer.Option("--suite-dir", help="Suite directory.")] = SUITE_DIR,
) -> None:
    """Builds the release report from recorded evidence; gates without evidence are "not run",
    human-judged gates without a review are "blocked"."""
    import importlib.util

    from score_docs_assistant.qualification.gates import Identity, load_gates
    from score_docs_assistant.qualification.report import build_report, to_markdown
    from score_docs_assistant.qualification.suite import freeze_status, load_suite
    from score_docs_assistant.storage.catalog import Catalog

    config = _config(ctx)
    active = None
    catalog = Catalog.open(config.data_dir, create=False)
    if catalog is not None:
        with catalog:
            active = catalog.active_id()
    digest = None
    lock_path = config.data_dir / "model-lock.json"
    if lock_path.is_file():
        for model in json.loads(lock_path.read_text()).get("models", []):
            if model.get("role") == "generation":
                digest = str(model.get("digest", "")).removeprefix("sha256:")
    heldout = suite_dir / "heldout.yaml"
    freeze = freeze_status(heldout, load_suite(heldout)[1])[1] if heldout.is_file() else None
    traceability: list[str] | None = None
    script = Path("scripts/check_traceability.py")
    if script.is_file():
        spec = importlib.util.spec_from_file_location("check_traceability", script)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            root = Path.cwd()
            traceability = module.check(
                (root / "docs" / "PROJECT_SPEC.md").read_text(),
                (root / "docs" / "TRACEABILITY.md").read_text(),
                root,
            )
    report = build_report(
        load_gates(gates),
        reports=reports_dir(config),
        identity=Identity(snapshot_id=active, generation_digest=digest, freeze=freeze),
        traceability=traceability,
        assumptions=Path("docs/ASSUMPTIONS.md"),
    )
    out = reports_dir(config) / f"release-{stamp()}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    (out / "report.md").write_text(to_markdown(report))
    counts: dict[str, int] = {}
    for gate in report.gates:
        counts[gate.status] = counts.get(gate.status, 0) + 1
    typer.echo(f"verdict: {report.verdict}  gates: {counts}")
    for item in report.blocking:
        typer.echo(f"  {item}")
    typer.echo(f"report: {out}/report.md")
