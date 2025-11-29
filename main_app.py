import streamlit as st
import ee
import numpy as np
import folium
from streamlit_folium import st_folium
from matplotlib import cm
import datetime
import tempfile
import os
import matplotlib.pyplot as plt
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

from gee_client import GEEClient
from safe_ro_core import NDVIProcessor

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
# 2. CACHED FUNCTIONS & SECRETS
# -----------------------------------------------------------------------------

# Create mycreds.txt from secrets if it doesn't exist, for GDrive auth
if not os.path.exists("mycreds.txt") and "gdrive_creds_json" in st.secrets:
    with open("mycreds.txt", "w") as f:
        f.write(st.secrets["gdrive_creds_json"])

@st.cache_resource
def get_gee_client():
    try:
        gee_project = st.secrets["gee_project"]
        return GEEClient(project=gee_project)
    except KeyError:
        st.error("Missing GEE project configuration. Please create a file `.streamlit/secrets.toml` and add `gee_project = 'your-project-id'`.")
        st.stop()

gee_client = get_gee_client()


# -----------------------------------------------------------------------------
# 3. LOCAL ANALYSIS HELPERS
# -----------------------------------------------------------------------------
@st.cache_resource
def get_drive_connection():
    """Authenticates with Google Drive once and keeps the connection open."""
    try:
        gauth = GoogleAuth()
        creds_path = "mycreds.txt"

        # Check if the file exists before trying to load
        if not os.path.exists(creds_path):
            st.error(f"❌ Google Drive credentials file ('{creds_path}') not found.")
            st.info("For local development, run authentication locally. For deployment, add 'gdrive_creds_json' to your Streamlit secrets.")
            return None

        gauth.LoadCredentialsFile(creds_path)

        if gauth.credentials is None:
            # This case might be triggered if the file is empty or invalid
            st.error(f"❌ Credentials in '{creds_path}' are invalid. Please re-authenticate.")
            return None
        elif gauth.access_token_expired:
            gauth.Refresh()
            gauth.SaveCredentialsFile(creds_path)
        else:
            gauth.Authorize()

        return GoogleDrive(gauth)
    except Exception as e:
        st.error(f"Google Drive Authentication Error: {e}")
        return None


def get_file_list(drive, folder_name="SAFE_RO_Cloud_Data"):
    """Lists all files in the cloud folder."""
    # 1. Find folder ID
    file_list = drive.ListFile({
        'q': f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    }).GetList()

    if not file_list:
        return []

    folder_id = file_list[0]['id']

    # 2. List files inside
    query = f"'{folder_id}' in parents and trashed=false"
    files = drive.ListFile({'q': query}).GetList()

    # Sort files by title so they appear in date order
    files.sort(key=lambda x: x['title'], reverse=True)
    return files


def download_from_drive(drive, file_obj):
    """Downloads a specific Google Drive file to a temp file."""
    try:
        # Create a temp file with the correct extension
        ext = os.path.splitext(file_obj['title'])[1]
        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tfile.close()

        file_obj.GetContentFile(tfile.name)
        return tfile.name
    except Exception as e:
        st.error(f"Download failed: {e}")
        return None



