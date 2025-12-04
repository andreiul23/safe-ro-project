import os
import sys
import time
import requests
import zipfile
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

# Add src directory to path to allow for sibling imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# --- DEFINING REGIONS ---
REGIONS = {
    "Fagaras": [24.5, 45.5, 25.5, 46.0],
    "Iasi": [27.5, 47.0, 27.8, 47.3],
    "Timisoara": [21.1, 45.6, 21.4, 45.9],
}


# ==========================================
# 1. GOOGLE DRIVE MANAGER
# ==========================================
class DriveManager:
    def __init__(self, folder_name="SAFE_RO_Cloud_Data"):
        self.creds_path = os.path.join(os.path.dirname(__file__), "..", "mycreds.txt")
        self.drive = self._auth()
        if self.drive:
            self.folder_id = self._get_or_create_folder(folder_name)
        else:
            self.folder_id = None

    def _auth(self):
        gauth = GoogleAuth()
        try:
            gauth.LoadCredentialsFile(self.creds_path)
            if gauth.credentials is None:
                print("[AUTH] No valid credentials. Please run interactively first.")
                return None
            elif gauth.access_token_expired:
                gauth.Refresh()
            else:
                gauth.Authorize()
            gauth.SaveCredentialsFile(self.creds_path)
            return GoogleDrive(gauth)
        except Exception as e:
            print(f"[AUTH] Error: {e}")
            return None

    def _get_or_create_folder(self, folder_name):
        # ... (rest of the class is unchanged)
        file_list = self.drive.ListFile(
            {
                "q": f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            }
        ).GetList()
        if file_list:
            return file_list[0]["id"]
        folder = self.drive.CreateFile(
            {"title": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        )
        folder.Upload()
        return folder["id"]

    def upload_file(self, local_path, region_tag):
        # We prepend the Region Name to the file so the App knows where it belongs!
        filename = os.path.basename(local_path)
        final_name = f"{region_tag}_{filename}"

        existing = self.drive.ListFile(
            {
                "q": f"title='{final_name}' and '{self.folder_id}' in parents and trashed=false"
            }
        ).GetList()
        if existing:
            print(f"[CLOUD] ✅ {final_name} exists (Skipping)")
            return existing[0]["id"]

        print(f"[CLOUD] ⏳ Uploading {final_name}...")
        gfile = self.drive.CreateFile(
            {"title": final_name, "parents": [{"id": self.folder_id}]}
        )
        gfile.SetContentFile(local_path)
        for i in range(3):
            try:
                gfile.Upload()
                print("[CLOUD] ✅ Success!")
                return gfile["id"]
            except Exception as e:
                print(f"[CLOUD] ❌ Upload failed: {e}")
                time.sleep(5)
        return None


# ==========================================
# 2. HYBRID DOWNLOADER
# ==========================================
class HybridDownloader:
    AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.token = None

    def authenticate(self):
        r = requests.post(
            self.AUTH_URL,
            data={
                "client_id": "cdse-public",
                "username": self.username,
                "password": self.password,
                "grant_type": "password",
            },
        )
        if r.status_code == 200:
            self.token = r.json()["access_token"]
        else:
            raise Exception(f"Login Failed: {r.text}")

    def _download_and_extract(self, product, temp_dir, mode="S2"):
        prod_name = product["Name"]
        print(f"[CDSE] 🎯 Selected: {prod_name} ({mode})")
        os.makedirs(temp_dir, exist_ok=True)
        zip_path = os.path.join(temp_dir, f"{prod_name}.zip")

        # 1. Download
        if not (os.path.exists(zip_path) and zipfile.is_zipfile(zip_path)):
            initial_url = f"{self.SEARCH_URL}({product['Id']})/$value"
            r_head = requests.get(
                initial_url,
                headers={"Authorization": f"Bearer {self.token}"},
                allow_redirects=False,
                stream=True,
            )
            final_url = (
                r_head.headers["Location"]
                if r_head.status_code in [301, 302, 303, 307, 308]
                else initial_url
            )

            print(f"[CDSE] ⬇️ Downloading {mode} ZIP...")
            downloaded = False
            while not downloaded:
                try:
                    curr = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
                    headers = {"Authorization": f"Bearer {self.token}"}
                    m = "wb"
                    if curr > 0:
                        headers["Range"] = f"bytes={curr}-"
                        m = "ab"

                    with requests.get(
                        final_url, headers=headers, stream=True, timeout=60
                    ) as r:
                        if r.status_code == 416:
                            break
                        r.raise_for_status()
                        with open(zip_path, m) as f:
                            for chunk in r.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    f.write(chunk)
                    downloaded = True
                except Exception as e:
                    print(f"[CDSE] ❌ Download failed: {e}")
                    time.sleep(5)
        else:
            print("[CACHE] ✅ Using local ZIP.")

        # 2. Extract
        files = []
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                for info in z.infolist():
                    target = None
                    if mode == "S2":
                        if (
                            ("_B04_" in info.filename or "_B08_" in info.filename)
                            and info.filename.endswith(".jp2")
                            and "R60m" not in info.filename
                        ):
                            suffix = (
                                "RED.jp2" if "_B04_" in info.filename else "NIR.jp2"
                            )
                            target = os.path.join(temp_dir, f"{prod_name}_{suffix}")
                    elif mode == "S1":
                        if (
                            "measurement" in info.filename
                            and "-vv-" in info.filename.lower()
                            and info.filename.endswith(".tiff")
                        ):
                            target = os.path.join(temp_dir, f"{prod_name}_VV.tiff")

                    if target:
                        with open(target, "wb") as f:
                            f.write(z.read(info.filename))
                        files.append(target)
        except Exception as e:
            print(f"Extract Error: {e}")
        return files

    def process_region(self, region_name, bbox, temp_dir):
        if not self.token:
            self.authenticate()
        polygon = f"SRID=4326;POLYGON(({bbox[0]} {bbox[1]}, {bbox[2]} {bbox[1]}, {bbox[2]} {bbox[3]}, {bbox[0]} {bbox[3]}, {bbox[0]} {bbox[1]}))"

        # Try S2 (Clear)
        print(f"\n--- Processing Region: {region_name} ---")
        filter_s2 = f"Collection/Name eq 'SENTINEL-2' and OData.CSC.Intersects(area=geography'{polygon}') and ContentDate/Start ge 2024-01-01T00:00:00.000Z and Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/Value lt 20.00)"
        r = requests.get(
            self.SEARCH_URL,
            params={
                "$filter": filter_s2,
                "$orderby": "ContentDate/Start desc",
                "$top": 1,
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )
        s2_res = r.json().get("value", [])

        if s2_res:
            return self._download_and_extract(s2_res[0], temp_dir, "S2")

        # Try S1 (Radar)
        print(f"[CDSE] {region_name} is cloudy. Switching to Radar.")
        filter_s1 = f"Collection/Name eq 'SENTINEL-1' and OData.CSC.Intersects(area=geography'{polygon}') and ContentDate/Start ge 2024-01-01T00:00:00.000Z and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/Value eq 'GRD') and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'sensorMode' and att/Value eq 'IW')"
        r = requests.get(
            self.SEARCH_URL,
            params={
                "$filter": filter_s1,
                "$orderby": "ContentDate/Start desc",
                "$top": 1,
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )
        s1_res = r.json().get("value", [])

        if s1_res:
            return self._download_and_extract(s1_res[0], temp_dir, "S1")
        return []


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage: python safe_ro_cloud.py <copernicus_user> <copernicus_pass> <download_location>"
        )
        sys.exit(1)

    COP_USER = sys.argv[1]
    COP_PASS = sys.argv[2]
    DOWNLOAD_LOCATION = sys.argv[3]

    try:
        drive = DriveManager("SAFE_RO_Cloud_Data")
        if drive.folder_id:
            dl = HybridDownloader(COP_USER, COP_PASS)
            for region_name, bbox in REGIONS.items():
                files = dl.process_region(region_name, bbox, DOWNLOAD_LOCATION)
                for f in files:
                    drive.upload_file(f, region_name)
            print("\n🎉 All Regions Updated Successfully!")
    except Exception as e:
        print(f"Error: {e}")
