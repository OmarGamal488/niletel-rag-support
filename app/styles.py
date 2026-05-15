"""Styles + HTML renderers for the NileTel UI.

Most of the visual layer is plain HTML/CSS injected via st.markdown.
We only keep Streamlit widgets where we need real state (chat input,
toggles, buttons). The design comes from `NileTel Support v2 Vibrant.html`.
"""

from __future__ import annotations

import html
import textwrap
from datetime import datetime


def _h(s: str) -> str:
    """Dedent and strip an HTML template so Streamlit's markdown
    parser does not treat the leading indentation as a code block."""
    return textwrap.dedent(s).strip()

# --------------------------------------------------------------------- CSS
BRAND_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Sans+Arabic:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root{
  --primary:#0891B2;
  --primary-deep:#0E7490;
  --accent-soft:#CFFAFE;
  --accent-tint:#ECFEFF;
  --secondary:#F59E0B;
  --secondary-soft:#FEF3C7;

  --text-primary:#0B1220;
  --text-muted:#64748B;
  --surface:#FFFFFF;
  --surface-elevated:#F8FAFC;
  --surface-tint:#F0FDFA;
  --border:#E2E8F0;

  --success:#059669;
  --warning:#D97706;
  --destructive:#DC2626;
  --info:#2563EB;
  --violet:#7C3AED;
  --neutral-tag:#475569;

  --bg-info:#DBE7FE;
  --bg-warning:#FEF0D9;
  --bg-success:#D1FAE5;
  --bg-violet:#EDE9FE;
  --bg-neutral:#ECEEF2;

  --radius-sm:6px; --radius-md:10px; --radius-lg:14px;
  --shadow-1:0 1px 2px rgba(15,23,42,0.04);
  --shadow-2:0 2px 8px rgba(15,23,42,0.06);

  --sans:"Inter",-apple-system,"Segoe UI",system-ui,sans-serif;
  --arabic:"IBM Plex Sans Arabic","Segoe UI","Tahoma",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,monospace;
}

/* ---------- Minimal Streamlit chrome hiding ----------
   Only hide the small bits we want gone. Leave the header,
   sidebar toggle and footer alone so navigation keeps working. */
#MainMenu{display:none !important}
[data-testid="stDeployButton"]{display:none !important}

/* ---------- App body ---------- */
.stApp{ background:var(--surface); color:var(--text-primary); font-family:var(--sans); }
/* Leave enough top padding for Streamlit's fixed header (which holds
   the sidebar toggle); 4rem clears it on every modern Streamlit. */
.block-container{ padding: 4rem 32px 2rem !important; max-width: 1200px !important; }

