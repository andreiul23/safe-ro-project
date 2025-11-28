import tempfile
import os
import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

# Import your existing core logic
from safe_ro_core import NDVIProcessor

st.set_page_config(page_title="SAFE-RO Dashboard", layout="wide")


# ==========================================
# 0. HELPER: GOOGLE DRIVE CONNECTION
# ==========================================
@st.cache_resource
def get_drive_connection():
    """Authenticates with Google Drive once and keeps the connection open."""
    try:
        gauth = GoogleAuth()
        # Look for credentials in the current folder
        gauth.LoadCredentialsFile("mycreds.txt")

        if gauth.credentials is None:
            st.error("❌ No credentials found! Run 'safe_ro_cloud.py' locally first to log in.")
            return None
        elif gauth.access_token_expired:
            gauth.Refresh()
            gauth.SaveCredentialsFile("mycreds.txt")
        else:
            gauth.Authorize()

        return GoogleDrive(gauth)
    except Exception as e:
        st.error(f"Authentication Error: {e}")
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


# ==========================================
# 1. DASHBOARD UI
# ==========================================

st.title("🛰️ SAFE-RO – Institutional Dashboard")
st.markdown("Monitoring **Floods**, **Vegetation (NDVI)**, and **Wildfires** using Sentinel-2 & FIRMS data.")

tab1, tab2, tab3 = st.tabs(["☁️ Cloud Data (Automatic)", "📂 Manual Upload", "🔥 Fire Monitor"])

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
            # This is the fix: The dropdown will only see the string keys
            red_map = {f['title']: f for f in red_files}
            nir_map = {f['title']: f for f in nir_files}

            col_sel1, col_sel2 = st.columns(2)

            with col_sel1:
                # Dropdown gets pure strings (titles)
                red_choice = st.selectbox("Select RED Band", list(red_map.keys()))

            with col_sel2:
                # Try to auto-select matching NIR
                nir_options = list(nir_map.keys())
                default_index = 0
                if red_choice:
                    base_name = red_choice.replace("_RED.jp2", "")
                    # Find corresponding NIR in the list
                    for i, name in enumerate(nir_options):
                        if base_name in name:
                            default_index = i
                            break

                nir_choice = st.selectbox("Select NIR Band", nir_options, index=default_index)

            if st.button("🚀 Analyze Cloud Data"):
                # 3. Retrieve the real objects using the map
                selected_red_obj = red_map[red_choice]
                selected_nir_obj = nir_map[nir_choice]

                with st.spinner("Downloading from Google Drive..."):
                    path_red = download_from_drive(drive, selected_red_obj)
                    path_nir = download_from_drive(drive, selected_nir_obj)

                if path_red and path_nir:
                    st.success(f"Loaded: {red_choice}")

                    # --- RUN CORE ANALYSIS ---
                    try:
                        proc = NDVIProcessor(path_red, path_nir)
                        ndvi = proc.compute_ndvi()

                        stats = {
                            "Min NDVI": float(np.nanmin(ndvi)),
                            "Max NDVI": float(np.nanmax(ndvi)),
                            "Mean NDVI": float(np.nanmean(ndvi)),
                        }

                        col_res1, col_res2 = st.columns([3, 1])
                        with col_res1:
                            fig, ax = plt.subplots(figsize=(10, 6))
                            # Fix: NDVI range is usually -1 to 1
                            im = ax.imshow(ndvi, cmap="RdYlGn", vmin=-0.2, vmax=0.8)
                            ax.set_title(f"Vegetation Health Analysis\nSource: {red_choice[:20]}...")
                            fig.colorbar(im, ax=ax, label="NDVI Index")
                            st.pyplot(fig)

                        with col_res2:
                            st.subheader("Risk Insights")
                            st.write(stats)
                            if stats['Mean NDVI'] < 0.2:
                                st.error("⚠️ Low Vegetation Detected! Potential Drought.")
                            elif stats['Mean NDVI'] > 0.5:
                                st.success("✅ Healthy Vegetation Coverage.")

                    except Exception as e:
                        st.error(f"Processing Error: {e}")
                    finally:
                        # Cleanup temp files
                        if os.path.exists(path_red): os.remove(path_red)
                        if os.path.exists(path_nir): os.remove(path_nir)

# --- TAB 2: MANUAL UPLOAD ---
with tab2:
    st.header("Manual File Upload")
    uploaded_red = st.file_uploader("Upload RED Band (.tif/.jp2)", key="m_red")
    uploaded_nir = st.file_uploader("Upload NIR Band (.tif/.jp2)", key="m_nir")

    if uploaded_red and uploaded_nir:
        with tempfile.NamedTemporaryFile(delete=False) as tr, tempfile.NamedTemporaryFile(delete=False) as tn:
            tr.write(uploaded_red.read())
            tn.write(uploaded_nir.read())
            tr.flush()
            tn.flush()

            proc = NDVIProcessor(tr.name, tn.name)
            ndvi = proc.compute_ndvi()

            st.image(ndvi, caption="NDVI Analysis", clamp=True, channels='GRAY')

# --- TAB 3: FIRES ---
with tab3:
    st.header("🔥 Real-time Fire Alerts (FIRMS)")
    st.info("Connect FIRMS API Key in next update.")