import datetime
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from ....database.oauth_tokens import FirebaseOAuthStorage, OAuthTokens
from google.auth.transport.requests import Request
from typing import List, Optional
from datetime import datetime
from langchain.tools import tool

class GoogleCalendarManager:
    def __init__(
        self,
        token_storage: FirebaseOAuthStorage,
        client_id: str,
        client_secret: str,
        user_id: str,
        team_id: str
    ):
        """Initialize GoogleCalendarManager with OAuth2 credentials."""
        logging.info(f"Initializing GoogleCalendarManager for user {user_id} in team {team_id}")
        self.token_storage = token_storage
        self.user_id = user_id
        self.team_id = team_id

        tokens = token_storage.get_tokens(user_id=user_id, team_id=team_id, integration_type="google")
        if not tokens:
            raise ValueError("Tokens not found! Ask user to signin to google.")
        
        logging.info("Retrieved tokens from storage")
        
        self.credentials = Credentials(
            token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            expiry=datetime.utcfromtimestamp(tokens.expires_at),
            scopes=['https://www.googleapis.com/auth/calendar']
        )

        if not self.credentials.valid:
            logging.info("Credentials are invalid, attempting to refresh")
            try:
                self.refresh_access_token()
                logging.info("Successfully refreshed access token")
            except Exception as e:
                logging.error(f"Failed to refresh access token: {str(e)}")
                self.token_storage.delete_tokens(user_id=user_id, team_id=team_id, integration_type="google")
                logging.info("Deleted invalid tokens from storage")
                raise ValueError("Invalid or insufficient scopes in the token. Token has been deleted. Ask user to signin to google.")
        
        if not self.credentials.valid or not self.credentials.has_scopes(['https://www.googleapis.com/auth/calendar']):
            logging.error("Token is invalid or has insufficient scopes")
            self.token_storage.delete_tokens(user_id=user_id, team_id=team_id, integration_type="google")
            logging.info("Deleted invalid tokens from storage")
            raise ValueError("Invalid or insufficient scopes in the token. Token has been deleted. Ask user to signin to google.")
        
        logging.info("Creating Google Calendar service")
        self.service = build('calendar', 'v3', credentials=self.credentials)
        logging.info("GoogleCalendarManager initialization complete")

    def __del__(self):
        """Destructor to store new tokens back to the database."""
        logging.info("Storing new tokens")
        if hasattr(self, 'credentials') and self.credentials:
            expiry = self.credentials.expiry            
            self.token_storage.store_or_update_tokens(
                OAuthTokens(
                    user_id=self.user_id,
                    team_id=self.team_id,
                    integration_type="google",
                    access_token=self.credentials.token,
                    refresh_token=self.credentials.refresh_token,
                    expires_at=expiry.timestamp()
                )
            )

    def refresh_access_token(self) -> None:
        """Refreshes the access token if it is expired."""
        if self.credentials.expired:
            self.credentials.refresh(Request())

    def create_event(self, summary: str, start_time: datetime, end_time: datetime, description: Optional[str] = None, location: Optional[str] = None) -> str:
        """Create a new event in the user's primary calendar."""
        event = {
            'summary': summary,
            'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
        }
        if description:
            event['description'] = description
        if location:
            event['location'] = location

        try:
            created_event = self.service.events().insert(calendarId='primary', body=event).execute()
            return created_event['id']
        except Exception as e:
            logging.error(f"Failed to create event: {str(e)}")
            raise

    def delete_event(self, event_id: str) -> None:
        """Delete an event from the user's primary calendar."""
        try:
            self.service.events().delete(calendarId='primary', eventId=event_id).execute()
        except Exception as e:
            logging.error(f"Failed to delete event: {str(e)}")
            raise

    def list_events(self, max_results: int = 10) -> List[dict]:
        """List upcoming events from the user's primary calendar."""
        now = datetime.utcnow().isoformat() + 'Z'
        try:
            events_result = self.service.events().list(calendarId='primary', timeMin=now,
                maxResults=max_results, singleEvents=True,
                orderBy='startTime').execute()
            return events_result.get('items', [])
        except Exception as e:
            logging.error(f"Failed to list events: {str(e)}")
            raise

def create_ai_tools_for_calendar(    
    token_storage: FirebaseOAuthStorage,
    client_id: str,
    client_secret: str,
    user_id: str,
    team_id: str
) -> List:
    """Create AI tools for Google Calendar operations."""

    @tool
    def create_google_calendar_event(summary: str, start_time: datetime, end_time: datetime, description: Optional[str] = None, location: Optional[str] = None) -> str:
        """Create a new Google Calendar event."""
        try:
            manager = GoogleCalendarManager(token_storage=token_storage, client_id=client_id, client_secret=client_secret, user_id=user_id, team_id=team_id)
            return manager.create_event(summary, start_time, end_time, description, location)
        except Exception as e:
            return f"Failed to create event: {str(e)}"

    @tool
    def delete_google_calendar_event(event_id: str) -> str:
        """Delete a Google Calendar event."""
        try:
            manager = GoogleCalendarManager(token_storage=token_storage, client_id=client_id, client_secret=client_secret, user_id=user_id, team_id=team_id)
            manager.delete_event(event_id)
            return f"Event {event_id} deleted successfully"
        except Exception as e:
            return f"Failed to delete event: {str(e)}"

    @tool
    def list_google_calendar_events(max_results: int = 10) -> str:
        """List upcoming Google Calendar events."""
        try:
            manager = GoogleCalendarManager(token_storage=token_storage, client_id=client_id, client_secret=client_secret, user_id=user_id, team_id=team_id)
            events = manager.list_events(max_results)
            return "\n".join([f"{event['summary']} - {event['start'].get('dateTime', event['start'].get('date'))}" for event in events])
        except Exception as e:
            return f"Failed to list events: {str(e)}"

    return [create_google_calendar_event, delete_google_calendar_event, list_google_calendar_events]