# -----------------------------------------------------------------------------
# 3. MAP VISUALIZATION
# -----------------------------------------------------------------------------
def create_folium_map(data, bounds, data_type="ndvi", height=500):
    """
    Creates and displays a Folium map with a raster overlay.
    
    Args:
        data (np.array): The raster data to display.
        bounds (list or rasterio.coords.BoundingBox): The geographic bounds of the data.
        data_type (str): The type of data ('ndvi' or 'water') for colormap selection.
        height (int): The height of the map in pixels.
    """
    # Determine center and bounds format
    if isinstance(bounds, (list, tuple)) and len(bounds) == 4: # GEE format [min_lon, min_lat, max_lon, max_lat]
        c_lat = (bounds[1] + bounds[3]) / 2
        c_lon = (bounds[0] + bounds[2]) / 2
        map_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]]
    elif hasattr(bounds, 'left') and hasattr(bounds, 'bottom') and hasattr(bounds, 'right') and hasattr(bounds, 'top'): # rasterio format
        c_lat = (bounds.bottom + bounds.top) / 2
        c_lon = (bounds.left + bounds.right) / 2
        map_bounds = [[bounds.bottom, bounds.left], [bounds.top, bounds.right]]
    else:
        # Default fallback if bounds are invalid
        st.error("Invalid bounds provided for map display.")
        return

    m = folium.Map(location=[c_lat, c_lon], zoom_start=10, tiles="OpenStreetMap")

    # Add raster overlay if data is valid
    if data is not None and data.size > 0:
        if data_type == "ndvi":
            # Normalize NDVI data and apply colormap
            colored_data = cm.RdYlGn((data.astype(float) + 1) / 2)
        else: # 'water'
            colored_data = cm.Blues(data.astype(float))
        
        folium.raster_layers.ImageOverlay(
            image=colored_data,
            bounds=map_bounds,
            opacity=0.7,
            name=f"{data_type.upper()} Overlay"
        ).add_to(m)

    # Always show the region boundary
    folium.Rectangle(
        bounds=map_bounds,
        color="red",
        fill=False,
        weight=2,
        tooltip="Analysis Area"
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

# --- DATE SELECTION ---
st.sidebar.markdown("---")
st.sidebar.header("Date Range")
today = datetime.date.today()
last_week = today - datetime.timedelta(days=7)
start_date = st.sidebar.date_input("Start Date", last_week)
end_date = st.sidebar.date_input("End Date", today)

# Convert to GEE format
gee_aoi = ee.Geometry.Rectangle(current_bbox)


# -----------------------------------------------------------------------------
# MODE: HOME
# -----------------------------------------------------------------------------
if mode == "Home":
    st.title(f"Welcome to SAFE-RO")

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("### 🌍 Real-time Disaster Monitoring with Google Earth Engine")
        st.write(
            "SAFE-RO now uses **Google Earth Engine** to analyze **Sentinel-1 (Radar)** and **Sentinel-2 (Optical)** data for flood detection and vegetation monitoring across Romania.")
        st.write("Select **Citizen App** to see alerts, or **Authority Dashboard** for in-depth analysis.")

        st.markdown("---")
        st.image("https://images.unsplash.com/photo-1451187580459-43490279c0fa",
                 caption="Sentinel Constellation View",
                 use_container_width=True)

    with col2:
        st.info(f"📍 **Current Region:** {selected_region}")
        create_folium_map(None, current_bbox, height=350)

# -----------------------------------------------------------------------------
# MODE: CITIZEN APP
# -----------------------------------------------------------------------------
elif mode == "Citizen App":
    st.title(f"Alert System: {selected_region}")
    
    st.markdown('<div class="safe-box">✅ STATUS: Monitoring services are active.</div>', unsafe_allow_html=True)

    st.subheader("Live Satellite Map")

    show_sat = st.toggle("Overlay Satellite Data", value=False)

    map_data = None
    map_type = "ndvi"
    
    if show_sat:
        with st.spinner("Querying Google Earth Engine..."):
            map_data = gee_client.get_ndvi(gee_aoi, str(start_date), str(end_date))
            if map_data is None:
                 st.warning("No Sentinel-2 data found for the selected period. Trying Sentinel-1 for floods.")
                 map_data = gee_client.get_flood_data(gee_aoi, str(start_date), str(end_date))
                 map_type = "water"
                 if map_data is None:
                    st.error("No data found for the selected region and date range.")


    create_folium_map(map_data, current_bbox, data_type=map_type)

# -----------------------------------------------------------------------------
# MODE: AUTHORITY DASHBOARD
# -----------------------------------------------------------------------------
elif mode == "Authority Dashboard":
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


# -----------------------------------------------------------------------------
# MODE: LOCAL ANALYSIS
# -----------------------------------------------------------------------------
elif mode == "Local Analysis":
    st.title("Local Analysis – Manual & Google Drive")
    st.markdown("Process your own raster files or connect to Google Drive.")

    tab1, tab2, tab3 = st.tabs(["☁️ Cloud Data (Google Drive)", "📂 Manual Upload", "🔥 Fire Monitor"])

    # --- TAB 1: CLOUD DATA ---
    with tab1:
        st.header("Latest Satellite Imagery (Google Drive)")

        drive = get_drive_connection()

        if drive:
            # Get raw files
            files = get_file_list(drive)

            if not files:
                st.warning("Connected to Drive, but 'SAFE_RO_Cloud_Data' folder is empty or missing.")
            else:
                # 1. Separate into RED and NIR lists
                red_files = [f for f in files if "RED" in f['title']]
                nir_files = [f for f in files if "NIR" in f['title']]

                if not red_files:
                    st.info("No RED bands found in cloud.")

                # 2. Create simple Dictionaries { "Filename": FileObject }
                red_map = {f['title']: f for f in red_files}
                nir_map = {f['title']: f for f in nir_files}

                col_sel1, col_sel2 = st.columns(2)

                with col_sel1:
                    red_choice = st.selectbox("Select RED Band", list(red_map.keys()))

                with col_sel2:
                    nir_options = list(nir_map.keys())
                    default_index = 0
                    if red_choice:
                        base_name = red_choice.replace("_RED.jp2", "")
                        for i, name in enumerate(nir_options):
                            if base_name in name:
                                default_index = i
                                break

                    nir_choice = st.selectbox("Select NIR Band", nir_options, index=default_index)

                if st.button("🚀 Analyze Cloud Data"):
                    selected_red_obj = red_map[red_choice]
                    selected_nir_obj = nir_map[nir_choice]

                    with st.spinner("Downloading from Google Drive..."):
                        path_red = download_from_drive(drive, selected_red_obj)
                        path_nir = download_from_drive(drive, selected_nir_obj)

                    if path_red and path_nir:
                        st.success(f"Loaded: {red_choice}")

                        try:
                            proc = NDVIProcessor(path_red, path_nir)
                            ndvi, bounds = proc.compute_ndvi()

                            if ndvi is not None and bounds is not None:
                                stats = {
                                    "Min NDVI": float(np.nanmin(ndvi)),
                                    "Max NDVI": float(np.nanmax(ndvi)),
                                    "Mean NDVI": float(np.nanmean(ndvi)),
                                }

                                col_res1, col_res2 = st.columns([3, 1])
                                with col_res1:
                                    st.subheader("NDVI Analysis Map")
                                    create_folium_map(ndvi, bounds, data_type="ndvi")

                                with col_res2:
                                    st.subheader("Risk Insights")
                                    st.write(stats)
                                    if stats['Mean NDVI'] < 0.2:
                                        st.error("⚠️ Low Vegetation Detected! Potential Drought.")
                                    elif stats['Mean NDVI'] > 0.5:
                                        st.success("✅ Healthy Vegetation Coverage.")
                            else:
                                st.error("Could not compute NDVI. Check the input files.")

                        except Exception as e:
                            st.error(f"Processing Error: {e}")
                        finally:
                            if os.path.exists(path_red): os.remove(path_red)
                            if os.path.exists(path_nir): os.remove(path_nir)

    # --- TAB 2: MANUAL UPLOAD ---
    with tab2:
        st.header("Manual File Upload")
        uploaded_red = st.file_uploader("Upload RED Band (.tif/.jp2)", key="m_red")
        uploaded_nir = st.file_uploader("Upload NIR Band (.tif/.jp2)", key="m_nir")

        if st.button("🚀 Analyze Local Files"):
            if uploaded_red and uploaded_nir:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".tif") as tr, \
                     tempfile.NamedTemporaryFile(delete=False, suffix=".tif") as tn:
                    
                    tr.write(uploaded_red.read())
                    tn.write(uploaded_nir.read())
                    
                    tr.flush()
                    tn.flush()

                    try:
                        proc = NDVIProcessor(tr.name, tn.name)
                        ndvi, bounds = proc.compute_ndvi()

                        if ndvi is not None and bounds is not None:
                            st.subheader("NDVI Analysis Map")
                            create_folium_map(ndvi, bounds, data_type="ndvi")
                        else:
                            st.error("Could not compute NDVI. Check the input files.")

                    except Exception as e:
                        st.error(f"An error occurred during processing: {e}")
                    finally:
                        # Clean up the temporary files
                        os.remove(tr.name)
                        os.remove(tn.name)
            else:
                st.warning("Please upload both RED and NIR band files.")

