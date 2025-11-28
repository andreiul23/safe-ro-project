import os
import time
import requests
import zipfile
import shutil
from datetime import datetime
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


# ==========================================
# 1. GOOGLE DRIVE MANAGER
# ==========================================
class DriveManager:
    def __init__(self, folder_name="SAFE_RO_Data"):
        self.drive = self._auth()
        self.folder_name = folder_name
        self.folder_id = self._get_or_create_folder(folder_name)

    def _auth(self):
        gauth = GoogleAuth()

        # 1. Try to load existing credentials
        gauth.LoadCredentialsFile("mycreds.txt")

        # 2. If they don't exist or are broken, start fresh login
        if gauth.credentials is None:
            print("[AUTH] Opening browser for login...")

            # --- FIX: Force "Offline" access to get a Refresh Token ---
            # This ensures you don't get the "No refresh_token" error again
            gauth.GetFlow()
            gauth.flow.params.update({'access_type': 'offline'})
            gauth.flow.params.update({'prompt': 'consent'})

            # Launch browser on specific port 8080
            gauth.LocalWebserverAuth(port_numbers=[8080])

        # 3. If they exist but expired, refresh them automatically
        elif gauth.access_token_expired:
            try:
                gauth.Refresh()
            except Exception:
                # If refresh fails, delete the file and restart
                print("[AUTH] Token expired and refresh failed. Deleting credentials...")
                if os.path.exists("mycreds.txt"):
                    os.remove("mycreds.txt")
                return self._auth()  # Recursively try again
        else:
            gauth.Authorize()

        # 4. Save the good credentials
        gauth.SaveCredentialsFile("mycreds.txt")
        return GoogleDrive(gauth)

    def _get_or_create_folder(self, folder_name):
        file_list = self.drive.ListFile({
            'q': f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        }).GetList()

        if file_list:
            print(f"[CLOUD] Found folder: {folder_name}")
            return file_list[0]['id']
        else:
            print(f"[CLOUD] Creating folder: {folder_name}")
            folder = self.drive.CreateFile({'title': folder_name, 'mimeType': 'application/vnd.google-apps.folder'})
            folder.Upload()
            return folder['id']

    def upload_file(self, local_path):
        filename = os.path.basename(local_path)

        # 1. CHECK IF FILE ALREADY EXISTS IN CLOUD
        # We ask Drive: "Do you have a file with this name in this folder?"
        query = f"title='{filename}' and '{self.folder_id}' in parents and trashed=false"
        existing_files = self.drive.ListFile({'q': query}).GetList()

        if existing_files:
            print(f"[CLOUD] ✅ File exists (Skipping upload): {filename}")
            return existing_files[0]['id']

        # 2. UPLOAD IF NEW
        print(f"[CLOUD] ⏳ Uploading {filename} (Please wait, this may take minutes)...")
        gfile = self.drive.CreateFile({'title': filename, 'parents': [{'id': self.folder_id}]})
        gfile.SetContentFile(local_path)

        # Retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                gfile.Upload()
                print(f"[CLOUD] ✅ Success: {filename}")
                return gfile['id']
            except Exception as e:
                print(f"⚠️ Upload error (Attempt {attempt + 1}): {e}")
                time.sleep(5)

        print("❌ Upload failed.")
        return None


