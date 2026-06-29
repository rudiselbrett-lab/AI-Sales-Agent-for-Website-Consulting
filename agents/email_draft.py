"""
Email Draft Agent

Generates personalized cold outreach emails using Claude.
Branch logic: Track A (website exists) vs Track B (no website) → different angle and framing.
"""

import anthropic
from rich.console import Console
from config import settings
from models.lead import TrackType, EmailDraft

console = Console()

SENDER_NAME = "Chat"  # update to real sender name


class EmailDraftAgent:

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def draft(
        self,
        track: TrackType,
        tokens: dict[str, str],
    ) -> EmailDraft:
        if track == TrackType.WEBSITE_EXISTS:
            subject, body = await self._draft_website_email(tokens)
        else:
            subject, body = await self._draft_no_website_email(tokens)

        console.log(f"[cyan]Email drafted[/cyan] for {tokens.get('BusinessName')} ({track})")
        return EmailDraft(subject=subject, body=body, track=track, personalization_tokens=tokens)

    async def _draft_website_email(self, t: dict) -> tuple[str, str]:
        prompt = f"""Write a short, direct cold outreach email to the owner of a local service business.

Context:
- Business: {t.get('BusinessName')} ({t.get('Industry')} in {t.get('City')})
- Owner name: {t.get('OwnerName')}
- Their website scored {t.get('WebsiteScore', '?')}/100
- Top issue 1: {t.get('TopIssue1', '')}
- Top issue 2: {t.get('TopIssue2', '')}
- Quick win 1: {t.get('QuickWin1', '')}
- Sender name: {SENDER_NAME}

Rules:
- Under 120 words in the body
- Lead with one specific observation about their site
- NO generic praise ("great business!")
- Soft CTA: offer to send a free breakdown, not a sales pitch
- Conversational, no jargon
- Do NOT use the word "leverage" or "optimize"
- End with just the sender's first name

Return JSON with keys "subject" and "body". Subject line under 8 words.
"""
        return await self._call_claude(prompt)

    async def _draft_no_website_email(self, t: dict) -> tuple[str, str]:
        prompt = f"""Write a short, direct cold outreach email to the owner of a local service business that has NO website.

Context:
- Business: {t.get('BusinessName')} ({t.get('Industry')} in {t.get('City')})
- Owner name: {t.get('OwnerName')}
- Approx {t.get('CompetitorPct', '70')}% of their local competitors have websites
- Estimated missed inbound leads/month: {t.get('MissedLeads', 'several')}
- Key gap 1: {t.get('VisibilityGap1', 'local search visibility')}
- Fast capture option: {t.get('FastCapture', 'a simple one-page site')}
- Sender name: {SENDER_NAME}

Rules:
- Under 120 words in the body
- Frame around what they're MISSING, not what they're doing wrong
- Do NOT say "your competitors are beating you"
- Lead with the search visibility angle (AI search, Google Maps)
- Soft CTA: offer a free breakdown of what people see when they search for their services
- Conversational, no jargon, no hype
- End with just the sender's first name

Return JSON with keys "subject" and "body". Subject line under 8 words.
"""
        return await self._call_claude(prompt)

    async def _call_claude(self, prompt: str) -> tuple[str, str]:
        import json

        response = self.client.messages.create(
            model=settings.agent_model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            data = json.loads(raw)
            return data.get("subject", "Quick note about your online presence"), data.get("body", "")
        except json.JSONDecodeError:
            return "Quick note about your online presence", raw
