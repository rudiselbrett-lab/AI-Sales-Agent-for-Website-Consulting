"""
Human Review Queue

Persists leads as newline-delimited JSON for human review before sending.
Supports reading back the queue and marking items as sent/skipped.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from rich.console import Console
from models.lead import Lead

console = Console()


class ReviewQueue:

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def enqueue(self, lead: Lead) -> None:
        record = {
            "enqueued_at": datetime.utcnow().isoformat(),
            "business_name": lead.business.name,
            "track": lead.track.value,
            "priority": lead.opportunity_score.priority.value if lead.opportunity_score else "unknown",
            "score": lead.opportunity_score.final_score if lead.opportunity_score else 0,
            "owner_name": lead.business.owner_name,
            "owner_email": lead.business.owner_email,
            "email_subject": lead.email_draft.subject if lead.email_draft else None,
            "email_body": lead.email_draft.body if lead.email_draft else None,
            "status": "pending_review",
            "full_lead": lead.model_dump(mode="json"),
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def list_pending(self) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    if record.get("status") == "pending_review":
                        records.append(record)
        return records

    def mark_sent(self, business_name: str) -> None:
        self._update_status(business_name, "sent")

    def mark_skipped(self, business_name: str) -> None:
        self._update_status(business_name, "skipped")

    def _update_status(self, business_name: str, new_status: str) -> None:
        if not self.path.exists():
            return
        lines = self.path.read_text().splitlines()
        updated = []
        for line in lines:
            if not line.strip():
                continue
            record = json.loads(line)
            if record["business_name"] == business_name and record["status"] == "pending_review":
                record["status"] = new_status
                record[f"{new_status}_at"] = datetime.utcnow().isoformat()
            updated.append(json.dumps(record))
        self.path.write_text("\n".join(updated) + "\n")
        console.log(f"[dim]Queue: {business_name} → {new_status}[/dim]")