# ==========================================
# 2. SATELLITE DOWNLOADER (CDSE)
# ==========================================
class SmartDownloader:
    AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.token = None

    def authenticate(self):
        data = {"client_id": "cdse-public", "username": self.username, "password": self.password,
                "grant_type": "password"}
        r = requests.post(self.AUTH_URL, data=data)
        if r.status_code == 200:
            self.token = r.json()["access_token"]
            print("[CDSE] Authentication successful.")
        else:
            raise Exception(f"Login Failed: {r.text}")

    def find_and_process_latest(self, bbox, temp_dir="temp_download"):
        if not self.token: self.authenticate()

        print(f"[CDSE] Searching images in {bbox}...")
        polygon = (f"SRID=4326;POLYGON(({bbox[0]} {bbox[1]}, {bbox[2]} {bbox[1]}, "
                   f"{bbox[2]} {bbox[3]}, {bbox[0]} {bbox[3]}, {bbox[0]} {bbox[1]}))")

        filter_query = (f"Collection/Name eq 'SENTINEL-2' and OData.CSC.Intersects(area=geography'{polygon}') "
                        f"and ContentDate/Start ge 2024-01-01T00:00:00.000Z")

        r = requests.get(self.SEARCH_URL,
                         params={"$filter": filter_query, "$orderby": "ContentDate/Start desc", "$top": 1},
                         headers={"Authorization": f"Bearer {self.token}"})

        if r.status_code != 200:
            print(f"[ERROR] Search Failed: {r.text}")
            return []

        results = r.json().get('value', [])
        if not results: return []

        product = results[0]
        prod_name = product['Name']
        prod_id = product['Id']
        print(f"[CDSE] Newest image: {prod_name}")

        # --- SKIP CHECK ---
        expected_red = os.path.join(temp_dir, f"{prod_name}_RED.jp2")
        expected_nir = os.path.join(temp_dir, f"{prod_name}_NIR.jp2")

        if os.path.exists(expected_red) and os.path.exists(expected_nir):
            print(f"✅ [SKIP] Files already downloaded and extracted!")
            return [expected_red, expected_nir]

        # --- DOWNLOAD ---
        os.makedirs(temp_dir, exist_ok=True)
        zip_path = os.path.join(temp_dir, f"{prod_name}.zip")
        initial_url = f"{self.SEARCH_URL}({prod_id})/$value"

        # Handle Redirect
        r_head = requests.get(initial_url, headers={"Authorization": f"Bearer {self.token}"}, allow_redirects=False,
                              stream=True)
        final_url = r_head.headers['Location'] if r_head.status_code in [301, 302, 303, 307, 308] else initial_url

        print(f"[CDSE] ⬇️ Downloading ZIP (Resumable)...")

        download_complete = False
        retries = 0
        while not download_complete and retries < 20:
            try:
                current_size = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
                headers = {"Authorization": f"Bearer {self.token}"}
                mode = 'wb'
                if current_size > 0:
                    headers['Range'] = f"bytes={current_size}-"
                    mode = 'ab'
                    print(f"   -> Resuming from {current_size / 1024 / 1024:.1f} MB...")

                with requests.get(final_url, headers=headers, stream=True, timeout=60) as r_down:
                    if r_down.status_code == 416: break  # Done
                    r_down.raise_for_status()
                    with open(zip_path, mode) as f:
                        for chunk in r_down.iter_content(chunk_size=1024 * 1024):
                            if chunk: f.write(chunk)
                download_complete = True
            except Exception as e:
                print(f"⚠️ Interrupted: {e}. Retrying in 5s...")
                time.sleep(5)
                retries += 1

        # --- EXTRACT (With 60m Exclusion Fix) ---
        extracted_files = []
        print(f"[PROCESS] 📦 Unzipping RED/NIR...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                for info in z.infolist():

                    # === THIS IS THE PART THAT WAS MODIFIED ===
                    is_band = ("_B04_" in info.filename) or ("_B08_" in info.filename)
                    is_img = info.filename.endswith(".jp2")

                    # We strictly ignore "R60m" to avoid the resolution mismatch error
                    if is_band and is_img and ("R60m" not in info.filename):
                        suffix = "RED.jp2" if "_B04_" in info.filename else "NIR.jp2"
                        target = os.path.join(temp_dir, f"{prod_name}_{suffix}")

                        with open(target, "wb") as f:
                            f.write(z.read(info.filename))
                        extracted_files.append(target)
                        print(f"   -> Extracted: {suffix}")

        except Exception as e:
            print(f"❌ Extraction Error: {e}")
            return []

        os.remove(zip_path)
        return extracted_files

# ==========================================
# 3. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    BBOX_ROMANIA = [24.5, 45.5, 25.5, 46.0]

    # !!! CHECK CREDENTIALS !!!
    COP_USER = "farcastiberia@yahoo.com"
    COP_PASS = "Rospin_proiect2025"
    DOWNLOAD_LOCATION = "D:/SAFE_RO_Temp"

    try:
        # 1. Auth Cloud (Will force port 8080)
        drive = DriveManager("SAFE_RO_Cloud_Data")

        # 2. Download (Or find existing files)
        downloader = SmartDownloader(COP_USER, COP_PASS)
        files = downloader.find_and_process_latest(BBOX_ROMANIA, temp_dir=DOWNLOAD_LOCATION)

        # 3. Upload
        if files:
            for f_path in files:
                drive.upload_file(f_path)
                # Optional: Delete from local D: drive after upload
                # os.remove(f_path)
            print("\n🎉 SUCCESS: Files are in Google Drive!")
        else:
            print("No files found.")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")