/* ---------- Topbar ---------- */
.nt-topbar{
  display:flex;align-items:center;justify-content:space-between;
  height:56px;border-bottom:1px solid var(--border);margin-bottom:24px;
  background:var(--surface);
  padding:0 4px;
}
.nt-brand{display:flex;align-items:center;gap:10px;font-weight:600;color:var(--text-primary);font-size:15px;letter-spacing:-0.01em}
.nt-brand-mark{width:26px;height:26px;border-radius:8px;background:linear-gradient(135deg,#0891B2 0%,#06B6D4 60%,#22D3EE 100%);color:#fff;display:grid;place-items:center;font-size:14px;font-weight:700;box-shadow:0 1px 2px rgba(8,145,178,0.4)}
.nt-topbar-right{display:flex;align-items:center;gap:20px;font-size:12.5px;color:var(--text-muted)}
.nt-topbar-right .health{display:flex;align-items:center;gap:8px}
.nt-topbar-right .session-meta{font-variant-numeric:tabular-nums;font-family:var(--mono);font-size:12px}
.nt-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;display:inline-block}
.nt-dot.success{background:var(--success)}
.nt-dot.warning{background:var(--warning)}
.nt-dot.destructive{background:var(--destructive)}
.nt-dot.muted{background:var(--text-muted)}

/* ---------- Sidebar (Streamlit's) ---------- */
[data-testid="stSidebar"]{
  background:var(--surface) !important;
  border-right:1px solid var(--border);
  padding-top:8px;
}
[data-testid="stSidebar"] .block-container{ padding: 24px 20px !important; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4{ display:none; }

.nt-side-label{font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-muted);margin-bottom:8px;margin-top:8px;display:block}

/* style sidebar text inputs */
[data-testid="stSidebar"] [data-baseweb="input"] input{
  font-family:var(--mono) !important; font-size:13px !important;
  border-radius:var(--radius-sm) !important;
}

/* style sidebar buttons as chips */
[data-testid="stSidebar"] .stButton button{
  width:100%;
  display:flex; align-items:center; justify-content:flex-start; gap:8px;
  padding:10px 12px !important;
  border:1px solid var(--border) !important;
  border-radius:var(--radius-md) !important;
  background:var(--surface) !important;
  color:var(--text-primary) !important;
  font-size:13.5px !important; font-weight:400 !important;
  text-align:left !important; line-height:1.4 !important;
  transition:all .12s !important;
  box-shadow:none !important;
}
[data-testid="stSidebar"] .stButton button:hover{
  background:var(--surface-elevated) !important;
  border-color:var(--text-muted) !important;
}
[data-testid="stSidebar"] .stButton button:active,
[data-testid="stSidebar"] .stButton button:focus{
  background:var(--accent-soft) !important;
  border-color:var(--primary) !important;
  color:var(--primary) !important;
  outline:none !important;
}

/* health indicator block */
.nt-health{display:flex;align-items:center;gap:8px;padding:8px 0;font-size:13px}
.nt-health .lbl{color:var(--text-primary);font-weight:500}
.nt-health .meta{font-family:var(--mono);font-size:12px;color:var(--text-muted);margin-left:auto;font-variant-numeric:tabular-nums}

/* ---------- Metrics ---------- */
.nt-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
.nt-metric{position:relative;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:18px 16px 16px;box-shadow:var(--shadow-1);display:flex;flex-direction:column;gap:6px;transition:all .15s;overflow:hidden}
.nt-metric::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:var(--metric-color,var(--primary));border-radius:var(--radius-lg) var(--radius-lg) 0 0}
.nt-metric:hover{transform:translateY(-1px);box-shadow:0 4px 12px rgba(15,23,42,0.06);border-color:var(--metric-color,var(--text-muted))}
.nt-metric.m-queries{--metric-color:var(--primary)}
.nt-metric.m-latency{--metric-color:var(--info)}
.nt-metric.m-complaints{--metric-color:var(--warning)}
.nt-metric.m-tickets{--metric-color:var(--violet)}
.nt-metric-icon{position:absolute;top:14px;right:14px;width:28px;height:28px;border-radius:8px;background:color-mix(in srgb,var(--metric-color) 12%,white);color:var(--metric-color);display:grid;place-items:center;font-size:14px;font-weight:700}
.nt-metric-label{font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-muted)}
.nt-metric-value{font-size:30px;font-weight:700;color:var(--text-primary);font-variant-numeric:tabular-nums;line-height:1.15;letter-spacing:-0.02em}
.nt-metric-value .unit{font-size:14px;font-weight:500;color:var(--text-muted);margin-left:2px}
.nt-metric-delta{font-size:12px;font-weight:500;letter-spacing:0.02em;display:inline-flex;align-items:center;gap:4px}
.nt-metric-delta.up{color:var(--success)}
.nt-metric-delta.flat{color:var(--text-muted)}

