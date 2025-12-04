import os
from pydrive2.auth import GoogleAuth


def authenticate():
    """
    Runs the local web server authentication flow to create 'mycreds.txt'.
    """
    project_root = os.path.join(os.path.dirname(__file__), "..")
    client_secrets_path = os.path.join(project_root, "client_secrets.json")
    mycreds_path = os.path.join(project_root, "mycreds.txt")

    if not os.path.exists(client_secrets_path):
        print(f"Error: 'client_secrets.json' not found at '{client_secrets_path}'")
        print(
            "Please download it from Google Cloud Console and place it in the project root."
        )
        return

    gauth = GoogleAuth()
    gauth.settings["client_config_file"] = client_secrets_path
    gauth.settings["get_refresh_token"] = True

    try:
        print("Attempting to authenticate with Google Drive via local web server...")
        print(
            "Your browser should open for you to log in and authorize the application."
        )
        gauth.LocalWebserverAuth()
        gauth.SaveCredentialsFile(mycreds_path)
        print(f"Successfully authenticated and saved credentials to '{mycreds_path}'.")
    except Exception as e:
        print(f"An error occurred during authentication: {e}")
        print("Please try running the script again.")


if __name__ == "__main__":
    authenticate()
