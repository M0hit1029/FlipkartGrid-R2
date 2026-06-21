"""Shared paths, data loading and styling for all dashboard pages."""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean.parquet"
HEX = ROOT / "data" / "hotspots.parquet"

DAYPARTS = ["Morning peak (7-11)", "Midday (11-16)",
            "Evening peak (16-21)", "Night (21-7)"]


@st.cache_data
def load():
    return pd.read_parquet(CLEAN), pd.read_parquet(HEX)


def inject_css():
    st.html(
        """
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
          :root {
            --bg:#0b0d13; --panel:#141722; --panel-2:#1a1e2b;
            --line:#262b3a; --line-2:#2f3547;
            --txt:#e8eaf0; --muted:#9aa0b4; --muted-2:#6b7185;
            --accent:#ff5a5f; --accent-2:#ff8a4c;
            --green:#3fc850; --amber:#e0b020;
          }
          html, body, [class*="css"] { font-family:'Inter',sans-serif; }

          .stApp {
            background:
              radial-gradient(900px 500px at 12% -8%, rgba(255,90,95,0.10), transparent 60%),
              radial-gradient(800px 500px at 100% 0%, rgba(255,138,76,0.08), transparent 55%),
              var(--bg);
          }
          .block-container { padding-top:2rem; padding-bottom:2rem; max-width:1500px; }

          h1 { font-weight:800; letter-spacing:-1px; }
          h2, h3 { font-weight:700; letter-spacing:-0.4px; }
          h2 { font-size:1.15rem !important; margin-top:0.4rem; }

          /* ---------- KPI metric cards ---------- */
          div[data-testid="stMetric"] {
            background:linear-gradient(165deg, var(--panel-2), var(--panel));
            border:1px solid var(--line); border-radius:16px;
            padding:16px 18px; box-shadow:0 6px 18px rgba(0,0,0,0.28);
            transition:transform .15s ease, border-color .15s ease;
          }
          div[data-testid="stMetric"]:hover {
            transform:translateY(-2px); border-color:var(--line-2);
          }
          div[data-testid="stMetricValue"] {
            font-size:1.8rem; font-weight:800;
            background:linear-gradient(90deg,#ff7a6e,#ff8a4c);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
          }
          div[data-testid="stMetricLabel"] p {
            color:var(--muted); font-weight:600; font-size:0.8rem;
            text-transform:uppercase; letter-spacing:0.4px;
          }

          /* ---------- sidebar ---------- */
          section[data-testid="stSidebar"] {
            background:linear-gradient(180deg,#121521,#0d0f17);
            border-right:1px solid var(--line);
          }
          section[data-testid="stSidebar"] .block-container { padding-top:1.1rem; }

          /* sidebar nav links */
          section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] {
            border-radius:10px; margin:2px 0; padding:6px 10px;
          }
          section[data-testid="stSidebar"] a[aria-current="page"] {
            background:rgba(255,90,95,0.14);
            border:1px solid rgba(255,90,95,0.35);
          }

          /* filter section label */
          .filt-label {
            font-size:0.72rem; font-weight:700; letter-spacing:1px;
            text-transform:uppercase; color:var(--muted);
            margin:14px 0 4px 2px;
          }
          .filt-card {
            background:rgba(255,255,255,0.02);
            border:1px solid var(--line); border-radius:14px;
            padding:12px 12px 4px 12px; margin-bottom:6px;
          }

          /* ---------- multiselect tags as accent pills ---------- */
          span[data-baseweb="tag"] {
            background:linear-gradient(90deg, rgba(255,90,95,0.9), rgba(255,138,76,0.9))
              !important;
            border-radius:20px !important; color:#11131a !important;
            font-weight:600 !important;
          }
          span[data-baseweb="tag"] span[role="presentation"] svg { fill:#11131a; }
          div[data-baseweb="select"] > div {
            background:var(--panel) !important; border-radius:12px !important;
            border:1px solid var(--line) !important;
          }

          /* ---------- pills / segmented control ---------- */
          button[kind="pills"], button[kind="pillsActive"],
          div[data-testid="stSegmentedControl"] button {
            border-radius:20px !important; font-weight:600 !important;
          }
          button[kind="pillsActive"],
          div[data-testid="stSegmentedControl"] button[aria-checked="true"] {
            background:linear-gradient(90deg, var(--accent), var(--accent-2)) !important;
            color:#11131a !important; border:none !important;
          }

          /* ---------- sliders ---------- */
          div[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] {
            background:var(--accent) !important; border-color:var(--accent) !important;
          }

          /* ---------- expanders ---------- */
          details[data-testid="stExpander"], div[data-testid="stExpander"] {
            border:1px solid var(--line) !important; border-radius:14px !important;
            background:rgba(255,255,255,0.015);
          }

          /* ---------- buttons / download ---------- */
          div[data-testid="stDownloadButton"] button,
          .stButton button {
            background:linear-gradient(90deg, var(--accent), var(--accent-2));
            color:#11131a; font-weight:700; border:none; border-radius:12px;
            padding:8px 16px;
          }
          div[data-testid="stDownloadButton"] button:hover { filter:brightness(1.07); }

          /* ---------- alerts ---------- */
          div[data-testid="stAlert"] { border-radius:14px; }

          /* legend chips */
          .legend span { display:inline-block; padding:3px 11px; margin:2px 5px 2px 0;
            border-radius:20px; font-size:0.76rem; color:#11131a; font-weight:700; }

          /* hero subtitle */
          .hero-sub { color:var(--muted); font-size:0.95rem; margin:-6px 0 6px 0; }
          /* section divider spacing */
          hr { border-color:var(--line) !important; }
        </style>
        """
    )


def sidebar_brand():
    with st.sidebar:
        st.html(
            """
        <div style="display:flex;align-items:center;gap:11px;
                    padding:4px 4px 16px 4px;">
          <div style="width:38px;height:38px;border-radius:11px;
               background:linear-gradient(135deg,#ff5a5f,#ff8a4c);
               display:flex;align-items:center;justify-content:center;
               font-weight:800;color:#11131a;font-size:1.15rem;
               box-shadow:0 4px 14px rgba(255,90,95,0.35);">P</div>
          <div>
            <div style="font-size:1.12rem;font-weight:800;letter-spacing:-0.4px;
                 line-height:1.05;">Parking Intel</div>
            <div style="color:#9aa0b4;font-size:0.74rem;margin-top:1px;">
              Bengaluru congestion intelligence</div>
          </div>
        </div>
        """
        )


def section_label(text):
    """Small uppercase label used above filter groups."""
    st.html(f'<div class="filt-label">{text}</div>')
