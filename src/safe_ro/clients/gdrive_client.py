import os
import tempfile
import streamlit as st
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive


class GDriveClient:
    def __init__(self):
        self.drive = self._auth()

    def _auth(self):
        """
        Authenticates with Google Drive using a local 'mycreds.txt' file.
        """
        creds_path = "mycreds.txt"
        gauth = GoogleAuth()

        # Case 1: Running on Streamlit Cloud with secrets
        if "gdrive_creds_json" in st.secrets:
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_creds:
                temp_creds.write(st.secrets["gdrive_creds_json"])
                temp_creds_path = temp_creds.name
            gauth.LoadCredentialsFile(temp_creds_path)
            os.unlink(temp_creds_path)

        # Case 2: Local development
        else:
            if not os.path.exists(creds_path):
                st.error(f"Google Drive credentials file ('{creds_path}') not found.")
                st.error(
                    "Please run 'python scripts/authenticate_gdrive.py' to create it."
                )
                return None

            gauth.LoadCredentialsFile(creds_path)
            if gauth.credentials is None:
                st.error(f"Credentials in '{creds_path}' are invalid.")
                st.error(
                    f"Please delete '{creds_path}' and run 'python scripts/authenticate_gdrive.py' again."
                )
                return None
            elif gauth.access_token_expired:
                try:
                    gauth.Refresh()
                    gauth.SaveCredentialsFile(creds_path)
                except Exception as e:
                    st.error(f"Failed to refresh Google Drive token: {e}")
                    st.error(
                        f"Please delete '{creds_path}' and run 'python scripts/authenticate_gdrive.py' again."
                    )
                    return None
            else:
                gauth.Authorize()

        return GoogleDrive(gauth)

    def get_file_list(self, folder_name="SAFE_RO_Cloud_Data"):
        """Lists all files in a specified Google Drive folder."""
        if not self.drive:
            return []

        try:
            folder_list = self.drive.ListFile(
                {
                    "q": f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
                }
            ).GetList()

            if not folder_list:
                st.warning(f"Google Drive folder '{folder_name}' not found.")
                return []

            folder_id = folder_list[0]["id"]
            files = self.drive.ListFile(
                {"q": f"'{folder_id}' in parents and trashed=false"}
            ).GetList()
            files.sort(key=lambda x: x["title"], reverse=True)
            return files
        except Exception as e:
            st.error(f"Failed to list files from Google Drive: {e}")
            return []

    def download_file(self, file_obj):
        """Downloads a Google Drive file to a temporary local file."""
        if not self.drive:
            return None

        try:
            ext = os.path.splitext(file_obj["title"])[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tfile:
                file_path = tfile.name

            file_obj.GetContentFile(file_path)
            return file_path
        except Exception as e:
            st.error(f"Failed to download '{file_obj['title']}': {e}")
            return None
