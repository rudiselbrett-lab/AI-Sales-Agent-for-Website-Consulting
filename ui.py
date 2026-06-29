"""
Streamlit UI — SMB Sales Agent
Run with: streamlit run ui.py
"""

import asyncio
import os
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="SMB Sales Agent",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎯 SMB Sales Agent")
    st.caption("Charlotte, NC — Live Data")
    st.divider()

    from config import settings as cfg

    all_industries = [
        "plumber", "electrician", "hvac", "roofer", "landscaper",
        "auto-repair", "dentist", "chiropractor", "restaurant", "salon",
    ]
    selected_industries = st.multiselect(
        "Industries", all_industries, default=["plumber"]
    )
    limit = st.slider("Total businesses to scan", 1, 50, 5)
    stale_years = st.slider(
        "Flag sites older than (years)", 3, 20, cfg.stale_site_years,
        help="Sites with a copyright year older than this are marked as stale."
    )
    import os; os.environ["STALE_SITE_YEARS"] = str(stale_years)
    min_score = st.slider("Min opportunity score", 0, 100, 40)

    st.divider()
    debug_browser = st.toggle(
        "Show browser while scraping",
        value=False,
        help="Watch the scraper work in real time. Useful for debugging.",
    )

    st.divider()
    with st.expander("⚙️ Optional AI keys"):
        st.caption("Add these to get AI-scored analysis and personalised email copy. Not required to find businesses.")
        anthropic_key = st.text_input("Anthropic API Key", type="password",
                                       value=os.environ.get("ANTHROPIC_API_KEY", ""),
                                       placeholder="sk-ant-...")
        if anthropic_key:
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key

os.environ["MIN_OPPORTUNITY_SCORE"] = str(min_score)

