import sys
import glob
import webbrowser
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

def main():
    secret_files = glob.glob("client_secret*.json")
    if not secret_files:
        print("\n[ERROR] 'client_secret.json' was not found in this folder!", flush=True)
        sys.exit(1)

    secret_file = secret_files[0]
    print(f"Using credentials file: {secret_file}", flush=True)
    
    flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
    
    # Run local server on port 8080
    print("\nStarting local server on port 8080...", flush=True)
    creds = flow.run_local_server(
        port=8080,
        prompt="consent",
        access_type="offline",
        open_browser=True
    )

    env_content = f"""CLIENT_ID={creds.client_id}
CLIENT_SECRET={creds.client_secret}
REFRESH_TOKEN={creds.refresh_token}
"""
    with open(".env", "w") as f:
        f.write(env_content)

    print("=" * 60, flush=True)
    print("SUCCESS! Credentials have been saved automatically to .env", flush=True)
    print("=" * 60, flush=True)
    print(f"CLIENT_ID:     {creds.client_id}", flush=True)
    print(f"CLIENT_SECRET: {creds.client_secret}", flush=True)
    print(f"REFRESH_TOKEN: {creds.refresh_token}", flush=True)
    print("=" * 60, flush=True)

if __name__ == "__main__":
    main()
