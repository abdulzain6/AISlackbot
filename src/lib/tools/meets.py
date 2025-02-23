import logging
from datetime import datetime, timedelta
from typing import Callable, Optional
from langchain.tools import tool
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ...globals import OAUTH_INTEGRATIONS
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms import Platform, send_dm
from ...database.oauth_tokens import OAuthTokens, FirebaseOAuthStorage
from .tool_maker import ToolMaker, ToolConfig
from langchain_core.tools import Tool


class InvalidCredsException(Exception):
    pass


class MeetsConfig(ToolConfig):
    send_dm_callable: Callable[[Platform, str, str], None] = send_dm
    platform: Platform = Platform.SLACK
    user_id: str
    team_id: str
    token_storage: FirebaseOAuthStorage = None
    oauth_client: OAuthClient = OAUTH_INTEGRATIONS["google"]

    class Config:
        arbitrary_types_allowed = True


class MeetsHandler(ToolMaker):
    def __init__(
        self,
        tool_config: MeetsConfig,
    ):
        """Initialize Meets handler with OAuth2 credentials."""
        logging.info(
            f"Initializing MeetsHandler for user {tool_config.user_id} in team {tool_config.team_id}"
        )

        if not tool_config.token_storage:
            tool_config.token_storage = FirebaseOAuthStorage()

        self.token_storage = tool_config.token_storage
        self.team_user_id = tool_config.user_id
        self.team_id = tool_config.team_id
        self.platform = tool_config.platform
        self.send_dm_callable = tool_config.send_dm_callable
        self.oauth_client = tool_config.oauth_client

    def make_service(self):
        tokens = self.token_storage.get_tokens(
            user_id=self.team_user_id,
            team_id=self.team_id,
            integration_type="google",
            app_name=self.platform.value.lower(),
        )
        if not tokens:
            raise InvalidCredsException("No tokens found for user")

        logging.info("Retrieved tokens from storage")

        credentials = Credentials(
            token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.oauth_client.client_id,
            client_secret=self.oauth_client.client_secret,
            expiry=datetime.utcfromtimestamp(tokens.expires_at),
            scopes=[
                "https://www.googleapis.com/auth/calendar"
            ],  # Add required scopes here
        )

        # Refresh the token if it's expired
        if not credentials.valid:
            logging.info("Credentials are invalid, attempting to refresh")
            try:
                if credentials.expired:
                    credentials.refresh(Request())
                    logging.info("Successfully refreshed access token")
            except Exception as e:
                logging.error(f"Failed to refresh access token: {str(e)}")
                self.token_storage.delete_tokens(
                    user_id=self.team_user_id,
                    team_id=self.team_id,
                    integration_type="google",
                    app_name=self.platform.value.lower(),
                )
                logging.info("Deleted invalid tokens from storage")
                raise InvalidCredsException(
                    "Invalid or insufficient scopes in the token. Token has been deleted. Ask user to signin to google."
                )

        # Verify if the token is valid and has the needed scopes
        if not credentials.valid or not credentials.has_scopes(
            ["https://www.googleapis.com/auth/calendar"]
        ):
            logging.error("Token is invalid or has insufficient scopes")
            # If the token is invalid or doesn't have the required scopes, delete it
            self.token_storage.delete_tokens(
                user_id=self.team_user_id,
                team_id=self.team_id,
                integration_type="google",
                app_name=self.platform.value.lower(),
            )
            logging.info("Deleted invalid tokens from storage")
            raise InvalidCredsException(
                "Invalid or insufficient scopes in the token. Token has been deleted. Ask user to signin to google."
            )

        # Create the Google Calendar service
        logging.info("Creating Google Calendar service")
        return build("calendar", "v3", credentials=credentials), credentials

    def update_credentials(self, credentials: Credentials):
        """Destructor to store new tokens back to the database."""
        logging.info("Storing new tokens")
        expiry = credentials.expiry
        self.token_storage.store_or_update_tokens(
            OAuthTokens(
                user_id=self.team_user_id,
                team_id=self.team_id,
                integration_type="google",
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                expires_at=expiry.timestamp(),
                app_name=self.platform.value.lower(),
            )
        )

    def create_meeting(
        self,
        service,
        start_time: datetime,
        end_time: datetime,
        title: str,
        participants: list,
        description: str = "",
    ) -> str:
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
            "summary": title,
            "description": description,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC",
            },
            "attendees": [{"email": email} for email in participants],
            "conferenceData": {
                "createRequest": {
                    "requestId": f"{title}-{start_time.timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        event = (
            service.events()
            .insert(
                calendarId="primary",
                body=event,
                conferenceDataVersion=1,
                sendUpdates="all",  # This parameter ensures email invitations are sent
            )
            .execute()
        )
        meet_link = event.get("hangoutLink")

        return meet_link

    def create_meeting_with_duration(
        self,
        service,
        start_time: datetime,
        duration_minutes: int,
        title: str,
        participants: list,
        description: str = "",
    ) -> str:
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
        return self.create_meeting(
            service, start_time, end_time, title, participants, description
        )

    def create_event(self, service, summary: str, start_time: datetime, end_time: datetime, description: Optional[str] = None, location: Optional[str] = None) -> str:
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
            created_event = service.events().insert(calendarId='primary', body=event).execute()
            return created_event['id']
        except Exception as e:
            logging.error(f"Failed to create event: {str(e)}")
            raise

    def delete_event(self, service, event_id: str) -> None:
        """Delete an event from the user's primary calendar."""
        try:
            service.events().delete(calendarId='primary', eventId=event_id).execute()
        except Exception as e:
            logging.error(f"Failed to delete event: {str(e)}")
            raise

    def list_events(self, service, max_results: int = 10) -> list[dict]:
        """List upcoming events from the user's primary calendar."""
        now = datetime.utcnow().isoformat() + 'Z'
        try:
            events_result = service.events().list(calendarId='primary', timeMin=now,
                maxResults=max_results, singleEvents=True,
                orderBy='startTime').execute()
            return events_result.get('items', [])
        except Exception as e:
            logging.error(f"Failed to list events: {str(e)}")
            raise
    def create_ai_tools(self) -> list[Tool]:
        
        def handle_service_creation():
            """Handle service creation and authentication errors."""
            service, credentials = self.make_service()
            return service, credentials

        def send_authentication_dm():
            """Send Direct Message with authentication link."""
            link = self.oauth_client.get_authorization_url(
                {
                    "team_id": self.team_id,
                    "team_user_id": self.team_user_id,
                    "app_name": self.platform.value.lower(),
                }
            )
            self.send_dm_callable(
                self.platform,
                f"Please Authenticate to use this functionality: <{link}|Click here to authenticate>",
                self.team_user_id,
            )

        @tool
        def create_meeting(
            start_time: str,
            duration_minutes: int,
            title: str,
            participants: list[str],
            description: str = "",
        ) -> str:
            """Create a Google Meet meeting with a specified duration and return the meeting link."""
            try:
                service, credentials = handle_service_creation()
                start_datetime = datetime.fromisoformat(start_time)
                meeting_link = self.create_meeting_with_duration(
                    service, start_datetime, duration_minutes, title, participants, description
                )
                self.update_credentials(credentials)
                return meeting_link
            except InvalidCredsException as e:
                logging.error(f"Invalid Creds: {e}")
                send_authentication_dm()
                return "Failed to create meeting: User needs to authenticate. Check your DM for the link."
            except Exception as e:
                logging.error(f"Error: {e}")
                return f"Failed to create meeting: Error: {e}"

        @tool
        def create_google_calendar_event(
            summary: str,
            start_time: datetime,
            end_time: datetime,
            description: Optional[str] = None,
            location: Optional[str] = None,
        ) -> str:
            """Create a new Google Calendar event."""
            try:
                service, credentials = handle_service_creation()
                event_id = self.create_event(service, summary, start_time, end_time, description, location)
                self.update_credentials(credentials)
                return f"Event created successfully with ID: {event_id}"
            except InvalidCredsException as e:
                logging.error(f"Invalid Creds: {e}")
                send_authentication_dm()
                return "Failed to create event: User needs to authenticate. Check your DM for the link."
            except Exception as e:
                logging.error(f"Failed to create event: {str(e)}")
                return f"Failed to create event: {str(e)}"

        @tool
        def delete_google_calendar_event(event_id: str) -> str:
            """Delete a Google Calendar event."""
            try:
                service, credentials = handle_service_creation()
                self.delete_event(service, event_id)
                self.update_credentials(credentials)
                return f"Event {event_id} deleted successfully"
            except InvalidCredsException as e:
                logging.error(f"Invalid Creds: {e}")
                send_authentication_dm()
                return "Failed to delete event: User needs to authenticate. Check your DM for the link."
            except Exception as e:
                logging.error(f"Failed to delete event: {str(e)}")
                return f"Failed to delete event: {str(e)}"

        @tool
        def list_google_calendar_events(max_results: int = 10) -> str:
            """List upcoming Google Calendar events. Returns a string with event summaries, start times, and event IDs."""
            try:
                service, credentials = handle_service_creation()
                events = self.list_events(service, max_results)
                self.update_credentials(credentials)
                return "\n".join([
                    f"ID: {event['id']} - Summary: {event['summary']} - Start: {event['start'].get('dateTime', event['start'].get('date'))}"
                    for event in events
                ])
            except InvalidCredsException as e:
                logging.error(f"Invalid Creds: {e}")
                send_authentication_dm()
                return "Failed to list events: User needs to authenticate. Check your DM for the link."
            except Exception as e:
                logging.error(f"Failed to list events: {str(e)}")
                return f"Failed to list events: {str(e)}"

        return [
            create_google_calendar_event,
            delete_google_calendar_event,
            list_google_calendar_events,
            create_meeting,
        ]