from firms_client import FIRMSClient

# ... (existing imports)

# ... (existing code up to the local analysis mode)

# -----------------------------------------------------------------------------
    # --- TAB 3: FIRES ---
    with tab3:
        st.header("Real-time Fire Alerts (FIRMS)")
        
        firms_api_key = st.secrets.get("firms_api_key")
        
        if not firms_api_key:
            st.warning("Please add your `firms_api_key` to `.streamlit/secrets.toml` to use this feature.")
            st.markdown("You can obtain a key from the [FIRMS API website](https://firms.modaps.eosdis.nasa.gov/api/api_key/).")
        else:
            st.info("This tool fetches active fire data from NASA's FIRMS for the selected region and end date.")
            
            if st.button("🛰️ Fetch Active Fire Data"):
                with st.spinner("Querying FIRMS for active fire hotspots..."):
                    try:
                        firms_client = FIRMSClient(api_key=firms_api_key)
                        # Use the bounding box of the selected region and the end date from the sidebar
                        fire_data = firms_client.get_active_fires(current_bbox, end_date)

                        if fire_data is not None and not fire_data.empty:
                            st.success(f"Found {len(fire_data)} active fire hotspots.")
                            
                            # Create a map centered on the region
                            c_lat = (current_bbox[1] + current_bbox[3]) / 2
                            c_lon = (current_bbox[0] + current_bbox[2]) / 2
                            fire_map = folium.Map(location=[c_lat, c_lon], zoom_start=9, tiles="CartoDB positron")

                            # Add fire markers
                            for idx, fire in fire_data.iterrows():
                                folium.CircleMarker(
                                    location=[fire['latitude'], fire['longitude']],
                                    radius=3,
                                    color='red',
                                    fill=True,
                                    fill_color='orange',
                                    fill_opacity=0.7,
                                    tooltip=f"Confidence: {fire.get('confidence', 'N/A')}<br>Brightness: {fire.get('bright_ti4', 'N/A')}"
                                ).add_to(fire_map)
                            
                            # Display the map
                            st_folium(fire_map, width="100%", height=500)

                        else:
                            st.info("No active fires detected in the selected area for the given date.")

                    except Exception as e:
                        st.error(f"An error occurred while fetching fire data: {e}")


