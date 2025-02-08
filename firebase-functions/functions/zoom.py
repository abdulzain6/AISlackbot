import json
import urllib.parse
from typing import Dict
import requests


class ZoomMeetingManager:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = "https://zoom.us/oauth/authorize"
        self.token_url = "https://zoom.us/oauth/token"
        self.meeting_url = "https://api.zoom.us/v2/users/me/meetings"
        self.access_tokens: Dict[str, str] = {}  # Store access tokens per team/user

    def generate_oauth_link(self, user_id: str, team_id: str) -> str:
        """Generate an OAuth link with additional data in the state parameter."""
        # Encode additional data in the state parameter as JSON, then URL encode
        state_data = json.dumps({"user_id": user_id, "team_id": team_id})
        encoded_state = urllib.parse.quote(state_data)
        return (
            f"{self.auth_url}?response_type=code&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}&state={encoded_state}"
        )

    def exchange_code_for_token(self, code: str) -> tuple:
        """Exchange authorization code for an access token."""
        response = requests.post(
            self.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            auth=(self.client_id, self.client_secret)
        )
        print(response.text)
        response.raise_for_status()
        data = response.json()
        return data["access_token"], data["refresh_token"], data["expires_in"]

    def create_meeting_with_recording(self, access_token: str, topic: str, agenda: str) -> Dict:
        """Create a Zoom meeting with recording enabled."""
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "topic": topic,
            "type": 2,  # Scheduled meeting
            "agenda": agenda,
            "settings": {
                "auto_recording": "cloud"
            }
        }
        response = requests.post(self.meeting_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    
if __name__ == "__main__":
    manager = ZoomMeetingManager(
        "wefvMyg_R5SprBW43HPfA", "1zJtl0EqMl9nQB554wUWdd2Jhg9UJ8dR", "http://localhost:3000/"
    )
    print(manager.generate_oauth_link("test_user", "test_team"))