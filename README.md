# AI Sales Agent for Website Consulting

Local market intelligence + outbound sales system for SMB digital capture in Charlotte, NC.

## The Two-Track System

```
Charlotte SMB Discovery
        │
        ▼
Business Prospecting Agent
        │
        ├─────────────────────────────────┐
        │                                 │
   Has Website                    No Website Found
   (Track A)                      (Track B)
        │                                 │
        ▼                                 ▼
  Website Crawl Agent        Presence Reconstruction Agent
        │                                 │
        ▼                                 ▼
  Website Analysis           Digital Gap Analysis
  (SEO, UX, speed)           (GBP, directories, reviews)
        │                                 │
        └──────────────┬──────────────────┘
                       ▼
             Opportunity Scoring Engine
                       │
        ┌──────────────┼──────────────────┐
        ▼                                 ▼
 High Priority Lead              Medium / Low Lead
        │
        ▼
 Contact Discovery Agent
        │
        ▼
 Personalization Agent
        │
        ▼
 Email Draft Agent
        │
        ▼
 Human Review Queue → Send
```

**Track A** (website exists) — optimization play. Angle: "your site has gaps costing you calls."

**Track B** (no website) — greenfield capture. Angle: "you're invisible in local and AI search."

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env
# fill in API keys in .env
```

### Required API Keys

| Key | Purpose | Free tier |
|-----|---------|-----------|
| `ANTHROPIC_API_KEY` | Claude — all agent reasoning + email drafting | No |
| `SERPAPI_KEY` | Google Maps prospecting + directory signals | 100 searches/month |
| `HUNTER_API_KEY` | Contact discovery for Track A businesses | 25 searches/month |

Without API keys the pipeline runs on mock data for development.

## Usage

```bash
# Run full pipeline (all industries, Charlotte)
python main.py run

# Run for specific industries
python main.py run --industries plumber hvac electrician --limit 10

# Review the outreach queue
python main.py queue list

# Mark a lead as sent or skip it
python main.py queue send "Charlotte HVAC Co #1"
python main.py queue skip "Charlotte HVAC Co #2"
```

## Project Structure

```
├── main.py                       # CLI entry point
├── config.py                     # Settings (pydantic-settings + .env)
├── agents/
│   ├── prospecting.py            # Discovers SMBs via Google Maps
│   ├── website_router.py         # First-class track routing decision
│   ├── website_crawl.py          # Fetches homepage + key pages (Track A)
│   ├── presence_reconstruction.py # Rebuilds digital footprint (Track B)
│   ├── website_analysis.py       # SEO/UX/conversion audit + AI scoring (Track A)
│   ├── digital_gap_analysis.py   # Visibility gap analysis + AI scoring (Track B)
│   ├── scoring.py                # Opportunity Scoring Engine (both tracks)
│   ├── contact_discovery.py      # Owner name + email via Hunter / search
│   ├── personalization.py        # Builds token dict for email templates
│   └── email_draft.py            # Claude-drafted personalized cold emails
├── models/
│   ├── business.py               # Business data model + WebsiteStatus enum
│   ├── analysis.py               # WebsiteAnalysis + DigitalGapAnalysis
│   └── lead.py                   # Lead + OpportunityScore + EmailDraft
├── pipeline/
│   ├── orchestrator.py           # Runs the full two-track pipeline
│   └── review_queue.py           # JSONL queue for human review before send
└── data/                         # Created at runtime — gitignored
    └── review_queue.jsonl
```

## Scoring

**Track A — Website Present Score (0–100)**
- Mobile-friendliness
- SSL / HTTPS
- Load speed
- Contact CTA presence
- SEO basics (title, meta, H1, schema)
- Services page clarity
- Testimonials / social proof

**Track B — No-Website Score (0–100)**
- Google Business Profile completeness
- Local directory coverage
- Review count vs. competitors
- Estimated missed leads/month
- Competitor website saturation

**Final Opportunity Score = the track score for the assigned track**

Priority tiers: HIGH ≥ 70 | MEDIUM 40–69 | LOW < 40

## Email Branching

Track A angle:
> "Your current website has a few gaps that could be limiting how many calls you get from mobile users and local search."

Track B angle:
> "I couldn't find a website for your business, which usually means you're missing a meaningful amount of local search traffic and quote requests."

Same system. Different framing. Higher reply rate.