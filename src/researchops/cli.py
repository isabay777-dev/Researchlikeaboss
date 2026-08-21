"""ResearchOps command line interface.

The base installation makes no LLM calls and uses no paid API. Optional Docling
and PyAlex integrations run only when their explicit commands are requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


DEFAULT_CONFIG = {
    "version": 1,
    "mode": "api-free",
    "limits": {
        "max_source_mb": 80,
        "extract_timeout_seconds": 300,
        "audit_timeout_seconds": 120,
        "evidence_pack_chars": 12000,
        "max_excerpt_chars": 1400,
    },
    "integrations": {
        "docling": "optional",
        "openalex_via_pyalex": "optional",
        "paperqa2": "disabled",
        "openai_api": "disabled",
    },
}

TOKEN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿА-Яа-яЁё0-9][\w'’\-]*", re.UNICODE)


class ResearchOpsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Project:
    article: Path
    state: Path
    evidence: Path
    reports: Path
    discovery: Path
    config: Path
    lock: Path

    @classmethod
    def at(cls, article: Path) -> "Project":
        article = article.expanduser().resolve()
        state = article / ".researchops"
        return cls(
            article=article,
            state=state,
            evidence=state / "evidence",
            reports=state / "reports",
            discovery=state / "discovery",
            config=state / "config.json",
            lock=state / "active.lock",
        )

    def require(self) -> None:
        if not self.config.is_file():
            raise ResearchOpsError(
                f"ResearchOps is not initialized in {self.article}. Run 'researchops init' first."
            )


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(project: Project) -> Dict[str, object]:
    project.require()
    with project.config.open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-zА-Яа-яЁё0-9._-]+", "-", path.stem).strip("-._")
    return stem[:100] or "source"


@contextmanager
def single_job(project: Project, operation: str) -> Iterator[None]:
    project.state.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(project.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ResearchOpsError(
            f"Another ResearchOps job is active ({project.lock}). Do not run heavy jobs in parallel."
        ) from exc
    try:
        payload = {"pid": os.getpid(), "operation": operation, "started_at": int(time.time())}
        os.write(descriptor, json.dumps(payload).encode("utf-8"))
        os.close(descriptor)
        yield
    finally:
        try:
            project.lock.unlink()
        except FileNotFoundError:
            pass


def command_init(args: argparse.Namespace) -> int:
    project = Project.at(args.article)
    project.article.mkdir(parents=True, exist_ok=True)
    project.evidence.mkdir(parents=True, exist_ok=True)
    project.reports.mkdir(parents=True, exist_ok=True)
    project.discovery.mkdir(parents=True, exist_ok=True)
    if project.config.exists() and not args.force:
        raise ResearchOpsError(f"Already initialized: {project.config}")
    write_json(project.config, DEFAULT_CONFIG)
    print(f"Initialized API-free ResearchOps: {project.article}")
    return 0


def command_status(args: argparse.Namespace) -> int:
    project = Project.at(args.article)
    config = load_config(project)
    payload = {
        "article": str(project.article),
        "mode": config.get("mode"),
        "openai_api": config.get("integrations", {}).get("openai_api"),
        "paperqa2": config.get("integrations", {}).get("paperqa2"),
        "api_token_spend": 0,
        "evidence_documents": len(list(project.evidence.glob("*.md"))),
        "discovery_records": len(list(project.discovery.glob("*.json"))),
        "reports": len(list(project.reports.glob("*.md"))),
        "job_active": project.lock.exists(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _read_plain_source(source: Path) -> str:
    try:
        return source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return source.read_text(encoding="utf-8", errors="replace")


def command_extract(args: argparse.Namespace) -> int:
    project = Project.at(args.article)
    config = load_config(project)
    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise ResearchOpsError(f"Source does not exist: {source}")

    limits = config["limits"]
    max_bytes = int(limits["max_source_mb"]) * 1024 * 1024
    if source.stat().st_size > max_bytes:
        raise ResearchOpsError(
            f"Source is larger than {limits['max_source_mb']} MB. Raise the limit explicitly if intended."
        )

    source_hash = sha256(source)
    stem = f"{safe_stem(source)}-{source_hash[:10]}"
    output = project.evidence / f"{stem}.md"
    metadata = project.evidence / f"{stem}.meta.json"
    plain_suffixes = {".md", ".txt", ".rst", ".csv", ".tsv"}

    with single_job(project, "extract"):
        if source.suffix.lower() in plain_suffixes:
            markdown = _read_plain_source(source)
            engine = "plain-text"
        else:
            timeout = int(args.timeout or limits["extract_timeout_seconds"])
            temporary = project.evidence / f".{stem}.docling.tmp"
            command = [
                sys.executable,
                "-m",
                "researchops.docling_worker",
                str(source),
                str(temporary),
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise ResearchOpsError(
                    f"Docling exceeded {timeout}s and was stopped. No parallel retry was started."
                ) from exc
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout).strip()[-1200:]
                raise ResearchOpsError(f"Docling failed: {message}")
            markdown = temporary.read_text(encoding="utf-8")
            temporary.unlink(missing_ok=True)
            engine = "docling"

        output.write_text(markdown, encoding="utf-8")
        write_json(
            metadata,
            {
                "source_name": source.name,
                "source_sha256": source_hash,
                "source_bytes": source.stat().st_size,
                "engine": engine,
                "output": output.name,
                "extracted_at": int(time.time()),
            },
        )

    print(f"Extracted with {engine}: {output}")
    return 0


def _tokens(text: str) -> List[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def _paragraphs(text: str) -> Iterable[str]:
    for part in re.split(r"\n\s*\n", text):
        clean = re.sub(r"\s+", " ", part).strip()
        if len(clean) >= 80:
            yield clean


def _rank_evidence(project: Project, query: str) -> List[Tuple[int, str, int, str]]:
    query_terms = set(_tokens(query))
    if not query_terms:
        raise ResearchOpsError("The evidence query must contain words.")
    ranked: List[Tuple[int, str, int, str]] = []
    for source in sorted(project.evidence.glob("*.md")):
        for index, paragraph in enumerate(_paragraphs(source.read_text(encoding="utf-8")), 1):
            terms = _tokens(paragraph)
            overlap = sum(terms.count(term) for term in query_terms)
            coverage = len(query_terms.intersection(terms))
            score = overlap + (coverage * 3)
            if score:
                ranked.append((score, source.name, index, paragraph))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    return ranked


def command_pack(args: argparse.Namespace) -> int:
    project = Project.at(args.article)
    config = load_config(project)
    limits = config["limits"]
    budget = int(args.max_chars or limits["evidence_pack_chars"])
    excerpt_limit = int(limits["max_excerpt_chars"])
    ranked = _rank_evidence(project, args.query)
    if not ranked:
        raise ResearchOpsError("No evidence matched the query. Extract relevant sources first.")

    lines = [
        "# Evidence pack",
        "",
        f"Query: {args.query}",
        "",
        "Generated deterministically from local extracted sources; verify against originals.",
        "",
    ]
    seen = set()
    used = len("\n".join(lines))
    selected = 0
    for score, source, paragraph_number, paragraph in ranked:
        normalized = re.sub(r"\W+", "", paragraph.casefold())[:300]
        if normalized in seen:
            continue
        seen.add(normalized)
        excerpt = paragraph[:excerpt_limit].rstrip()
        block = f"## {source} · paragraph {paragraph_number} · score {score}\n\n{excerpt}\n\n"
        if used + len(block) > budget:
            continue
        lines.append(block.rstrip())
        lines.append("")
        used += len(block)
        selected += 1
        if selected >= args.max_excerpts:
            break

    output = Path(args.output).expanduser().resolve() if args.output else project.state / "EVIDENCE_PACK.md"
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Evidence pack: {output} ({selected} excerpts, {output.stat().st_size} bytes)")
    return 0


def _compact_openalex(work: object) -> Dict[str, object]:
    authors = []
    for authorship in (work.get("authorships") or [])[:12]:
        author = authorship.get("author") or {}
        if author.get("display_name"):
            authors.append(author["display_name"])
    return {
        "id": work.get("id"),
        "doi": work.get("doi"),
        "title": work.get("title"),
        "publication_year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count"),
        "type": work.get("type"),
        "open_access": work.get("open_access"),
        "authors": authors,
    }


def command_discover(args: argparse.Namespace) -> int:
    project = Project.at(args.article)
    load_config(project)
    try:
        from pyalex import Works, config as pyalex_config
    except ImportError as exc:
        raise ResearchOpsError(
            "PyAlex is not installed. Install the optional 'discovery' extra."
        ) from exc
    if args.email:
        pyalex_config.email = args.email
    with single_job(project, "discover"):
        works = Works().search_filter(title_and_abstract=args.query).get(per_page=args.limit)
        payload = {
            "query": args.query,
            "provider": "OpenAlex via PyAlex",
            "paid_api": False,
            "retrieved_at": int(time.time()),
            "works": [_compact_openalex(work) for work in works],
        }
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output = project.discovery / f"openalex-{stamp}.json"
        write_json(output, payload)
    print(f"OpenAlex metadata: {output} ({len(payload['works'])} works)")
    return 0


def find_qa_script(start: Path) -> Optional[Path]:
    for parent in [start] + list(start.parents):
        candidate = parent / "ACADEMIC_PUBLICATION_QA" / "manuscript_qc.py"
        if candidate.is_file():
            return candidate
    return None


def command_audit(args: argparse.Namespace) -> int:
    project = Project.at(args.article)
    config = load_config(project)
    manuscript = args.manuscript.expanduser().resolve()
    if not manuscript.is_file():
        raise ResearchOpsError(f"Manuscript does not exist: {manuscript}")
    qa_script = args.qa_script.expanduser().resolve() if args.qa_script else find_qa_script(project.article)
    if not qa_script or not qa_script.is_file():
        raise ResearchOpsError("ACADEMIC_PUBLICATION_QA/manuscript_qc.py was not found.")

    stem = safe_stem(manuscript)
    report = project.reports / f"{stem}-qc.md"
    json_report = project.reports / f"{stem}-qc.json"
    command = [
        sys.executable,
        str(qa_script),
        str(manuscript),
        "--report",
        str(report),
        "--json-report",
        str(json_report),
    ]
    if args.journal_config:
        command.extend(["--config", str(args.journal_config.expanduser().resolve())])
    if args.compare_root:
        command.extend(["--compare-root", str(args.compare_root.expanduser().resolve())])
    timeout = int(args.timeout or config["limits"]["audit_timeout_seconds"])
    with single_job(project, "audit"):
        try:
            completed = subprocess.run(
                command,
                check=False,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ResearchOpsError(f"Audit exceeded {timeout}s and was stopped.") from exc
    # The canonical auditor uses exit 2 for a valid STOP verdict. That is a
    # scientific result, not an execution failure, and its reports are usable.
    if completed.returncode not in (0, 2):
        message = (completed.stderr or completed.stdout).strip()[-1600:]
        raise ResearchOpsError(f"Audit failed: {message}")
    if completed.stdout.strip():
        print(completed.stdout.strip())
    print(f"Audit report: {report}")
    print(f"Machine report: {json_report}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="researchops",
        description="API-free local evidence operations for academic articles.",
    )
    subparsers = root.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize an article workspace")
    init.add_argument("article", type=Path)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=command_init)

    status = subparsers.add_parser("status", help="Show local mode and artifact counts")
    status.add_argument("article", type=Path)
    status.set_defaults(func=command_status)

    extract = subparsers.add_parser("extract", help="Extract one source into local Markdown")
    extract.add_argument("article", type=Path)
    extract.add_argument("source", type=Path)
    extract.add_argument("--timeout", type=int)
    extract.set_defaults(func=command_extract)

    pack = subparsers.add_parser("pack", help="Build a bounded local evidence pack")
    pack.add_argument("article", type=Path)
    pack.add_argument("--query", required=True)
    pack.add_argument("--max-chars", type=int)
    pack.add_argument("--max-excerpts", type=int, default=12)
    pack.add_argument("--output", type=Path)
    pack.set_defaults(func=command_pack)

    discover = subparsers.add_parser("discover", help="Find metadata through free OpenAlex")
    discover.add_argument("article", type=Path)
    discover.add_argument("--query", required=True)
    discover.add_argument("--limit", type=int, default=10, choices=range(1, 51))
    discover.add_argument("--email", help="Optional OpenAlex polite-pool email")
    discover.set_defaults(func=command_discover)

    audit = subparsers.add_parser("audit", help="Run the existing offline publication audit")
    audit.add_argument("article", type=Path)
    audit.add_argument("manuscript", type=Path)
    audit.add_argument("--journal-config", type=Path)
    audit.add_argument("--compare-root", type=Path)
    audit.add_argument("--qa-script", type=Path)
    audit.add_argument("--timeout", type=int)
    audit.set_defaults(func=command_audit)
    return root


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        return int(arguments.func(arguments))
    except ResearchOpsError as exc:
        print(f"researchops: {exc}", file=sys.stderr)
        return 2
