# SMB Digital Presence Agent — Business Case & Build Log

**Status:** Active development | Testing with real Charlotte data
**Type:** Personal project / agent engineering practice
**Stack:** Python, Claude API, Playwright, Streamlit

---

## The Problem

Most small service businesses in Charlotte — plumbers, roofers, HVAC companies, electricians — have a broken relationship with the internet. They either have no web presence at all, or they have a website that was built in 2014 and hasn't been touched since.

The result: they're invisible in local search, invisible in AI-powered recommendations, and losing inbound leads to competitors who spent $500 on a basic site.

**The market signal:**
- ~500,000 SMBs in the Charlotte metro area
- Roughly 35–40% of local service businesses have no website at all
- Of those that do, studies estimate 60–70% haven't been updated in over 3 years
- 76% of local searches result in a phone call or visit within 24 hours (BrightLocal)
- AI search tools (ChatGPT, Perplexity, Google AI Overviews) increasingly surface businesses with structured web presence over those without

This isn't a niche problem. It's a structural gap that gets bigger every year as AI search becomes the default.

---

## The Insight That Drives the System

Most website consulting tools treat every business the same: "your site needs work." That's a weak pitch.

The real split is binary:

**Has a website** → the conversation is about optimization: speed, SEO, conversion rate, mobile UX. These are consultative sales with higher ticket prices.

**No website** → the conversation is about existence: you are effectively invisible to AI search engines and under-indexed in Google Maps. This is a faster, easier sale with a lower friction close.

Building a system that detects this split and routes to different outreach angles is the core architectural decision. Same pipeline, two different messages, meaningfully higher reply rate.

---

## What I Built

An end-to-end multi-agent pipeline that:

1. **Discovers** local SMBs by scraping Google Maps with a headless browser (no API cost)
2. **Routes** each business into one of two tracks based on whether a live website is detected
3. **Analyzes** Track A businesses for SEO, UX, speed, and conversion gaps
4. **Reconstructs** Track B businesses' digital footprint from Google Business Profile and directory signals
5. **Scores** each as an opportunity (0–100) with HIGH/MEDIUM/LOW priority tiers
6. **Discovers** owner contact information
7. **Drafts** personalized cold emails with track-specific framing
8. **Queues** everything for human review before any email is sent

The pipeline is fully async, runs locally, and surfaces results in a Streamlit dashboard with a review queue.

### Agent Architecture

```
Google Maps Scraper (Playwright — free, no API)
        │
        ▼
Website Router — live HEAD request to validate presence
        │
        ├─────────────────────────┐
   Track A                   Track B
  (has website)            (no website)
        │                        │
  Website Crawl          Presence Reconstruction
        │                        │
  Website Analysis        Digital Gap Analysis
  (Claude-scored)         (Claude-scored)
        │                        │
        └──────────┬─────────────┘
                   ▼
         Opportunity Scoring Engine
                   │
         Contact Discovery
                   │
         Personalization (branched by track)
                   │
         Email Draft (Claude — track-specific angle)
                   │
         Human Review Queue → Send
```

### Tech Stack
- **Python 3.12** — async throughout
- **Playwright** — headless Chromium for Google Maps scraping
- **Claude (Anthropic)** — website scoring, gap analysis, email drafting
- **Pydantic v2** — typed data models across every agent boundary
- **Streamlit** — internal dashboard for running the pipeline and reviewing leads
- **HTTPX** — async HTTP for website crawling and API calls

---

## Where I Am Now

This project is in active testing. The pipeline runs end-to-end:

- The Google Maps scraper pulls real Charlotte businesses without any API key
- The website router correctly identifies live vs. dead/missing sites
- The analysis agents produce scored outputs with identified issues
- The email drafts are structured and branched by track
- The Streamlit UI lets me run a batch, review leads, and mark emails as sent

**What's working:**
- Full two-track routing logic
- Heuristic scoring without Claude (for cost-free testing)
- Claude-enhanced scoring and email drafting when the API key is present
- Human-in-the-loop review queue before any outreach goes out

**What's next:**
- Validate scraper output quality against real Charlotte businesses
- Tune scoring thresholds based on actual reply rates
- Add email sending integration (Gmail API or SMTP)
- Track reply rates by track (A vs B) to validate the two-angle hypothesis

---

## Why I Built This

This is a practice project for agent engineering. The goal wasn't to ship a product — it was to build something that required real design decisions:

- How do you structure data flow across agents without it becoming a mess?
- Where does Claude add value vs. where is a heuristic good enough?
- How do you build a pipeline that degrades gracefully when API keys are missing?
- What does a human-in-the-loop system actually look like in practice?

The SMB consulting angle is real — the problem exists, the market is large, and the outreach angle is sound. But the primary output of this project is a working agent system I understand end-to-end, not a business I'm ready to scale.

That's the honest version. The system is good enough to generate real leads and real emails. Whether those emails convert is the next experiment.

---

## Key Metrics (Market Framing)

| Signal | Source |
|--------|--------|
| ~35% of US SMBs have no website | Forbes / SCORE 2023 |
| 76% of local searches → call or visit within 24h | BrightLocal 2024 |
| Average website consulting engagement: $1,500–$5,000 | Industry estimates |
| Greenfield (no website) close rate typically 2–3x higher than optimization pitch | Sales heuristic |
| Charlotte metro business count: ~500,000 | US Census / Charlotte Chamber |

---

*Built by Brett Rudisel — June 2026*