# ── tabs ──────────────────────────────────────────────────────────────────────
tab_run, tab_analyze, tab_queue, tab_lead = st.tabs(["▶ Run", "🔬 Analyze", "📋 Review Queue", "🔍 Lead Detail"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Run
# ════════════════════════════════════════════════════════════════════════════
with tab_run:
    st.header("Find Charlotte SMBs")

    st.write(
        f"Scraping Google Maps for **{', '.join(selected_industries) or '—'}** "
        f"— **{limit}** businesses total."
    )

    run_btn = st.button("🚀 Run", type="primary", disabled=not selected_industries, use_container_width=True)

    if run_btn:
        from pipeline import PipelineOrchestrator
        from agents.google_maps_scraper import GoogleMapsScraper

        status = st.empty()

        async def _run():
            scraper = GoogleMapsScraper(
                headless=not debug_browser,
                slow_mo=300 if debug_browser else 0,
            )
            orchestrator = PipelineOrchestrator()
            orchestrator.prospector.scraper = scraper
            return await orchestrator.run(
                industries=selected_industries,
                total_limit=limit,
            )

        status.info("Scraping Google Maps… this takes 20–40 seconds per industry.")
        leads = asyncio.run(_run())
        st.session_state["leads"] = leads
        status.empty()

        if not leads:
            st.warning(
                "No businesses returned. Try enabling **Show browser while scraping** "
                "to see what's happening, then check data/debug/ for a screenshot."
            )
        else:
            track_a = [l for l in leads if l.track.value == "website_exists"]
            track_b = [l for l in leads if l.track.value == "no_website"]
            high    = [l for l in leads if l.opportunity_score and l.opportunity_score.priority.value == "high"]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Businesses found", len(leads))
            c2.metric("Have a website", len(track_a))
            c3.metric("No website", len(track_b))
            c4.metric("High priority", len(high))

            rows = []
            for l in sorted(leads, key=lambda x: x.opportunity_score.final_score if x.opportunity_score else 0, reverse=True):
                score = l.opportunity_score
                stale = ""
                if l.website_analysis:
                    if l.website_analysis.is_stale:
                        stale = f"Stale ({l.website_analysis.copyright_year or '?'})"
                    elif l.website_analysis.copyright_year:
                        stale = str(l.website_analysis.copyright_year)

                rows.append({
                    "Business": l.business.name,
                    "Industry": l.business.industry,
                    "Has website": "✓" if l.track.value == "website_exists" else "✗",
                    "Site age": stale or ("—" if l.track.value == "website_exists" else "N/A"),
                    "Mobile": "✓" if (l.website_analysis and l.website_analysis.has_mobile_viewport) else ("—" if l.track.value == "no_website" else "✗"),
                    "Score": score.final_score if score else "—",
                    "Priority": (score.priority.value if score else "—").upper(),
                    "Phone": l.business.phone or "—",
                    "Maps": l.business.google_maps_url or "—",
                })
            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Maps": st.column_config.LinkColumn("Maps", display_text="View →"),
                },
            )

    elif "leads" not in st.session_state:
        st.info("Pick your industries in the sidebar and hit **Run**. No API keys needed.")

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Analyze Selected
# ════════════════════════════════════════════════════════════════════════════
with tab_analyze:
    st.header("Analyze Selected Businesses")

    leads_for_analysis = st.session_state.get("leads", [])

    if not leads_for_analysis:
        st.info("Run the pipeline first, then come back here to analyze specific businesses.")
    else:
        st.caption("Pick the businesses you want to deep-analyze. The agent will visit their website (or confirm they have none) and score the quality.")

        options = [l.business.name for l in leads_for_analysis]
        selected_names = st.multiselect("Select businesses to analyze", options, default=options[:3])

        analyze_btn = st.button(
            f"🔬 Analyze {len(selected_names)} business{'es' if len(selected_names) != 1 else ''}",
            type="primary",
            disabled=not selected_names,
            use_container_width=True,
        )

        if analyze_btn and selected_names:
            from agents import WebsiteCrawlAgent, WebsiteAnalysisAgent, DigitalGapAnalysisAgent, OpportunityScoringEngine
            from agents.presence_reconstruction import PresenceReconstructionAgent

            crawler = WebsiteCrawlAgent()
            web_analyzer = WebsiteAnalysisAgent()
            gap_analyzer = DigitalGapAnalysisAgent()
            scorer = OpportunityScoringEngine()
            presence_agent = PresenceReconstructionAgent()

            targets = [l for l in leads_for_analysis if l.business.name in selected_names]

            progress = st.progress(0, text="Starting analysis…")
            results_placeholder = st.empty()

            async def _analyze_leads(leads):
                updated = []
                for i, lead in enumerate(leads):
                    progress.progress((i) / len(leads), text=f"Analyzing {lead.business.name}…")
                    try:
                        if lead.track.value == "website_exists" and lead.business.website_url:
                            crawl = await crawler.crawl(lead.business)
                            if crawl and crawl.pages:
                                website_analysis = await web_analyzer.analyze(lead.business, crawl)
                                digital_gap_analysis = None
                            else:
                                business = await presence_agent.reconstruct(lead.business)
                                website_analysis = None
                                digital_gap_analysis = await gap_analyzer.analyze(business)
                        else:
                            business = await presence_agent.reconstruct(lead.business)
                            website_analysis = None
                            digital_gap_analysis = await gap_analyzer.analyze(business)

                        score = scorer.score(
                            track=lead.track,
                            website_analysis=website_analysis,
                            digital_gap_analysis=digital_gap_analysis,
                        )
                        updated.append(lead.model_copy(update={
                            "website_analysis": website_analysis,
                            "digital_gap_analysis": digital_gap_analysis,
                            "opportunity_score": score,
                        }))
                    except Exception as exc:
                        st.warning(f"Could not analyze {lead.business.name}: {exc}")
                        updated.append(lead)
                return updated

            updated_leads = asyncio.run(_analyze_leads(targets))
            progress.progress(1.0, text="Done!")

            # Merge updated leads back into session state
            name_to_updated = {l.business.name: l for l in updated_leads}
            st.session_state["leads"] = [
                name_to_updated.get(l.business.name, l) for l in leads_for_analysis
            ]

            # Show results
            for lead in sorted(updated_leads, key=lambda x: x.opportunity_score.final_score if x.opportunity_score else 0, reverse=True):
                score = lead.opportunity_score
                wa = lead.website_analysis
                has_site = lead.track.value == "website_exists"

                priority_color = {"high": "🔴", "medium": "🟡", "low": "⚫"}.get(
                    score.priority.value if score else "low", "⚫"
                )
                with st.expander(
                    f"{priority_color} **{lead.business.name}** · {'Has site' if has_site else 'No site'} · Score {score.final_score if score else '—'}",
                    expanded=True,
                ):
                    if wa:
                        st.progress(wa.website_score / 100, text=f"Website score: {wa.website_score}/100")
                        if wa.is_stale:
                            st.error(f"⚠️ Stale site — {wa.age_label}")
                        elif wa.copyright_year:
                            st.warning(f"🕐 {wa.age_label}")

                        if wa.summary:
                            st.markdown(wa.summary)

                        col1, col2 = st.columns(2)
                        with col1:
                            if wa.top_issues:
                                st.markdown("**Issues**")
                                for issue in wa.top_issues:
                                    st.markdown(f"- ⚠️ {issue}")
                        with col2:
                            if wa.quick_wins:
                                st.markdown("**Quick wins**")
                                for win in wa.quick_wins:
                                    st.markdown(f"- ✅ {win}")

                        m1, m2, m3 = st.columns(3)
                        m1.metric("Mobile", "✓" if wa.has_mobile_viewport else "✗")
                        m2.metric("HTTPS", "✓" if wa.has_ssl else "✗")
                        m3.metric("Load time", f"{wa.load_time_seconds}s" if wa.load_time_seconds else "—")

                    elif lead.digital_gap_analysis:
                        g = lead.digital_gap_analysis
                        st.progress(g.no_website_score / 100, text=f"Opportunity score: {g.no_website_score}/100")
                        if g.summary:
                            st.markdown(g.summary)

        elif "leads" in st.session_state and not analyze_btn:
            st.info("Select businesses above and click **Analyze** to run a deep website audit.")


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Review Queue
# ════════════════════════════════════════════════════════════════════════════
with tab_queue:
    st.header("Review Queue")

    from config import settings
    from pipeline import ReviewQueue

    q = ReviewQueue(settings.review_queue_path)
    pending = q.list_pending()

    col_r, col_f = st.columns([1, 3])
    with col_r:
        if st.button("🔄 Refresh"):
            pending = q.list_pending()
    with col_f:
        priority_filter = st.selectbox("Filter", ["All", "HIGH", "MEDIUM", "LOW"])

    if priority_filter != "All":
        pending = [r for r in pending if r.get("priority", "").upper() == priority_filter]

    if not pending:
        st.info("No pending leads yet. Run the pipeline first.")
    else:
        st.write(f"**{len(pending)} leads** pending review")

        for idx, r in enumerate(sorted(pending, key=lambda x: x.get("score", 0), reverse=True)):
            priority = r.get("priority", "low").upper()
            color = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚫"}.get(priority, "⚫")
            has_site = r["track"] == "website_exists"
            track_label = "Has website" if has_site else "No website"

            with st.expander(f"{color} **{r['business_name']}** · {track_label} · Score {r['score']}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Priority:** {priority}")
                    st.markdown(f"**Has website:** {'Yes' if has_site else 'No'}")
                    st.markdown(f"**Contact:** {r.get('owner_email') or r.get('owner_name') or '—'}")

                with c2:
                    if r.get("email_subject"):
                        st.markdown(f"**Subject:** {r['email_subject']}")

                if r.get("email_body"):
                    st.text_area("Email Draft", value=r["email_body"], height=180,
                                 key=f"body_{idx}")

                b1, b2 = st.columns(2)
                with b1:
                    if st.button("✅ Mark Sent", key=f"send_{idx}"):
                        q.mark_sent(r["business_name"])
                        st.rerun()
                with b2:
                    if st.button("⏭ Skip", key=f"skip_{idx}"):
                        q.mark_skipped(r["business_name"])
                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Lead Detail
# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — Lead Detail
# ════════════════════════════════════════════════════════════════════════════
with tab_lead:
    st.header("Lead Detail")

    leads_in_session = st.session_state.get("leads", [])

    if not leads_in_session:
        st.info("Run the pipeline first.")
    else:
        selected = st.selectbox("Select a business", [l.business.name for l in leads_in_session])
        lead = next((l for l in leads_in_session if l.business.name == selected), None)

        if lead:
            b = lead.business
            score = lead.opportunity_score
            has_site = lead.track.value == "website_exists"

            # Header metrics
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Industry", b.industry.title())
            c2.metric("Has website", "Yes ✓" if has_site else "No ✗")
            c3.metric("Score", score.final_score if score else "—")
            c4.metric("Priority", score.priority.value.upper() if score else "—")

            st.divider()
            left, right = st.columns(2)

            with left:
                st.subheader("Business Info")
                if b.google_maps_url:
                    st.markdown(f"**[View on Google Maps →]({b.google_maps_url})**")
                st.markdown(f"**Phone:** {b.phone or '—'}")
                st.markdown(f"**Address:** {b.address or '—'}")
                st.markdown(f"**Website:** {b.website_url or 'None'}")
                st.markdown(f"**Google rating:** {b.google_rating or '—'} ({b.google_review_count or 0} reviews)")

                if score and score.scoring_notes:
                    st.subheader("Why this score")
                    for note in score.scoring_notes:
                        st.markdown(f"- {note}")

            with right:
                if lead.website_analysis:
                    a = lead.website_analysis
                    st.subheader("Website Analysis")

                    # Staleness badge
                    if a.is_stale:
                        st.error(f"⚠️ Stale website — {a.age_label}")
                    elif a.copyright_year:
                        st.warning(f"🕐 {a.age_label}")
                    else:
                        st.info("Age unknown — no copyright date found")

                    st.progress(a.website_score / 100, text=f"Website score: {a.website_score}/100")

                    if a.summary:
                        st.markdown(a.summary)

                    # Quick fact chips
                    fc1, fc2, fc3 = st.columns(3)
                    fc1.metric("Mobile ready", "✓" if a.has_mobile_viewport else "✗")
                    fc2.metric("HTTPS", "✓" if a.has_ssl else "✗")
                    fc3.metric("Load time", f"{a.load_time_seconds}s" if a.load_time_seconds else "—")

                    if a.top_issues:
                        st.markdown("**Issues found**")
                        for i in a.top_issues:
                            st.markdown(f"- ⚠️ {i}")
                    if a.quick_wins:
                        st.markdown("**Quick wins**")
                        for w in a.quick_wins:
                            st.markdown(f"- ✅ {w}")

                elif lead.digital_gap_analysis:
                    g = lead.digital_gap_analysis
                    st.subheader("No Website — Gap Analysis")
                    st.progress(g.no_website_score / 100, text=f"Opportunity score: {g.no_website_score}/100")
                    if g.summary:
                        st.markdown(g.summary)
                    c1, c2 = st.columns(2)
                    c1.metric("Est. missed leads/mo", g.estimated_monthly_missed_leads)
                    c2.metric("Competitors with sites", f"{int(g.competitor_website_percentage*100)}%")
                    if g.visibility_gaps:
                        st.markdown("**Visibility gaps**")
                        for v in g.visibility_gaps:
                            st.markdown(f"- 🔍 {v}")
                    if g.fast_capture_recommendations:
                        st.markdown("**What to do**")
                        for rec in g.fast_capture_recommendations:
                            st.markdown(f"- 🚀 {rec}")

            st.divider()
            st.subheader("Email Draft")
            if lead.email_draft:
                st.markdown(f"**Subject:** {lead.email_draft.subject}")
                st.text_area("Body", value=lead.email_draft.body, height=200, key="detail_body")
            else:
                st.caption("Add an Anthropic key in the sidebar to generate personalised email copy.")
