from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from researchops.cli import main


class ResearchOpsCLITest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.article = self.root / "article"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str):
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_init_and_status_are_api_free(self) -> None:
        code, _, error = self.run_cli("init", str(self.article))
        self.assertEqual(code, 0, error)
        config = json.loads((self.article / ".researchops/config.json").read_text())
        self.assertEqual(config["mode"], "api-free")
        self.assertEqual(config["integrations"]["openai_api"], "disabled")

        code, output, error = self.run_cli("status", str(self.article))
        self.assertEqual(code, 0, error)
        status = json.loads(output)
        self.assertEqual(status["api_token_spend"], 0)
        self.assertFalse(status["job_active"])

    def test_plain_extract_and_bounded_pack(self) -> None:
        self.run_cli("init", str(self.article))
        source = self.root / "source.md"
        source.write_text(
            "# Study\n\nArtificial intelligence changes administrative capacity through "
            "information processing and coordination. This paragraph contains enough "
            "material to become a useful local evidence excerpt.\n\n"
            "Unrelated agricultural material is included in a separate long paragraph "
            "that should not outrank the requested mechanism in the evidence search.",
            encoding="utf-8",
        )
        code, _, error = self.run_cli("extract", str(self.article), str(source))
        self.assertEqual(code, 0, error)

        code, output, error = self.run_cli(
            "pack",
            str(self.article),
            "--query",
            "artificial intelligence capacity",
            "--max-chars",
            "1000",
        )
        self.assertEqual(code, 0, error)
        pack = (self.article / ".researchops/EVIDENCE_PACK.md").read_text()
        self.assertIn("information processing", pack)
        self.assertLessEqual(len(pack), 1000)
        self.assertIn("Evidence pack", output)

    def test_second_concurrent_job_is_rejected(self) -> None:
        self.run_cli("init", str(self.article))
        lock = self.article / ".researchops/active.lock"
        lock.write_text("{}")
        source = self.root / "source.txt"
        source.write_text("x" * 100)
        code, _, error = self.run_cli("extract", str(self.article), str(source))
        self.assertEqual(code, 2)
        self.assertIn("Do not run heavy jobs in parallel", error)

    def test_audit_stop_verdict_is_a_valid_result(self) -> None:
        self.run_cli("init", str(self.article))
        manuscript = self.root / "manuscript.md"
        manuscript.write_text("# Abstract\n\nA deliberately incomplete manuscript.", encoding="utf-8")
        auditor = self.root / "auditor.py"
        auditor.write_text(
            "import argparse, pathlib\n"
            "p=argparse.ArgumentParser(); p.add_argument('m'); p.add_argument('--report'); "
            "p.add_argument('--json-report'); a=p.parse_args()\n"
            "pathlib.Path(a.report).write_text('# STOP\\n')\n"
            "pathlib.Path(a.json_report).write_text('{\"verdict\":\"STOP\"}')\n"
            "print('STOP: 1 finding'); raise SystemExit(2)\n",
            encoding="utf-8",
        )
        code, output, error = self.run_cli(
            "audit",
            str(self.article),
            str(manuscript),
            "--qa-script",
            str(auditor),
        )
        self.assertEqual(code, 0, error)
        self.assertIn("STOP: 1 finding", output)
        self.assertTrue((self.article / ".researchops/reports/manuscript-qc.json").is_file())


if __name__ == "__main__":
    unittest.main()
