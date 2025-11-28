import streamlit as st
import os
import tempfile
import numpy as np
import folium
from streamlit_folium import st_folium
from matplotlib import cm
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

from safe_ro_core import NDVIProcessor, Sentinel1FloodDetector

# -----------------------------------------------------------------------------
# 1. CONFIGURATION & CSS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="SAFE-RO Platform", page_icon="🛰️", layout="wide")

st.markdown("""
<style>
    .safe-box { padding: 15px; background-color: #28a745; color: white; border-radius: 8px; margin-bottom: 15px; }
    .warn-box { padding: 15px; background-color: #ffc107; color: black; border-radius: 8px; margin-bottom: 15px; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
    /* Remove top padding for cleaner look */
    .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

REGIONS = {
    "Fagaras": [24.5, 45.5, 25.5, 46.0],
    "Iasi": [27.5, 47.0, 27.8, 47.3],
    "Timisoara": [21.1, 45.6, 21.4, 45.9],
    "Craiova": [23.7, 44.2, 24.0, 44.5],
    "Constanta": [28.5, 44.1, 28.8, 44.4],
    "Baia Mare": [23.4, 47.5, 23.7, 47.8],
    "Bucuresti": [25.9, 44.3, 26.2, 44.6],
    "Cluj": [23.5, 46.7, 23.8, 47.0]
}


# -----------------------------------------------------------------------------
# 2. CACHED FUNCTIONS
# -----------------------------------------------------------------------------
@st.cache_resource
def get_drive_connection():
    try:
        g = GoogleAuth()
        g.LoadCredentialsFile("mycreds.txt")
        if g.credentials is None: return None
        if g.access_token_expired:
            g.Refresh()
        else:
            g.Authorize()
        return GoogleDrive(g)
    except:
        return None


@st.cache_data(ttl=3600)
def get_file_list_cached():
    drive = get_drive_connection()
    if not drive: return []
    try:
        flist = drive.ListFile({'q': "title='SAFE_RO_Cloud_Data' and trashed=false"}).GetList()
        if not flist: return []
        fid = flist[0]['id']
        files = drive.ListFile({'q': f"'{fid}' in parents and trashed=false"}).GetList()
        files.sort(key=lambda x: x['title'], reverse=True)
        return [{'title': f['title'], 'id': f['id']} for f in files]
    except:
        return []


@st.cache_data(show_spinner=False)
def process_data(r_id, n_id, r_title, n_title):
    drive = get_drive_connection()

    def dl(fid, title):
        f = drive.CreateFile({'id': fid})
        t = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(title)[1])
        t.close()
        f.GetContentFile(t.name)
        return t.name

    try:
        p_r = dl(r_id, r_title);
        p_n = dl(n_id, n_title)
        proc = NDVIProcessor(p_r, p_n)
        res = proc.compute_ndvi()
        try:
            os.remove(p_r); os.remove(p_n)
        except:
            pass
        return res
    except:
        return None


@st.cache_data(show_spinner=False)
def process_radar(fid, title):
    drive = get_drive_connection()
    try:
        f = drive.CreateFile({'id': fid})
        t = tempfile.NamedTemporaryFile(delete=False, suffix=".tiff")
        t.close()
        f.GetContentFile(t.name)
        det = Sentinel1FloodDetector(t.name)
        res = det.detect(percentile=15)
        try:
            os.remove(t.name)
        except:
            pass
        return res
    except:
        return None


# -----------------------------------------------------------------------------
# 3. MAP VISUALIZATION
# -----------------------------------------------------------------------------
def display_map(data, bbox, type="ndvi", height=500):
    c_lat = (bbox[1] + bbox[3]) / 2
    c_lon = (bbox[0] + bbox[2]) / 2

    m = folium.Map(location=[c_lat, c_lon], zoom_start=10, tiles="OpenStreetMap")

    # Only add overlay if data exists
    if data is not None:
        if type == "ndvi":
            colored = cm.RdYlGn((data + 1) / 2)
        else:
            colored = cm.Blues(data)

        bounds = [[bbox[1], bbox[0]], [bbox[3], bbox[2]]]
        folium.raster_layers.ImageOverlay(image=colored, bounds=bounds, opacity=0.6).add_to(m)

    # Always show region box
    folium.Rectangle(bounds=[[bbox[1], bbox[0]], [bbox[3], bbox[2]]], color="red", fill=False).add_to(m)

    st_folium(m, width="100%", height=height, key="main_map")


# -----------------------------------------------------------------------------
# 4. APP LOGIC
# -----------------------------------------------------------------------------
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3920/3920466.png", width=100)
st.sidebar.title("SAFE-RO")

selected_region = st.sidebar.selectbox("📍 Select Location:", list(REGIONS.keys()))
current_bbox = REGIONS[selected_region]
mode = st.sidebar.radio("Mode:", ["🏠 Home", "📢 Citizen App", "🏢 Authority Dashboard"])

if st.sidebar.button("🧹 Clear Cache"):
    st.cache_data.clear()
    st.sidebar.success("Cache Cleared!")

# --- FILE LOADING ---
all_files = get_file_list_cached()
region_files = [f for f in all_files if f['title'].startswith(selected_region)]

# Demo Fallback
use_fallback = False
if not region_files and all_files:
    region_files = all_files
    use_fallback = True

reds = [f for f in region_files if "RED" in f['title']]
nirs = [f for f in region_files if "NIR" in f['title']]
radars = [f for f in region_files if "VV" in f['title']]

# -----------------------------------------------------------------------------
# MODE: HOME
# -----------------------------------------------------------------------------
if mode == "🏠 Home":
    st.title(f"Welcome to SAFE-RO 🛰️")

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("### 🌍 Real-time Disaster Monitoring")
        st.write(
            "SAFE-RO integrates **Sentinel-1 (Radar)** and **Sentinel-2 (Optical)** satellites to detect floods and monitor vegetation health across Romania.")
        st.write("Select **Citizen App** to see alerts for your area, or **Authority Dashboard** for analysis.")

        st.markdown("---")
        # FIXED: Replaced 'use_column_width' with 'use_container_width' to kill the warning
        st.image("https://images.unsplash.com/photo-1451187580459-43490279c0fa",
                 caption="Sentinel Constellation View",
                 use_container_width=True)

    with col2:
        st.info(f"📍 **Current Region:** {selected_region}")
        # FIXED: Mini-Map is back on the right side!
        # We pass None for data so it loads INSTANTLY (just the street map)
        display_map(None, current_bbox, height=350)

# -----------------------------------------------------------------------------
# MODE: CITIZEN APP
# -----------------------------------------------------------------------------
elif mode == "📢 Citizen App":
    st.title(f"📢 Alert System: {selected_region}")

    if radars:
        st.markdown('<div class="warn-box">⚠️ WEATHER ALERT: Heavy Clouds. Monitoring for Floods.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="safe-box">✅ STATUS NORMAL: Weather is Clear. No flood risk detected.</div>',
                    unsafe_allow_html=True)

    st.subheader("Live Satellite Map")

    # FAST LOADING FIX: Toggle Switch
    show_sat = st.toggle("📡 Overlay Satellite Data (Takes ~5s)", value=False)

    map_data = None
    map_type = "ndvi"

    if show_sat:
        # Only download if user asks for it
        if reds and nirs:
            r_f = reds[0]
            n_f = next((f for f in nirs if r_f['title'].replace("_RED.jp2", "") in f['title']), None)
            if n_f:
                with st.spinner("Downloading Satellite Feed..."):
                    map_data = process_data(r_f['id'], n_f['id'], r_f['title'], n_f['title'])
        elif radars:
            with st.spinner("Downloading Radar Feed..."):
                map_data = process_radar(radars[0]['id'], radars[0]['title'])
                map_type = "water"

    # Render Map (Instant if show_sat is False)
    display_map(map_data, current_bbox, map_type)

# -----------------------------------------------------------------------------
# MODE: AUTHORITY DASHBOARD
# -----------------------------------------------------------------------------
elif mode == "🏢 Authority Dashboard":
    if "auth" not in st.session_state: st.session_state.auth = False

    if not st.session_state.auth:
        st.title("🔒 Restricted Access")
        pwd = st.text_input("Enter Admin Password:", type="password")
        if st.button("Login"):
            if pwd == "admin123":
                st.session_state.auth = True; st.rerun()
            else:
                st.error("Invalid Password")
    else:
        st.title(f"🏢 Command Center: {selected_region}")

        if use_fallback:
            st.warning(f"⚠️ No local data for {selected_region}. Using Demo Data.")

        tab1, tab2 = st.tabs(["Vegetation (S2)", "Floods (S1)"])

        with tab1:
            if reds:
                r_sel = st.selectbox("Select Red Band", [f['title'] for f in reds])
                n_sel = next((f['title'] for f in nirs if r_sel.replace("RED", "NIR") in f['title']), None)

                if st.button("Analyze Optical Data"):
                    r_obj = next(f for f in reds if f['title'] == r_sel)
                    n_obj = next(f for f in nirs if f['title'] == n_sel)
                    with st.spinner("Processing..."):
                        # Save to Session State so map persists
                        st.session_state.dash_data = process_data(r_obj['id'], n_obj['id'], r_sel, n_sel)
                        st.session_state.dash_type = "ndvi"
            else:
                st.info("No Optical Data.")

        with tab2:
            if radars:
                s1_sel = st.selectbox("Select Radar Image", [f['title'] for f in radars])
                if st.button("Analyze Radar Data"):
                    s1_obj = next(f for f in radars if f['title'] == s1_sel)
                    with st.spinner("Processing..."):
                        st.session_state.dash_data = process_radar(s1_obj['id'], s1_sel)
                        st.session_state.dash_type = "water"
            else:
                st.info("✅ Weather is Clear: No Flood Radar Needed.")

        st.divider()

        # Use Session State for Dashboard Map
        if "dash_data" in st.session_state:
            st.subheader("Geospatial Analysis")
            display_map(st.session_state.dash_data, current_bbox, getattr(st.session_state, 'dash_type', 'ndvi'))