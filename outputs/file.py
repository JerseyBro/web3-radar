from __future__ import annotations
import json
import logging
from pathlib import Path

from outputs.base import BaseOutput, DeliveryResult, DeliveryContext, DeliveryStatus
from radar.report import Report

logger = logging.getLogger(__name__)


class FileOutput(BaseOutput):
    target = "file"

    def __init__(self, reports_dir: Path | None = None):
        from radar.config import ROOT
        self.dir = reports_dir or (ROOT / "reports")
        self.dir.mkdir(parents=True, exist_ok=True)

    def deliver(self, report: Report, context: DeliveryContext) -> DeliveryResult:
        # Always persist the report (even in dry-run / preview).
        md_path = self.dir / f"{report.period}-{report.radar}.md"
        json_path = self.dir / f"{report.period}-{report.radar}.json"
        md_path.write_text(report.markdown, encoding="utf-8")
        json_path.write_text(json.dumps(report.canonical_json(), indent=2, ensure_ascii=False), encoding="utf-8")
        return DeliveryResult(
            target=self.target, success=True, status=DeliveryStatus.SUCCESS.value,
            attempts=1, detail={"md": str(md_path), "json": str(json_path)},
        )
