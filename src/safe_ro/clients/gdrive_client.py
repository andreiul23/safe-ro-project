import os
import tempfile
import streamlit as st
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

class GDriveClient:
    def __init__(self):
        self.drive = self._auth()

    @st.cache_resource
    def _auth(_self):
        """
        Authenticates with Google Drive using Streamlit secrets for deployment
        or a local 'mycreds.txt' file for development.
        The '_self' is used to make this method cacheable by Streamlit.
        """
        creds_path = "mycreds.txt"
        
        # For deployment, create credentials from Streamlit secrets
        if not os.path.exists(creds_path) and "gdrive_creds_json" in st.secrets:
            with open(creds_path, "w") as f:
                f.write(st.secrets["gdrive_creds_json"])

        gauth = GoogleAuth()
        
        if not os.path.exists(creds_path):
            st.error(f"❌ Google Drive credentials file ('{creds_path}') not found.")
            st.info("For local development, run authentication locally. For deployment, add 'gdrive_creds_json' to your Streamlit secrets.")
            return None
            
        gauth.LoadCredentialsFile(creds_path)

        if gauth.credentials is None:
            st.error(f"❌ Credentials in '{creds_path}' are invalid. Please re-authenticate.")
            return None
        elif gauth.access_token_expired:
            try:
                gauth.Refresh()
                gauth.SaveCredentialsFile(creds_path)
            except Exception as e:
                st.error(f"Failed to refresh Google Drive token: {e}")
                return None
        else:
            gauth.Authorize()
            
        return GoogleDrive(gauth)

    def get_file_list(self, folder_name="SAFE_RO_Cloud_Data"):
        """Lists all files in a specified Google Drive folder."""
        if not self.drive:
            return []
            
        try:
            # 1. Find folder ID
            folder_list = self.drive.ListFile(
                {'q': f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"}
            ).GetList()

            if not folder_list:
                st.warning(f"Google Drive folder '{folder_name}' not found.")
                return []

            folder_id = folder_list[0]['id']

            # 2. List files inside the folder
            query = f"'{folder_id}' in parents and trashed=false"
            files = self.drive.ListFile({'q': query}).GetList()

            # Sort files by title (useful for date-based naming)
            files.sort(key=lambda x: x['title'], reverse=True)
            return files
        except Exception as e:
            st.error(f"Failed to list files from Google Drive: {e}")
            return []

    def download_file(self, file_obj):
        """Downloads a Google Drive file object to a temporary local file."""
        if not self.drive:
            return None
            
        try:
            # Create a temp file with the correct extension to preserve the format
            ext = os.path.splitext(file_obj['title'])[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tfile:
                file_path = tfile.name
            
            # Download the file content
            file_obj.GetContentFile(file_path)
            return file_path
        except Exception as e:
            st.error(f"Failed to download file '{file_obj['title']}' from Google Drive: {e}")
            return None
