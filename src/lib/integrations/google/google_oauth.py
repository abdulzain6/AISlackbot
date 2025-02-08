from datetime import datetime
from google_auth_oauthlib.flow import Flow
from typing import Dict, Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from langchain.tools import tool
from .. import OAuthBase
import os, json

class GoogleOAuth(OAuthBase):
    def __init__(self, client_secrets_file: str, redirect_uri: str, scopes: Optional[list] = None, **kwargs):
        self.client_secrets_file = client_secrets_file
        self.redirect_uri = redirect_uri
        self.scopes = scopes if scopes else [
            "https://www.googleapis.com/auth/meetings.space.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar"
        ]
        self.flow = Flow.from_client_secrets_file(
            self.client_secrets_file,
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )

    def generate_oauth_link(self, state: str = None) -> str:
        """
        Generate the OAuth authorization URL for Google Drive with an optional state parameter.
        """
        auth_url, _ = self.flow.authorization_url(prompt='consent', state=state)
        return auth_url

    def create_ai_tools(self, user_id: str, team_id: str):
        """
        Create AI tools and generate an OAuth link with user_id and team_id in the state parameter.
        """
        @tool
        def generate_signin_with_google_link(*args, **kwargs):
            "Used to make a signin link so user can use google services."
            state = json.dumps({"user_id": user_id, "team_id": team_id})
            oauth_link = self.generate_oauth_link(state)
            return f"Ask the user nicely to login using this link: {oauth_link}"
        
        return [generate_signin_with_google_link]

    def handle_callback(self, code: str) -> Dict[str, str]:
        """
        Handle the OAuth callback to retrieve access and refresh tokens.
        """
        self.flow.fetch_token(code=code)

        # Retrieve the credentials.
        credentials = self.flow.credentials

        # Store the access and refresh tokens.
        tokens = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expires_in": int((credentials.expiry - datetime.utcnow()).total_seconds()),
            "expires_at": credentials.expiry.isoformat(),
        }
        return tokens
    
    def refresh_access_token(self, access_token: str, refresh_token: str) -> Dict[str, str]:
        """
        Refresh the access token using the provided refresh token.
        """
        # Initialize credentials using the provided access token and refresh token
        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.flow.client_config["client_id"],
            client_secret=self.flow.client_config["client_secret"]
        )

        # Refresh the credentials
        credentials.refresh(GoogleRequest())

        # Return the new access token and expiry
        tokens = {
            "access_token": credentials.token,
            "expires_in": credentials.expiry.isoformat()
        }
        return tokens
    

if __name__ == "__main__":
    import json
    auth = GoogleOAuth(
        os.getenv("SECRETS_FILE"),
        os.getenv("GOOGLE_REDIRECT_URI")
    )
    link = auth.generate_oauth_link(json.dumps({"team_id" : "test_team" , "user_id" : "test_user"}))
    print(link)
