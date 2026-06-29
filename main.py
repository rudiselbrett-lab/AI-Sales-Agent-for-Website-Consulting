"""
AI Sales Agent for Website Consulting
Charlotte SMB Discovery — Two-Track Pipeline

Usage:
  python main.py run                              # run full pipeline
  python main.py run --industries plumber hvac    # specific industries
  python main.py queue list                       # show pending leads
  python main.py queue send <business_name>       # mark a lead as sent
  python main.py queue skip <business_name>       # mark a lead as skipped
"""

import asyncio
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="SMB digital presence discovery + outbound sales agent")
queue_app = typer.Typer(help="Manage the human review queue")
app.add_typer(queue_app, name="queue")

console = Console()


@app.command()
def run(
    industries: list[str] = typer.Option(None, "--industries", "-i", help="Industries to target"),
    limit: int = typer.Option(25, "--limit", "-l", help="Leads per industry"),
):
    """Discover SMBs, analyze digital presence, and draft outreach emails."""
    from pipeline import PipelineOrchestrator

    async def _run():
        orchestrator = PipelineOrchestrator()
        leads = await orchestrator.run(
            industries=industries or None,
            limit_per_industry=limit,
        )
        _print_summary(leads)

    asyncio.run(_run())


@queue_app.command("list")
def queue_list():
    """Show all leads pending human review."""
    from config import settings
    from pipeline import ReviewQueue

    q = ReviewQueue(settings.review_queue_path)
    pending = q.list_pending()

    if not pending:
        console.print("[dim]No pending leads in review queue.[/dim]")
        return

    table = Table(title=f"Pending Leads ({len(pending)})")
    table.add_column("Business", style="bold")
    table.add_column("Track")
    table.add_column("Score")
    table.add_column("Priority")
    table.add_column("Contact")
    table.add_column("Subject")

    for r in sorted(pending, key=lambda x: x["score"], reverse=True):
        priority_style = {"high": "red", "medium": "yellow", "low": "dim"}.get(r["priority"], "")
        table.add_row(
            r["business_name"],
            r["track"],
            str(r["score"]),
            f"[{priority_style}]{r['priority']}[/{priority_style}]",
            r.get("owner_email") or r.get("owner_name") or "—",
            (r.get("email_subject") or "")[:50],
        )

    console.print(table)


@queue_app.command("send")
def queue_send(business_name: str = typer.Argument(...)):
    """Mark a lead as sent in the review queue."""
    from config import settings
    from pipeline import ReviewQueue

    q = ReviewQueue(settings.review_queue_path)
    q.mark_sent(business_name)
    console.print(f"[green]Marked as sent:[/green] {business_name}")


@queue_app.command("skip")
def queue_skip(business_name: str = typer.Argument(...)):
    """Mark a lead as skipped in the review queue."""
    from config import settings
    from pipeline import ReviewQueue

    q = ReviewQueue(settings.review_queue_path)
    q.mark_skipped(business_name)
    console.print(f"[dim]Marked as skipped:[/dim] {business_name}")


def _print_summary(leads):
    from models.lead import TrackType, Priority

    table = Table(title="Pipeline Results")
    table.add_column("Business", style="bold")
    table.add_column("Track")
    table.add_column("Score")
    table.add_column("Priority")
    table.add_column("Email Ready")

    for lead in sorted(leads, key=lambda l: (l.opportunity_score.final_score if l.opportunity_score else 0), reverse=True):
        score_obj = lead.opportunity_score
        priority = score_obj.priority.value if score_obj else "—"
        priority_style = {"high": "red", "medium": "yellow", "low": "dim"}.get(priority, "")
        track_label = "A: Website" if lead.track == TrackType.WEBSITE_EXISTS else "B: No Site"
        table.add_row(
            lead.business.name,
            track_label,
            str(score_obj.final_score if score_obj else "—"),
            f"[{priority_style}]{priority}[/{priority_style}]",
            "✓" if lead.email_draft else "—",
        )

    console.print(table)


if __name__ == "__main__":
    app()
