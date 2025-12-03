import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import streamlit as st
import ee
import numpy as np
import folium
from streamlit_folium import st_folium
from matplotlib import cm
import datetime
import tempfile
import matplotlib.pyplot as plt

# Corrected imports after refactoring
from safe_ro.clients.gee_client import GEEClient
from safe_ro.clients.gdrive_client import GDriveClient
from safe_ro.clients.firms_client import FIRMSClient
from safe_ro.core.safe_ro_core import NDVIProcessor, Sentinel1FloodDetector

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
# 2. CACHED CLIENT INITIALIZATION
# -----------------------------------------------------------------------------

@st.cache_resource
def get_gee_client():
    try:
        gee_project = st.secrets["gee_project"]
        return GEEClient(project=gee_project)
    except KeyError:
        st.error("Missing GEE project configuration. Please create a file `.streamlit/secrets.toml` and add `gee_project = 'your-project-id'`.")
        st.stop()

@st.cache_resource
def get_gdrive_client():
    """Initializes the Google Drive client, which handles its own auth."""
    return GDriveClient()

# Initialize clients
gee_client = get_gee_client()
gdrive_client = get_gdrive_client()


# -----------------------------------------------------------------------------
# 3. MAP VISUALIZATION
# -----------------------------------------------------------------------------
def create_folium_map(data, bounds, data_type="ndvi", height=500):
    """
    Creates and displays a Folium map with a raster overlay.
    """
    if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
        c_lat = (bounds[1] + bounds[3]) / 2
        c_lon = (bounds[0] + bounds[2]) / 2
        map_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
    elif hasattr(bounds, 'left'):
        c_lat = (bounds.bottom + bounds.top) / 2
        c_lon = (bounds.left + bounds.right) / 2
        map_bounds = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]
    else:
        st.error("Invalid bounds provided for map display.")
        return

    m = folium.Map(location=[c_lat, c_lon], zoom_start=10, tiles="OpenStreetMap")

    if data is not None and data.size > 0:
        colormap = cm.RdYlGn if data_type == "ndvi" else cm.Blues
        colored_data = colormap((data.astype(float) + 1) / 2 if data_type == "ndvi" else data.astype(float))
        
        folium.raster_layers.ImageOverlay(
            image=colored_data,
            bounds=map_bounds,
            opacity=0.7,
            name=f"{data_type.upper()} Overlay"
        ).add_to(m)

    folium.Rectangle(
        bounds=map_bounds, color="red", fill=False, weight=2, tooltip="Analysis Area"
    ).add_to(m)

    folium.LayerControl().add_to(m)
    st_folium(m, width="100%", height=height, key=f"map_{data_type}")



# -----------------------------------------------------------------------------
# 4. APP LOGIC
# -----------------------------------------------------------------------------
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3920/3920466.png", width=100)
st.sidebar.title("SAFE-RO")

selected_region = st.sidebar.selectbox("📍 Select Location:", list(REGIONS.keys()))
current_bbox = REGIONS[selected_region]
mode = st.sidebar.radio("Mode:", ["Home", "Citizen App", "Authority Dashboard", "Local Analysis"])

if st.sidebar.button("🧹 Clear Cache"):
    st.cache_data.clear()
    st.sidebar.success("Cache Cleared!")

st.sidebar.markdown("---")
st.sidebar.header("Date Range")
today = datetime.date.today()
last_week = today - datetime.timedelta(days=7)
start_date = st.sidebar.date_input("Start Date", last_week)
end_date = st.sidebar.date_input("End Date", today)

gee_aoi = ee.Geometry.Rectangle(current_bbox)


# --- MODE: HOME ---
if mode == "Home":
    st.title(f"Welcome to SAFE-RO")
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown("### 🌍 Real-time Disaster Monitoring with Google Earth Engine")
        st.write("SAFE-RO uses **Google Earth Engine** to analyze **Sentinel-1 (Radar)** and **Sentinel-2 (Optical)** data for flood detection and vegetation monitoring across Romania.")
        st.image("https://images.unsplash.com/photo-1451187580459-43490279c0fa", caption="Sentinel Constellation View", use_container_width=True)
    with col2:
        st.info(f"📍 **Current Region:** {selected_region}")
        create_folium_map(None, current_bbox, height=350)

