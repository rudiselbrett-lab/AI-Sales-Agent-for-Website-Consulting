"""
Streamlit UI for the SMB Sales Agent pipeline.

Run with:  streamlit run ui.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import streamlit as st

# ── page config (must be first Streamlit call) ──────────────────────────────
st.set_page_config(
    page_title="SMB Sales Agent",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── sidebar: API keys ────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎯 SMB Sales Agent")
    st.caption("Charlotte, NC — Two-Track Pipeline")
    st.divider()

    st.subheader("API Keys")
    anthropic_key = st.text_input("Anthropic API Key", type="password",
                                   value=os.environ.get("ANTHROPIC_API_KEY", ""))
    serpapi_key   = st.text_input("SerpAPI Key", type="password",
                                   value=os.environ.get("SERPAPI_KEY", ""))
    hunter_key    = st.text_input("Hunter.io Key", type="password",
                                   value=os.environ.get("HUNTER_API_KEY", ""))

    st.caption("Leave blank to run on mock data (no API calls made).")
    st.divider()

    st.subheader("Run Settings")
    all_industries = [
        "plumber", "electrician", "hvac", "roofer", "landscaper",
        "auto-repair", "dentist", "chiropractor", "restaurant", "salon",
    ]
    selected_industries = st.multiselect(
        "Industries", all_industries, default=["plumber", "hvac"]
    )
    limit = st.slider("Leads per industry", 1, 25, 5)
    min_score = st.slider("Min opportunity score", 0, 100, 40)

# ── inject keys into env so config.py + agents pick them up ─────────────────
if anthropic_key:
    os.environ["ANTHROPIC_API_KEY"] = anthropic_key
if serpapi_key:
    os.environ["SERPAPI_KEY"] = serpapi_key
if hunter_key:
    os.environ["HUNTER_API_KEY"] = hunter_key
if min_score:
    os.environ["MIN_OPPORTUNITY_SCORE"] = str(min_score)

# ── tabs ─────────────────────────────────────────────────────────────────────
tab_run, tab_queue, tab_lead = st.tabs(["▶ Run Pipeline", "📋 Review Queue", "🔍 Lead Detail"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Run Pipeline
# ════════════════════════════════════════════════════════════════════════════
with tab_run:
    st.header("Run Pipeline")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(
            f"Will prospect **{', '.join(selected_industries) or 'no industries selected'}** "
            f"— up to **{limit}** businesses each, min score **{min_score}**."
        )
    with col2:
        run_btn = st.button("🚀 Run", type="primary", disabled=not selected_industries)

    if run_btn:
        from pipeline import PipelineOrchestrator

        progress_box = st.empty()
        log_box = st.empty()
        logs: list[str] = []

        def _log(msg: str):
            logs.append(msg)
            log_box.code("\n".join(logs[-30:]), language=None)

        _log("Starting pipeline…")

        async def _run():
            orchestrator = PipelineOrchestrator()
            return await orchestrator.run(
                industries=selected_industries,
                limit_per_industry=limit,
            )

        with st.spinner("Pipeline running…"):
            leads = asyncio.run(_run())

        st.session_state["leads"] = leads
        st.success(f"Done — {len(leads)} leads generated.")

        # summary cards
        high   = [l for l in leads if l.opportunity_score and l.opportunity_score.priority.value == "high"]
        medium = [l for l in leads if l.opportunity_score and l.opportunity_score.priority.value == "medium"]
        track_a = [l for l in leads if l.track.value == "website_exists"]
        track_b = [l for l in leads if l.track.value == "no_website"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total leads", len(leads))
        c2.metric("🔴 High priority", len(high))
        c3.metric("Track A (has site)", len(track_a))
        c4.metric("Track B (no site)", len(track_b))

        # results table
        rows = []
        for l in sorted(leads, key=lambda x: x.opportunity_score.final_score if x.opportunity_score else 0, reverse=True):
            score = l.opportunity_score
            rows.append({
                "Business": l.business.name,
                "Industry": l.business.industry,
                "Track": "A: Website" if l.track.value == "website_exists" else "B: No Site",
                "Score": score.final_score if score else "—",
                "Priority": (score.priority.value if score else "—").upper(),
                "Contact": l.business.owner_email or l.business.owner_name or "—",
                "Email ready": "✓" if l.email_draft else "—",
            })

        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)

    elif "leads" not in st.session_state:
        st.info("Configure settings in the sidebar, then click **Run**.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Review Queue
# ════════════════════════════════════════════════════════════════════════════
with tab_queue:
    st.header("Review Queue")

    from config import settings
    from pipeline import ReviewQueue

    q = ReviewQueue(settings.review_queue_path)
    pending = q.list_pending()

    col_refresh, col_filter = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh"):
            pending = q.list_pending()

    with col_filter:
        priority_filter = st.selectbox(
            "Filter by priority", ["All", "HIGH", "MEDIUM", "LOW"], index=0
        )

    if priority_filter != "All":
        pending = [r for r in pending if r.get("priority", "").upper() == priority_filter]

    if not pending:
        st.info("No pending leads. Run the pipeline first.")
    else:
        st.write(f"**{len(pending)} leads** pending review")

        for r in sorted(pending, key=lambda x: x.get("score", 0), reverse=True):
            priority = r.get("priority", "low").upper()
            color = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚫"}.get(priority, "⚫")
            track_label = "Track B — No Site" if r["track"] == "no_website" else "Track A — Has Site"

            with st.expander(
                f"{color} **{r['business_name']}** · Score {r['score']} · {track_label}"
            ):
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Priority:** {priority}")
                    st.markdown(f"**Track:** {track_label}")
                    st.markdown(f"**Contact:** {r.get('owner_email') or r.get('owner_name') or '—'}")
                    st.markdown(f"**Enqueued:** {r.get('enqueued_at', '—')[:19]}")

                with col_b:
                    if r.get("email_subject"):
                        st.markdown(f"**Subject:** {r['email_subject']}")

                if r.get("email_body"):
                    st.text_area(
                        "Email Draft",
                        value=r["email_body"],
                        height=180,
                        key=f"body_{r['business_name']}",
                    )

                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("✅ Mark Sent", key=f"send_{r['business_name']}"):
                        q.mark_sent(r["business_name"])
                        st.success("Marked as sent")
                        st.rerun()
                with btn_col2:
                    if st.button("⏭ Skip", key=f"skip_{r['business_name']}"):
                        q.mark_skipped(r["business_name"])
                        st.info("Skipped")
                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Lead Detail
# ════════════════════════════════════════════════════════════════════════════
with tab_lead:
    st.header("Lead Detail")

    leads_in_session = st.session_state.get("leads", [])

    if not leads_in_session:
        st.info("Run the pipeline first to see lead details.")
    else:
        names = [l.business.name for l in leads_in_session]
        selected = st.selectbox("Select a lead", names)
        lead = next((l for l in leads_in_session if l.business.name == selected), None)

        if lead:
            b = lead.business
            score = lead.opportunity_score

            st.subheader(b.name)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Industry", b.industry.title())
            c2.metric("Track", "A — Website" if lead.track.value == "website_exists" else "B — No Site")
            c3.metric("Score", score.final_score if score else "—")
            c4.metric("Priority", score.priority.value.upper() if score else "—")

            st.divider()

            left, right = st.columns(2)

            with left:
                st.subheader("Business Info")
                st.markdown(f"**Phone:** {b.phone or '—'}")
                st.markdown(f"**Address:** {b.address or '—'}")
                st.markdown(f"**Website:** {b.website_url or 'None'}")
                st.markdown(f"**Google rating:** {b.google_rating or '—'} ({b.google_review_count or 0} reviews)")
                st.markdown(f"**Owner:** {b.owner_name or '—'}")
                st.markdown(f"**Email:** {b.owner_email or '—'}")

                if score and score.scoring_notes:
                    st.subheader("Scoring Notes")
                    for note in score.scoring_notes:
                        st.markdown(f"- {note}")

            with right:
                if lead.website_analysis:
                    a = lead.website_analysis
                    st.subheader("Website Analysis")
                    st.markdown(a.summary)
                    st.progress(a.website_score / 100, text=f"Website score: {a.website_score}/100")
                    if a.top_issues:
                        st.markdown("**Top Issues**")
                        for i in a.top_issues:
                            st.markdown(f"- ⚠️ {i}")
                    if a.quick_wins:
                        st.markdown("**Quick Wins**")
                        for w in a.quick_wins:
                            st.markdown(f"- ✅ {w}")

                elif lead.digital_gap_analysis:
                    g = lead.digital_gap_analysis
                    st.subheader("Digital Gap Analysis")
                    st.markdown(g.summary)
                    st.progress(g.no_website_score / 100, text=f"Opportunity score: {g.no_website_score}/100")

                    c1, c2 = st.columns(2)
                    c1.metric("Est. missed leads/mo", g.estimated_monthly_missed_leads)
                    c2.metric("Competitors with sites", f"{int(g.competitor_website_percentage*100)}%")

                    if g.visibility_gaps:
                        st.markdown("**Visibility Gaps**")
                        for v in g.visibility_gaps:
                            st.markdown(f"- 🔍 {v}")
                    if g.fast_capture_recommendations:
                        st.markdown("**Fast Capture Recs**")
                        for r in g.fast_capture_recommendations:
                            st.markdown(f"- 🚀 {r}")

            st.divider()
            st.subheader("Email Draft")
            if lead.email_draft:
                st.markdown(f"**Subject:** {lead.email_draft.subject}")
                st.text_area("Body", value=lead.email_draft.body, height=200, key="detail_body")
            else:
                st.info("No email draft generated (score below threshold or no Claude key).")
