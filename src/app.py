"""
Parking Congestion Intelligence - multipage Streamlit app (dark / deck.gl 3D).

Run:  streamlit run src/app.py

Pages:
  - Dashboard      : interactive 3D hotspot map, KPIs, ranked zones, drill-down
  - How it works   : methodology, CIS scoring model, glossary, caveats
"""
import streamlit as st

from common import inject_css, sidebar_brand

st.set_page_config(page_title="Parking Congestion Intelligence", layout="wide")
inject_css()
sidebar_brand()

dashboard = st.Page("views/dashboard.py", title="Dashboard", default=True)
deployment = st.Page("views/deployment.py", title="Deployment")
docs = st.Page("views/docs.py", title="How it works")

pg = st.navigation({"Parking Intel": [dashboard, deployment, docs]})

st.sidebar.divider()
st.sidebar.caption("Hackathon - AI-driven parking intelligence")

pg.run()