# --- MODE: CITIZEN APP ---
elif mode == "Citizen App":
    st.title(f"Alert System: {selected_region}")
    st.markdown('<div class="safe-box">✅ STATUS: Monitoring services are active.</div>', unsafe_allow_html=True)
    st.subheader("Live Satellite Map")
    show_sat = st.toggle("Overlay Satellite Data", value=False)
    map_data, map_type = None, "ndvi"
    if show_sat:
        with st.spinner("Querying Google Earth Engine..."):
            map_data = gee_client.get_ndvi(gee_aoi, str(start_date), str(end_date))
            if map_data is None:
                st.warning("No Sentinel-2 data found. Trying Sentinel-1 for floods.")
                map_data = gee_client.get_flood_data(gee_aoi, str(start_date), str(end_date))
                map_type = "water"
            if map_data is None:
                st.error("No data found for the selected region and date range.")
    create_folium_map(map_data, current_bbox, data_type=map_type)

# --- MODE: AUTHORITY DASHBOARD ---
elif mode == "Authority Dashboard":
    # ... (code remains the same)
    if "auth" not in st.session_state: st.session_state.auth = False

    if not st.session_state.auth:
        st.title("Restricted Access")
        pwd = st.text_input("Enter Admin Password:", type="password")
        if st.button("Login"):
            if pwd == "admin123":
                st.session_state.auth = True; st.rerun()
            else:
                st.error("Invalid Password")
    else:
        st.title(f"Command Center: {selected_region}")

        tab1, tab2 = st.tabs(["Vegetation (S2)", "Floods (S1)"])

        with tab1:
            if st.button("Analyze Vegetation Health"):
                with st.spinner("Processing NDVI with GEE..."):
                    st.session_state.dash_data = gee_client.get_ndvi(gee_aoi, str(start_date), str(end_date))
                    st.session_state.dash_type = "ndvi"
                    if st.session_state.dash_data is None:
                        st.error("Could not retrieve Sentinel-2 data.")


        with tab2:
            if st.button("Analyze Flood Risk"):
                with st.spinner("Processing Flood Data with GEE..."):
                    st.session_state.dash_data = gee_client.get_flood_data(gee_aoi, str(start_date), str(end_date))
                    st.session_state.dash_type = "water"
                    if st.session_state.dash_data is None:
                        st.error("Could not retrieve Sentinel-1 data.")


        st.divider()

        if "dash_data" in st.session_state:
            st.subheader("Geospatial Analysis")
            create_folium_map(st.session_state.dash_data, current_bbox, data_type=getattr(st.session_state, 'dash_type', 'ndvi'))

