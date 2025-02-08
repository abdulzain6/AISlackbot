import json
import urllib.parse
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from .. import OAuthBase

class ZoomMeetingManager(OAuthBase):
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = "https://zoom.us/oauth/authorize"
        self.token_url = "https://zoom.us/oauth/token"
        self.meeting_url = "https://api.zoom.us/v2/users/me/meetings"
        self.base_url = "https://api.zoom.us/v2"

    def _get_encoded_credentials(self) -> str:
        import base64
        credentials = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(credentials.encode()).decode()

    def generate_oauth_link(self, state: Optional[Dict[str, str]] = None) -> str:
        """Generate the OAuth authorization URL with an optional state parameter."""
        encoded_state = urllib.parse.quote(json.dumps(state)) if state else ""
        return (
            f"{self.auth_url}?response_type=code&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}&state={encoded_state}"
        )

    def handle_callback(self, code: str) -> Dict[str, str]:
        """Handle the OAuth callback to retrieve access and refresh tokens."""
        response = requests.post(
            self.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            },
            auth=(self.client_id, self.client_secret)
        )
        response.raise_for_status()
        data = response.json()
        
        expires_in = data.get('expires_in', 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": expires_at.isoformat()
        }

    def refresh_access_token(self, access_token: str, refresh_token: str) -> Dict[str, str]:
        """Refresh the access token using the provided refresh token."""
        headers = {
            "Authorization": f"Basic {self._get_encoded_credentials()}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        response = requests.post(self.token_url, headers=headers, data=data)
        response.raise_for_status()
        data = response.json()

        expires_in = data.get('expires_in', 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)

        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": expires_at.isoformat()
        }

    def create_meeting(self, access_token: str, topic: str, agenda: str, 
                    start_time: datetime = None, duration: int = 60,
                    attendees: List[str] = None, force_email: bool = False) -> Dict:
        """
        Create a Zoom meeting with configurable email notifications.
        
        Args:
            access_token (str): OAuth token for authentication
            topic (str): Meeting topic/name
            agenda (str): Meeting agenda/description
            start_time (datetime, optional): Meeting start time. If None, creates instant meeting
            duration (int, optional): Meeting duration in minutes. Defaults to 60
            attendees (List[str], optional): List of attendee email addresses
            force_email (bool, optional): Send emails even for instant meetings. Defaults to False
            
        Returns:
            dict: Zoom API response containing meeting details
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        is_scheduled = bool(start_time)
        
        # Base payload with common settings
        payload = {
            "topic": topic,
            "type": 2 if is_scheduled else 1,  # 2 for scheduled, 1 for instant
            "agenda": agenda,
            "settings": {
                "host_video": True,
                "participant_video": False,
                "join_before_host": False,
                "mute_upon_entry": True,
                "waiting_room": True,
                "meeting_authentication": True,
                "audio": "both",
                "use_pmi": False,
                # Email settings based on meeting type
                "registrants_email_notification": is_scheduled or force_email,
                "registrants_confirmation_email": is_scheduled or force_email,
                "email_notification": is_scheduled or force_email
            }
        }
        
        # Add scheduling information if provided
        if start_time:
            payload.update({
                "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timezone": "UTC",
                "duration": duration
            })
        
        # Add attendees if provided
        if attendees and (is_scheduled or force_email):
            payload["settings"].update({
                "meeting_invitees": [{"email": email} for email in attendees]
            })
        
        try:
            response = requests.post(
                self.meeting_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            meeting_data = response.json()
            
            # Send invitations for scheduled meetings or if forced
            if attendees and (is_scheduled or force_email):
                self._send_invitations(
                    meeting_id=meeting_data['id'],
                    access_token=access_token,
                    attendees=attendees
                )
            
            # Add helpful metadata about email notifications
            meeting_data["meeting_info"] = {
                "scheduled": is_scheduled,
                "emails_enabled": is_scheduled or force_email,
                "duration_minutes": duration,
                "num_attendees": len(attendees) if attendees else 0,
                "join_url": meeting_data.get("join_url"),
                "meeting_id": meeting_data.get("id"),
                "password": meeting_data.get("password", ""),
                "notification_status": "Emails will be sent" if (is_scheduled or force_email) else "No emails will be sent"
            }
            
            return meeting_data
            
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Failed to create meeting: {str(e)}"
            )

    def _send_invitations(self, meeting_id: str, access_token: str, attendees: List[str]) -> None:
        """Helper method to send meeting invitations to attendees."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        invitation_url = f"{self.meeting_url}/{meeting_id}/registrants"
        
        for email in attendees:
            payload = {
                "email": email,
                "auto_approve": True
            }
            
            try:
                response = requests.post(invitation_url, headers=headers, json=payload)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"Warning: Failed to send invitation to {email}: {str(e)}")
    


if __name__ == "__main__":
    manager = ZoomMeetingManager(
        "wefvMyg_R5SprBW43HPfA", "1zJtl0EqMl9nQB554wUWdd2Jhg9UJ8dR", "https://zoom-oauth-callback-lffbg6lsda-uc.a.run.app/"
    )
