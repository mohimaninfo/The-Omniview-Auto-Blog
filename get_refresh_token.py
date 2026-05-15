from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/blogger"]

flow = InstalledAppFlow.from_client_secrets_file(
    "config/client_secrets.json",
    SCOPES
)

creds = flow.run_local_server(port=0)

print("\nREFRESH TOKEN:\n", creds.refresh_token)
print("\nACCESS TOKEN:\n", creds.token)