# --- MODE: LOCAL ANALYSIS ---
elif mode == "Local Analysis":
    st.title("Local Analysis – Manual & Google Drive")
    analysis_type = st.selectbox("Select Analysis Type", ["NDVI (Vegetation)", "Flood"])
    tab1, tab2, tab3 = st.tabs(["☁️ Cloud Data (Google Drive)", "📂 Manual Upload", "🔥 Fire Monitor"])

    # --- TAB 1: CLOUD DATA (Now uses GDriveClient) ---
    with tab1:
        st.header("Latest Satellite Imagery (Google Drive)")
        if gdrive_client.drive:
            files = gdrive_client.get_file_list()
            if not files:
                st.warning("Connected, but 'SAFE_RO_Cloud_Data' folder is empty or missing.")
            else:
                # NDVI Analysis from Cloud
                if analysis_type == "NDVI (Vegetation)":
                    red_map = {f['title']: f for f in files if "RED" in f['title']}
                    nir_map = {f['title']: f for f in files if "NIR" in f['title']}
                    col1, col2 = st.columns(2)
                    with col1:
                        red_choice = st.selectbox("Select RED Band", list(red_map.keys()))
                    with col2:
                        nir_choice = st.selectbox("Select NIR Band", list(nir_map.keys()))

                    if st.button("🚀 Analyze NDVI Cloud Data"):
                        if red_choice and nir_choice:
                            with st.spinner("Downloading from Google Drive..."):
                                path_red = gdrive_client.download_file(red_map[red_choice])
                                path_nir = gdrive_client.download_file(nir_map[nir_choice])
                            if path_red and path_nir:
                                try:
                                    proc = NDVIProcessor(path_red, path_nir)
                                    ndvi, bounds = proc.compute_ndvi()
                                    create_folium_map(ndvi, bounds, "ndvi")
                                finally:
                                    os.remove(path_red); os.remove(path_nir)
                # Flood Analysis from Cloud
                elif analysis_type == "Flood":
                    radar_map = {f['title']: f for f in files if "VV" in f['title']}
                    radar_choice = st.selectbox("Select Radar Image", list(radar_map.keys()))
                    if st.button("🚀 Analyze Flood Cloud Data"):
                        if radar_choice:
                            with st.spinner("Downloading from Google Drive..."):
                                path_radar = gdrive_client.download_file(radar_map[radar_choice])
                            if path_radar:
                                try:
                                    proc = Sentinel1FloodDetector(path_radar)
                                    mask, bounds = proc.detect()
                                    create_folium_map(mask, bounds, "water")
                                finally:
                                                                         os.remove(path_radar)
    # --- TAB 2: MANUAL UPLOAD ---
    with tab2:
        # ... (code remains the same)
        st.header("Manual File Upload")
        
        if analysis_type == "NDVI (Vegetation)":
            uploaded_red = st.file_uploader("Upload RED Band (.tif/.jp2)", key="m_red")
            uploaded_nir = st.file_uploader("Upload NIR Band (.tif/.jp2)", key="m_nir")

            if st.button("🚀 Analyze Local NDVI Files"):
                if uploaded_red and uploaded_nir:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".tif") as tr, \
                         tempfile.NamedTemporaryFile(delete=False, suffix=".tif") as tn:
                        tr.write(uploaded_red.read())
                        tn.write(uploaded_nir.read())
                        tr.flush(); tn.flush()

                        try:
                            proc = NDVIProcessor(tr.name, tn.name)
                            ndvi, bounds = proc.compute_ndvi()
                            if ndvi is not None:
                                st.subheader("NDVI Analysis Map")
                                create_folium_map(ndvi, bounds, data_type="ndvi")
                            else:
                                st.error("Could not compute NDVI.")
                        finally:
                            os.remove(tr.name)
                            os.remove(tn.name)
                else:
                    st.warning("Please upload both RED and NIR band files.")
        
        elif analysis_type == "Flood":
            uploaded_radar = st.file_uploader("Upload Sentinel-1 VV Band (.tif)", key="m_radar")
            
            if st.button("🚀 Analyze Local Flood File"):
                if uploaded_radar:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".tif") as tradar:
                        tradar.write(uploaded_radar.read())
                        tradar.flush()

                        try:
                            proc = Sentinel1FloodDetector(tradar.name)
                            flood_mask, bounds = proc.detect()
                            if flood_mask is not None:
                                st.subheader("Flood Analysis Map")
                                create_folium_map(flood_mask, bounds, data_type="water")
                            else:
                                st.error("Could not compute flood mask.")
                        finally:
                            os.remove(tradar.name)
                else:
                    st.warning("Please upload a Sentinel-1 VV band file.")

    # --- TAB 3: FIRES (Now uses FIRMSClient) ---
    with tab3:
        st.header("Real-time Fire Alerts (FIRMS)")
        firms_api_key = st.secrets.get("firms_api_key")
        if not firms_api_key:
            st.warning("Please add `firms_api_key` to `.streamlit/secrets.toml`.")
        else:
            if st.button("🛰️ Fetch Active Fire Data"):
                with st.spinner("Querying FIRMS..."):
                    try:
                        firms_client = FIRMSClient(api_key=firms_api_key)
                        fire_data = firms_client.get_active_fires(current_bbox, end_date)
                        if fire_data is not None and not fire_data.empty:
                            st.success(f"Found {len(fire_data)} active fire hotspots.")
                            c_lat = (current_bbox[1] + current_bbox[3]) / 2
                            c_lon = (current_bbox[0] + current_bbox[2]) / 2
                            fire_map = folium.Map(location=[c_lat, c_lon], zoom_start=9)
                            for _, fire in fire_data.iterrows():
                                folium.CircleMarker(
                                    location=[fire['latitude'], fire['longitude']],
                                    radius=3, color='red', fill=True, fill_color='orange',
                                    tooltip=f"Confidence: {fire.get('confidence', 'N/A')}"
                                ).add_to(fire_map)
                            st_folium(fire_map, width="100%", height=500)
                        else:
                            st.info("No active fires detected in the selected area.")
                    except Exception as e:
                        st.error(f"Error fetching fire data: {e}")
