from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/blogger"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(
        "config/client_secrets.json",
        SCOPES
    )

    creds = flow.run_local_server(port=0)

    print("\n=== ADD THIS TO .env ===\n")
    print("BLOGGER_CLIENT_ID=", creds.client_id)
    print("BLOGGER_CLIENT_SECRET=", creds.client_secret)
    print("BLOGGER_REFRESH_TOKEN=", creds.refresh_token)

if __name__ == "__main__":
    main()