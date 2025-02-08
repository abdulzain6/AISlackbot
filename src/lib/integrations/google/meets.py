import logging
from datetime import datetime, timedelta
from langchain.tools import tool
from typing import List
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from ....database.oauth_tokens import OAuthTokens, FirebaseOAuthStorage


class MeetsHandler:
    def __init__(
        self,
        token_storage: FirebaseOAuthStorage,
        client_id: str,
        client_secret: str,
        user_id: str,
        team_id: str
    ):
        """Initialize Meets handler with OAuth2 credentials."""
        logging.info(f"Initializing MeetsHandler for user {user_id} in team {team_id}")
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
            scopes=['https://www.googleapis.com/auth/calendar']  # Add required scopes here
        )

        # Refresh the token if it's expired
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
        
        # Verify if the token is valid and has the needed scopes
        if not self.credentials.valid or not self.credentials.has_scopes(['https://www.googleapis.com/auth/calendar']):
            logging.error("Token is invalid or has insufficient scopes")
            # If the token is invalid or doesn't have the required scopes, delete it
            self.token_storage.delete_tokens(user_id=user_id, team_id=team_id, integration_type="google")
            logging.info("Deleted invalid tokens from storage")
            raise ValueError("Invalid or insufficient scopes in the token. Token has been deleted. Ask user to signin to google.")
        
        # Create the Google Calendar service
        logging.info("Creating Google Calendar service")
        self.service = build('calendar', 'v3', credentials=self.credentials)
        logging.info("MeetsHandler initialization complete")

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

    def create_meeting(self, start_time: datetime, end_time: datetime, title: str, participants: list, description: str = "") -> str:
        """
        Create a Google Meet meeting, send email invitations to participants, and return the meeting link.
        
        :param start_time: UTC start time of the meeting
        :param end_time: UTC end time of the meeting
        :param title: Title of the meeting
        :param participants: List of email addresses of participants
        :param description: Optional description of the meeting
        :return: Google Meet link for the created meeting
        """
        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC',
            },
            'attendees': [{'email': email} for email in participants],
            'conferenceData': {
                'createRequest': {
                    'requestId': f"{title}-{start_time.timestamp()}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            },
        }

        event = self.service.events().insert(
            calendarId='primary',
            body=event,
            conferenceDataVersion=1,
            sendUpdates='all'  # This parameter ensures email invitations are sent
        ).execute()
        meet_link = event.get('hangoutLink')
        
        return meet_link

    def create_meeting_with_duration(self, start_time: datetime, duration_minutes: int, title: str, participants: list, description: str = "") -> str:
        """
        Create a Google Meet meeting with a specified duration and return the meeting link.
        
        :param start_time: UTC start time of the meeting
        :param duration_minutes: Duration of the meeting in minutes
        :param title: Title of the meeting
        :param participants: List of email addresses of participants
        :param description: Optional description of the meeting
        :return: Google Meet link for the created meeting
        """
        end_time = start_time + timedelta(minutes=duration_minutes)
        return self.create_meeting(start_time, end_time, title, participants, description)


def create_ai_tools_for_meets(    
    token_storage: FirebaseOAuthStorage,
    client_id: str,
    client_secret: str,
    user_id: str,
    team_id: str
) -> List:

    @tool
    def create_meeting(start_time: str, duration_minutes: int, title: str, participants: list[str], description: str = "") -> str:
        """
        Create a Google Meet meeting with a specified duration and return the meeting link.
        
        :param start_time: UTC start time of the meeting in ISO format (e.g., '2023-05-01T10:00:00')
        :param duration_minutes: Duration of the meeting in minutes
        :param title: Title of the meeting
        :param participants: Comma-separated list of email addresses of participants
        :param description: Optional description of the meeting
        :return: Google Meet link for the created meeting
        """
        try:
            meet_handler = MeetsHandler(
                token_storage=token_storage,
                client_id=client_id,
                client_secret=client_secret,
                user_id=user_id,
                team_id=team_id
            )
            start_datetime = datetime.fromisoformat(start_time)
            return meet_handler.create_meeting_with_duration(start_datetime, duration_minutes, title, participants, description)
        except Exception as e:
            import traceback
            traceback.print_exception(e)
            return f"Failed to create meeting: Error: {e}"

    return [create_meeting]