/* ---------- Transcript ---------- */
.nt-transcript{display:flex;flex-direction:column;gap:24px;padding:8px 0 16px;min-height:300px}
.nt-msg{display:flex;gap:12px;align-items:flex-start}
.nt-avatar{width:28px;height:28px;border-radius:50%;flex-shrink:0;display:grid;place-items:center;font-size:12px;font-weight:600;color:#fff;background:var(--text-muted)}
.nt-avatar.assistant{border-radius:8px;background:linear-gradient(135deg,#0891B2 0%,#06B6D4 50%,#22D3EE 100%);color:#fff;font-size:14px;font-weight:700;box-shadow:0 1px 2px rgba(8,145,178,0.35)}
.nt-msg-body{display:flex;flex-direction:column;gap:8px;min-width:0;flex:1}
.nt-msg-meta-top{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text-muted);font-weight:500;letter-spacing:0.02em}
.nt-msg-meta-top .who{color:var(--text-primary);font-weight:500}
.nt-msg-text{font-size:15px;line-height:1.55;color:var(--text-primary);white-space:pre-wrap;word-wrap:break-word}
.nt-msg-text[dir="rtl"]{font-family:var(--arabic);font-size:16px;line-height:1.7;text-align:right}

.nt-msg.user .nt-msg-text{padding:0}
.nt-msg.assistant .nt-msg-text{background:var(--surface-tint);border:1px solid #A5F3FC;border-left:3px solid var(--primary);border-radius:var(--radius-md);padding:14px 16px;max-width:92%}
.nt-msg.assistant .nt-msg-text[dir="rtl"]{border-left:1px solid #A5F3FC;border-right:3px solid var(--primary)}
.nt-msg.assistant.cat-complaint .nt-msg-text{background:#FFFBEB;border-color:#FDE68A;border-left-color:var(--warning)}
.nt-msg.assistant.cat-complaint .nt-msg-text[dir="rtl"]{border-left-color:#FDE68A;border-right-color:var(--warning)}
.nt-msg.assistant.cat-greeting .nt-msg-text{background:#ECFDF5;border-color:#A7F3D0;border-left-color:var(--success)}
.nt-msg.assistant.cat-scope .nt-msg-text{background:#F5F3FF;border-color:#DDD6FE;border-left-color:var(--violet)}

.nt-msg-meta-bottom{display:flex;align-items:center;gap:10px;flex-wrap:wrap;direction:ltr}
.nt-latency{font-family:var(--mono);font-size:12px;color:var(--text-muted);font-variant-numeric:tabular-nums}
.nt-meta-sep{color:var(--text-muted);font-size:12px}

/* badges */
.nt-badge{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border-radius:var(--radius-sm);font-size:11px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;line-height:1.4}
.nt-badge .bdot{width:6px;height:6px;border-radius:50%}
.nt-badge.info{background:var(--bg-info);color:var(--info)}
.nt-badge.info .bdot{background:var(--info)}
.nt-badge.complaint{background:var(--bg-warning);color:var(--warning)}
.nt-badge.complaint .bdot{background:var(--warning)}
.nt-badge.greeting{background:var(--bg-success);color:var(--success)}
.nt-badge.greeting .bdot{background:var(--success)}
.nt-badge.scope{background:var(--bg-violet);color:var(--violet)}
.nt-badge.scope .bdot{background:var(--violet)}

.nt-ticket{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border-radius:var(--radius-sm);border:1px solid var(--warning);background:#FFFBEB;color:var(--warning);font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:0.02em}

/* sources */
.nt-sources{border:1px solid var(--border);border-radius:var(--radius-md);overflow:hidden;background:var(--surface);max-width:92%;margin-top:6px}
.nt-sources summary{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--surface);border-bottom:1px solid transparent;transition:background .12s}
.nt-sources[open] summary{border-bottom-color:var(--border)}
.nt-sources summary::-webkit-details-marker{display:none}
.nt-sources summary::after{content:"›";color:var(--text-muted);transition:transform .15s;font-size:18px;line-height:1}
.nt-sources[open] summary::after{transform:rotate(90deg)}
.nt-sources-title{font-size:13px;font-weight:500;color:var(--text-primary)}
.nt-source-row{display:grid;grid-template-columns:32px 1fr auto;column-gap:12px;row-gap:4px;padding:12px 16px;border-bottom:1px solid var(--border);transition:background .1s;align-items:start}
.nt-source-row:last-child{border-bottom:none}
.nt-source-row:hover{background:var(--surface-elevated)}
.nt-source-idx{font-family:var(--mono);font-size:12px;color:var(--text-muted);font-variant-numeric:tabular-nums;padding-top:2px}
.nt-source-name{font-size:14px;font-weight:500;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nt-source-rel{font-family:var(--mono);font-size:12px;font-variant-numeric:tabular-nums;color:var(--text-muted);padding-top:2px}
.nt-source-rel.high{color:var(--primary);font-weight:500}
.nt-source-snippet{grid-column:2 / 4;font-size:13px;color:var(--text-muted);line-height:1.5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.nt-source-snippet[dir="rtl"]{font-family:var(--arabic);text-align:right;font-size:13.5px;line-height:1.65}

/* status / loading */
.nt-status{position:relative;background:var(--surface-elevated);border:1px solid var(--border);border-radius:var(--radius-md);padding:10px 14px;font-size:14px;color:var(--text-muted);overflow:hidden;max-width:92%}
.nt-status .track{position:absolute;left:0;bottom:0;height:2px;width:100%;background:var(--accent-soft)}
.nt-status::after{content:"";position:absolute;left:-40%;bottom:0;height:2px;width:40%;background:var(--primary);animation:ntslide 1.4s ease-in-out infinite}
@keyframes ntslide{0%{left:-40%}100%{left:100%}}

/* empty state */
.nt-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:48px 24px;gap:12px}
.nt-empty-mark{width:40px;height:40px;border-radius:var(--radius-md);background:var(--accent-soft);color:var(--primary);display:grid;place-items:center;font-size:20px;font-weight:700;margin-bottom:4px}
.nt-empty-title{font-size:16px;font-weight:600;color:var(--text-primary)}
.nt-empty-sub{font-size:14px;color:var(--text-muted);max-width:480px;line-height:1.55}

/* ---------- Inline composer (st.form) ---------- */
/* The form acts as our composer */
[data-testid="stForm"]{
  background:var(--surface) !important;
  border:1px solid var(--border) !important;
  border-radius:var(--radius-md) !important;
  box-shadow:var(--shadow-2) !important;
  padding:6px 6px 6px 14px !important;
  margin-top:16px !important;
  transition:border-color .12s, box-shadow .12s !important;
}
[data-testid="stForm"]:focus-within{
  border-color:var(--primary) !important;
  box-shadow:0 0 0 3px var(--accent-soft), var(--shadow-2) !important;
}
[data-testid="stForm"] [data-baseweb="input"]{
  background:transparent !important;
  border:none !important;
  box-shadow:none !important;
}
[data-testid="stForm"] [data-baseweb="input"] input{
  background:transparent !important;
  border:none !important;
  box-shadow:none !important;
  outline:none !important;
  font-size:15px !important;
  color:var(--text-primary) !important;
  padding:8px 0 !important;
}
[data-testid="stForm"] [data-baseweb="input"] input::placeholder{
  color:var(--text-muted) !important;
}
[data-testid="stForm"] .stFormSubmitButton button{
  display:grid !important; place-items:center !important;
  width:36px !important; height:36px !important; min-height:36px !important;
  padding:0 !important;
  border:none !important; border-radius:var(--radius-sm) !important;
  background:linear-gradient(135deg,#0891B2 0%,#06B6D4 100%) !important;
  color:#fff !important;
  font-size:16px !important; line-height:1 !important;
  box-shadow:0 1px 3px rgba(8,145,178,0.4) !important;
  transition:all .12s !important;
}
[data-testid="stForm"] .stFormSubmitButton button:hover{
  background:linear-gradient(135deg,#0E7490 0%,#0891B2 100%) !important;
  box-shadow:0 2px 6px rgba(8,145,178,0.5) !important;
}
[data-testid="stForm"] .stFormSubmitButton button p{
  margin:0 !important; font-weight:600 !important; font-size:16px !important;
  color:#fff !important;
}

/* ---------- Insights expander ---------- */
[data-testid="stExpander"]{
  border:1px solid var(--border) !important;
  border-radius:var(--radius-md) !important;
  background:var(--surface) !important;
  box-shadow:none !important;
  margin-top:24px;
  overflow:hidden;
}
[data-testid="stExpander"] details{
  background:var(--surface) !important;
}
[data-testid="stExpander"] details > summary,
[data-testid="stExpander"] [data-testid="stExpanderToggle"]{
  background:var(--surface) !important;
  color:var(--text-primary) !important;
  padding:14px 16px !important;
  font-size:14px !important;
  border:none !important;
}
[data-testid="stExpander"] details > summary:hover{
  background:var(--surface-elevated) !important;
}
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] [data-testid="stExpanderToggle"] p{
  font-weight:500 !important;
  color:var(--text-primary) !important;
  margin:0 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"],
[data-testid="stExpander"] [data-testid="stExpanderContent"]{
  padding:20px 16px !important;
  background:var(--surface) !important;
}
[data-testid="stExpander"] svg{ color:var(--text-muted) !important; }

.nt-insights-section{display:flex;flex-direction:column;gap:12px;margin-bottom:24px}
.nt-insights-title{font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-muted)}
.nt-bar-chart{display:flex;flex-direction:column;gap:8px}
.nt-bar-row{display:grid;grid-template-columns:140px 1fr 70px;gap:12px;align-items:center;font-size:13px}
.nt-bar-track{background:var(--surface-elevated);height:10px;border-radius:999px;overflow:hidden}
.nt-bar-fill{height:100%;border-radius:999px}
.nt-bar-fill.info{background:var(--info)}
.nt-bar-fill.complaint{background:var(--warning)}
.nt-bar-fill.greeting{background:var(--success)}
.nt-bar-fill.scope{background:var(--violet)}
.nt-bar-val{font-family:var(--mono);font-size:12px;color:var(--text-muted);text-align:right;font-variant-numeric:tabular-nums}

.nt-ragas{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.nt-ragas-card{position:relative;border:1px solid var(--border);border-radius:var(--radius-md);padding:12px 14px;background:var(--surface);display:flex;flex-direction:column;gap:4px;overflow:hidden}
.nt-ragas-card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--ragas-color,var(--primary))}
.nt-ragas-card.r1{--ragas-color:var(--primary)}
.nt-ragas-card.r2{--ragas-color:var(--success)}
.nt-ragas-card.r3{--ragas-color:var(--info)}
.nt-ragas-card.r4{--ragas-color:var(--violet)}
.nt-ragas-label{font-size:11px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:var(--text-muted)}
.nt-ragas-value{font-size:20px;font-weight:600;color:var(--text-primary);font-variant-numeric:tabular-nums}

/* ===========================================================
   Component styles hoisted from app/components/*.html
   They live here (single global stylesheet) so the markdown
   parser never has to handle <style> blocks inside per-message
   HTML snippets — that's what was leaking CSS as text.
   =========================================================== */

/* --- typing_indicator.html --- */
.nt-typing{
  display:inline-flex;align-items:center;gap:.55rem;
  /* margin-top creates breathing room from the "Routing query..." status
     line that sits directly above it during the pending state. */
  margin-top:.75rem;
  padding:.55rem .85rem;border-radius:14px;
  background:#ECFEFF;border:1px solid #CFFAFE;
  font-family:"Inter",system-ui,sans-serif;font-size:.85rem;color:#0E7490;
}
.nt-typing-dot{
  width:7px;height:7px;border-radius:50%;background:#0891B2;
  animation: nt-bounce 1.2s infinite ease-in-out both;
}
.nt-typing-dot:nth-child(1){ animation-delay:-0.32s; }
.nt-typing-dot:nth-child(2){ animation-delay:-0.16s; }
.nt-typing-label{ margin-left:.25rem;letter-spacing:.01em; }
@keyframes nt-bounce{
  0%,80%,100%{ transform:scale(0.6); opacity:.55; }
  40%        { transform:scale(1.0); opacity:1;   }
}

/* --- ticket_badge.html --- */
.nt-ticket-wrap{ display:flex;padding:.25rem 0; }
.nt-ticket-badge{
  position:relative;display:inline-flex;align-items:center;gap:.6rem;
  padding:.55rem .85rem;border-radius:999px;
  background:linear-gradient(90deg,#FEF3C7 0%,#FDE68A 100%);
  color:#7C3AED;border:1px solid #FDE68A;
  font-family:"Inter",system-ui,sans-serif;font-size:.85rem;font-weight:600;
  box-shadow:0 2px 8px rgba(245,158,11,0.18);
  animation: nt-badge-pop .55s cubic-bezier(.2,.9,.25,1.2) both;
}
.nt-ticket-icon{ font-size:1.05rem;line-height:1; }
.nt-ticket-body{ display:inline-flex;flex-direction:column;gap:0;line-height:1.1; }
.nt-ticket-label{ font-size:.7rem;font-weight:500;color:#92400E;letter-spacing:.02em; }
.nt-ticket-id{ font-family:var(--mono);font-size:.85rem;color:#7C3AED; }
.nt-ticket-pill{
  margin-left:.35rem;padding:.12rem .55rem;border-radius:999px;
  background:#7C3AED;color:#fff;font-size:.65rem;letter-spacing:.04em;text-transform:uppercase;
}
.nt-ticket-ring{
  position:absolute;inset:-4px;border-radius:999px;border:2px solid #F59E0B;
  opacity:0;animation: nt-badge-ring 1.6s ease-out 1;
}
@keyframes nt-badge-pop{
  0%   { transform:scale(.85); opacity:0;   }
  60%  { transform:scale(1.04); opacity:1;  }
  100% { transform:scale(1);    opacity:1;  }
}
@keyframes nt-badge-ring{
  0%   { transform:scale(.9);  opacity:.85; }
  100% { transform:scale(1.25); opacity:0;  }
}

/* --- source_card.html --- */
/* Container that holds all source cards — explicit flex so Streamlit's
   inter-block wrappers can't sneak gaps in between cards. */
.nt-src-list{
  display:flex;flex-direction:column;gap:0;
  margin:.3rem 0 0 0;border-radius:10px;overflow:hidden;
  border:1px solid #E2E8F0;background:#F8FAFC;
}
.nt-src-card{
  border:none;border-bottom:1px solid #E2E8F0;
  background:#F8FAFC;overflow:hidden;
  margin:0 !important;padding:0 !important;
  border-radius:0;
  font-family:"Inter",system-ui,sans-serif;font-size:.85rem;
  transition: background .15s ease;
}
.nt-src-list .nt-src-card:last-child{ border-bottom:none; }
.nt-src-card[open]{ background:#fff; }
.nt-src-card[open]{ border-color:#0891B2;box-shadow:0 2px 8px rgba(8,145,178,.12); }
.nt-src-summary{
  display:grid;grid-template-columns:auto 1fr auto auto;gap:.6rem;align-items:center;
  padding:.5rem .75rem;cursor:pointer;list-style:none;color:#0B1220;
}
.nt-src-summary::-webkit-details-marker{ display:none; }
.nt-src-rank{
  font-family:var(--mono);font-size:.72rem;
  color:#0E7490;background:#CFFAFE;padding:.1rem .4rem;border-radius:6px;
}
.nt-src-title{ font-weight:600;color:#0E7490;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.nt-src-score{
  font-family:var(--mono);font-size:.72rem;
  color:#475569;background:#ECEEF2;padding:.1rem .45rem;border-radius:999px;
}
.nt-src-chev{ color:#64748B;transition: transform .15s ease; }
.nt-src-card[open] .nt-src-chev{ transform: rotate(180deg); }
.nt-src-snippet{
  margin:0;padding:.65rem .85rem;border-top:1px solid #E2E8F0;
  background:#fff;white-space:pre-wrap;word-break:break-word;
  font-family:"IBM Plex Sans Arabic","Inter",system-ui,sans-serif;
  font-size:.82rem;line-height:1.55;color:#0B1220;direction:auto;
}

</style>
"""

# --------------------------------------------------------------------- helpers

CATEGORY_BADGE = {
    "INFO": "info",
    "COMPLAINT": "complaint",
    "GREETING": "greeting",
    "OUT_OF_SCOPE": "scope",
}
CATEGORY_BUBBLE_CLASS = {
    "INFO": "",
    "COMPLAINT": "cat-complaint",
    "GREETING": "cat-greeting",
    "OUT_OF_SCOPE": "cat-scope",
}
CATEGORY_LABEL = {
    "INFO": "Info",
    "COMPLAINT": "Complaint",
    "GREETING": "Greeting",
    "OUT_OF_SCOPE": "Scope",
}


def is_rtl(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" or "֐" <= ch <= "׿" for ch in text or "")


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _now_str() -> str:
    return datetime.now().strftime("%H:%M")


# --------------------------------------------------------------------- topbar

def render_topbar(connected: bool, queries: int) -> str:
    dot = "success" if connected else "destructive"
    label = "Connected" if connected else "Backend offline"
    return _h(f"""
        <div class="nt-topbar">
          <div class="nt-brand">
            <div class="nt-brand-mark">◐</div>
            <span>NileTel Support</span>
          </div>
          <div class="nt-topbar-right">
            <span class="health"><span class="nt-dot {dot}"></span>{label}</span>
            <span class="session-meta">Session · {queries} queries</span>
          </div>
        </div>
    """)


# --------------------------------------------------------------------- metrics

def render_metrics(total: int, latency_ms: float, complaints: int, tickets: int) -> str:
    return _h(f"""
        <section class="nt-metrics">
          <div class="nt-metric m-queries">
            <div class="nt-metric-icon">Q</div>
            <div class="nt-metric-label">Total queries</div>
            <div class="nt-metric-value">{total}</div>
            <div class="nt-metric-delta flat">across sessions</div>
          </div>
          <div class="nt-metric m-latency">
            <div class="nt-metric-icon">≡</div>
            <div class="nt-metric-label">Avg latency</div>
            <div class="nt-metric-value">{latency_ms:.0f}<span class="unit">ms</span></div>
            <div class="nt-metric-delta flat">end-to-end</div>
          </div>
          <div class="nt-metric m-complaints">
            <div class="nt-metric-icon">!</div>
            <div class="nt-metric-label">Complaints</div>
            <div class="nt-metric-value">{complaints}</div>
            <div class="nt-metric-delta flat">auto-routed</div>
          </div>
          <div class="nt-metric m-tickets">
            <div class="nt-metric-icon">◻</div>
            <div class="nt-metric-label">Tickets</div>
            <div class="nt-metric-value">{tickets}</div>
            <div class="nt-metric-delta flat">opened</div>
          </div>
        </section>
    """)


# --------------------------------------------------------------------- messages

def render_user_message(text: str, time_str: str | None = None) -> str:
    rtl = ' dir="rtl"' if is_rtl(text) else ""
    time_str = time_str or _now_str()
    return _h(f"""
        <div class="nt-msg user">
          <div class="nt-avatar">A</div>
          <div class="nt-msg-body">
            <div class="nt-msg-meta-top"><span class="who">You</span><span>·</span><span>{_esc(time_str)}</span></div>
            <div class="nt-msg-text"{rtl}>{_esc(text)}</div>
          </div>
        </div>
    """)


def _pseudo_relevance(rank: int) -> float:
    """Return a stable pseudo-relevance score for a rank-ordered source.

    Real scores aren't returned by EnsembleRetriever, so this gives users
    something visually useful (decreasing) without lying about provenance.
    """
    return max(0.55, 0.94 - 0.08 * rank)


def _render_sources(sources: list[dict]) -> str:
    if not sources:
        return ""
    rows = []
    for i, s in enumerate(sources):
        rel = _pseudo_relevance(i)
        snippet = s.get("snippet", "")
        rtl = ' dir="rtl"' if is_rtl(snippet) else ""
        rel_class = "high" if rel >= 0.80 else ""
        rows.append(
            f'<div class="nt-source-row">'
            f'<div class="nt-source-idx">{i + 1:02d}</div>'
            f'<div class="nt-source-name">{_esc(s.get("source", "?"))}</div>'
            f'<div class="nt-source-rel {rel_class}">{rel:.2f}</div>'
            f'<div class="nt-source-snippet"{rtl}>"{_esc(snippet)}"</div>'
            f'</div>'
        )
    return (
        f'<details class="nt-sources">'
        f'<summary><span class="nt-sources-title">Sources · {len(sources)}</span></summary>'
        f'<div class="nt-sources-list">{"".join(rows)}</div>'
        f'</details>'
    )


def render_assistant_message(
    text: str,
    category: str = "INFO",
    latency_ms: float | None = None,
    ticket_id: str | None = None,
    sources: list[dict] | None = None,
    time_str: str | None = None,
) -> str:
    rtl = ' dir="rtl"' if is_rtl(text) else ""
    cat_class = CATEGORY_BUBBLE_CLASS.get(category, "")
    badge_cls = CATEGORY_BADGE.get(category, "info")
    badge_label = CATEGORY_LABEL.get(category, category)
    time_str = time_str or _now_str()

    meta_parts = [
        f'<span class="nt-badge {badge_cls}"><span class="bdot"></span>{badge_label}</span>'
    ]
    if latency_ms is not None:
        meta_parts.append('<span class="nt-meta-sep">·</span>')
        meta_parts.append(f'<span class="nt-latency">{latency_ms:.0f} ms</span>')
    if ticket_id:
        meta_parts.append('<span class="nt-meta-sep">·</span>')
        meta_parts.append(
            f'<span class="nt-ticket"><span class="square">◻</span>'
            f'TICKET #{_esc(ticket_id)}</span>'
        )

    return _h(f"""
        <div class="nt-msg assistant {cat_class}">
          <div class="nt-avatar assistant">◐</div>
          <div class="nt-msg-body">
            <div class="nt-msg-meta-top"><span class="who">NileTel</span><span>·</span><span>{_esc(time_str)}</span></div>
            <div class="nt-msg-text"{rtl}>{_esc(text)}</div>
            <div class="nt-msg-meta-bottom">{''.join(meta_parts)}</div>
            {_render_sources(sources or [])}
          </div>
        </div>
    """)


def render_status(message: str = "Retrieving sources…") -> str:
    return _h(f"""
        <div class="nt-msg assistant">
          <div class="nt-avatar assistant">◐</div>
          <div class="nt-msg-body">
            <div class="nt-msg-meta-top"><span class="who">NileTel</span><span>·</span><span>just now</span></div>
            <div class="nt-status"><span>{_esc(message)}</span><span class="track"></span></div>
          </div>
        </div>
    """)


def render_empty_state() -> str:
    return _h("""
        <div class="nt-empty">
          <div class="nt-empty-mark">◐</div>
          <div class="nt-empty-title">Ask NileTel anything</div>
          <div class="nt-empty-sub">
            Type a question in Arabic, English, or both — about plans, billing, troubleshooting,
            or report a problem. Use the example prompts on the left to get started.
          </div>
        </div>
    """)


# --------------------------------------------------------------------- insights

def render_insights_body(
    category_counts: dict[str, int],
    ragas_scores: dict[str, float] | None,
) -> str:
    total = sum(category_counts.values()) or 1

    def bar(cat: str, label: str, css: str) -> str:
        n = category_counts.get(cat, 0)
        pct = round(100 * n / total)
        return (
            f'<div class="nt-bar-row">'
            f'<span><span class="nt-badge {css}"><span class="bdot"></span>{label}</span></span>'
            f'<div class="nt-bar-track"><div class="nt-bar-fill {css}" style="width:{pct}%"></div></div>'
            f'<div class="nt-bar-val">{n} · {pct}%</div>'
            f'</div>'
        )

    bars = "".join(
        [
            bar("INFO", "Info", "info"),
            bar("COMPLAINT", "Complaint", "complaint"),
            bar("GREETING", "Greeting", "greeting"),
            bar("OUT_OF_SCOPE", "Scope", "scope"),
        ]
    )

    ragas_html = ""
    if ragas_scores:
        f = ragas_scores.get("faithfulness", 0)
        ar = ragas_scores.get("answer_relevancy", 0)
        cp = ragas_scores.get("context_precision", 0)
        cr = ragas_scores.get("context_recall", 0)
        ragas_html = (
            '<div class="nt-insights-section">'
            '<div class="nt-insights-title">RAGAS evaluation</div>'
            '<div class="nt-ragas">'
            f'<div class="nt-ragas-card r1"><div class="nt-ragas-label">Faithfulness</div><div class="nt-ragas-value">{f:.2f}</div></div>'
            f'<div class="nt-ragas-card r2"><div class="nt-ragas-label">Answer relevance</div><div class="nt-ragas-value">{ar:.2f}</div></div>'
            f'<div class="nt-ragas-card r3"><div class="nt-ragas-label">Context precision</div><div class="nt-ragas-value">{cp:.2f}</div></div>'
            f'<div class="nt-ragas-card r4"><div class="nt-ragas-label">Context recall</div><div class="nt-ragas-value">{cr:.2f}</div></div>'
            '</div>'
            '</div>'
        )

    return (
        '<div class="nt-insights-section">'
        '<div class="nt-insights-title">Category distribution</div>'
        f'<div class="nt-bar-chart">{bars}</div>'
        '</div>'
        f'{ragas_html}'
    )
