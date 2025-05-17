import base64
import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langchain.tools import tool
from ....database.oauth_tokens import FirebaseOAuthStorage, OAuthTokens, TokenRequest


class GmailHandler:
    def __init__(
        self,
        token_storage: FirebaseOAuthStorage,
        client_id: str,
        client_secret: str,
        user_id: str,
        team_id: str
    ):
        """Initialize Gmail handler with OAuth2 credentials."""
        logging.info(f"Initializing GmailHandler for user {user_id} in team {team_id}")
        self.token_storage = token_storage
        self.user_id = user_id
        self.team_id = team_id

        tokens = token_storage.get_tokens(user_id=user_id, team_id=team_id, integration_type="google")
        if not tokens:
            raise ValueError("Tokens not found! Ask user to sign in to Google.")

        logging.info("Retrieved tokens from storage")

        self.credentials = Credentials(
            token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            expiry=datetime.utcfromtimestamp(tokens.expires_at),
            scopes=['https://www.googleapis.com/auth/gmail.modify']  # Full read/write access to Gmail
        )

        # Refresh the token if it's expired
        if not self.credentials.valid:
            logging.info("Credentials are invalid, attempting to refresh")
            try:
                self.refresh_access_token()
                logging.info("Successfully refreshed access token")
            except Exception as e:
                logging.error(f"Failed to refresh access token: {str(e)}")
                self.token_storage.delete_tokens(
                    TokenRequest(
                        user_id=user_id, 
                        team_id=team_id, 
                        integration_type="google",
                        app_name=self.c
                    )
                )
                logging.info("Deleted invalid tokens from storage")
                raise ValueError("Invalid or insufficient scopes in the token. Token has been deleted. Ask user to sign in to Google.")

        # Verify if the token is valid and has the needed scopes
        if not self.credentials.valid or not self.credentials.has_scopes(['https://www.googleapis.com/auth/gmail.modify']):
            logging.error("Token is invalid or has insufficient scopes")
            # If the token is invalid or doesn't have the required scopes, delete it
            self.token_storage.delete_tokens(user_id=user_id, team_id=team_id, integration_type="google")
            logging.info("Deleted invalid tokens from storage")
            raise ValueError("Invalid or insufficient scopes in the token. Token has been deleted. Ask user to sign in to Google.")

        # Create the Gmail service
        logging.info("Creating Gmail service")
        self.service = build('gmail', 'v1', credentials=self.credentials)
        logging.info("GmailHandler initialization complete")

    def refresh_access_token(self) -> None:
        """Refreshes the access token if it is expired."""
        if self.credentials.expired:
            self.credentials.refresh(Request())

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

    def get_inbox_emails(self, page_number: int = 1, batch_size: int = 10, unread_only: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches a specific page of emails with sender, subject, snippet, date sent, sender's name, thread ID, and latest message.

        Args:
            page_number (int): The page number to fetch (default is 1).
            batch_size (int): The number of emails to fetch per page (default is 10).
            unread_only (bool): If True, fetch only unread emails (default is False).

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing email information.
        """
        self.refresh_access_token()
        service = build('gmail', 'v1', credentials=self.credentials)

        # Initialize for pagination
        email_data = []
        page_token = None
        current_page = 1

        # Set up query for unread emails if requested
        query = 'is:unread' if unread_only else None

        # Loop to fetch the specified page
        while current_page <= page_number:
            results = service.users().messages().list(
                userId='me',
                labelIds=['INBOX'],
                pageToken=page_token,
                maxResults=batch_size,
                q=query
            ).execute()

            messages = results.get('messages', [])
            page_token = results.get('nextPageToken')

            # Stop if the target page is reached
            if current_page == page_number:
                for message in messages:
                    msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()

                    headers = msg['payload']['headers']
                    email_info = {
                        'sender': '',
                        'sender_name': '',
                        'subject': '',
                        'snippet': msg.get('snippet', ''),
                        'date_sent': '',
                        'thread_id': msg['threadId'],
                        'latest_message': {}  # Add latest message object
                    }

                    # Extract relevant header information
                    for header in headers:
                        if header['name'] == 'From':
                            email_info['sender'] = header['value']
                            if '<' in header['value']:
                                email_info['sender_name'], email_info['sender'] = header['value'].split('<')
                                email_info['sender_name'] = email_info['sender_name'].strip()
                                email_info['sender'] = email_info['sender'].replace('>', '').strip()
                            else:
                                email_info['sender_name'] = email_info['sender']
                        elif header['name'] == 'Subject':
                            email_info['subject'] = header['value']
                        elif header['name'] == 'Date':
                            clean_date = re.sub(r"\s\([A-Za-z]+\)", "", header['value'])
                            try:
                                email_info['date_sent'] = datetime.strptime(clean_date, '%a, %d %b %Y %H:%M:%S %z').isoformat()
                            except ValueError:
                                email_info['date_sent'] = clean_date  # Use raw format if parsing fails

                    latest_message = self._get_message_body(msg['payload'])
                    email_info['latest_message'] = {
                        'sender': email_info['sender'],
                        'content': latest_message
                    }

                    email_data.append(email_info)

            # Move to the next page if more results are available
            if not page_token:
                break  # No more pages available
            current_page += 1

        return email_data

    def get_signature(self, service, user_email: str) -> str:
        send_as = service.users().settings().sendAs().list(userId=user_email).execute()
        send_as_email = send_as['sendAs'][0]['sendAsEmail']
        signature_info = service.users().settings().sendAs().get(userId=user_email, sendAsEmail=send_as_email).execute()
        return signature_info.get('signature', '')

    def send_email(
        self, recipient: str, body: str, thread_id: str | None = None, message_id: str | None = None, subject: str = None
    ):
        service = build('gmail', 'v1', credentials=self.credentials)

        # Automatically get sender_email
        sender_info = service.users().getProfile(userId='me').execute()
        sender_email = sender_info['emailAddress']

        signature = self.get_signature(service, sender_email)
        separator = '<hr><!-- Signature Starts -->'
        full_body = f"{body}{separator}{signature}" if signature else body

        msg = MIMEMultipart()
        msg["To"] = recipient
        msg["From"] = sender_email
        if thread_id and message_id:
            msg['In-Reply-To'] = message_id
            msg['References'] = message_id

        # If we're replying and no subject is provided, fetch the original subject
        if subject is None:
            original_message = service.users().messages().get(userId='me', id=message_id, format='metadata', metadataHeaders=['subject']).execute()
            original_subject = next((header['value'] for header in original_message['payload']['headers'] if header['name'].lower() == 'subject'), 'No Subject')
            subject = f"Re: {original_subject}" if not original_subject.lower().startswith('re:') else original_subject

        # If subject is still None (not a reply), use a default subject
        if subject is None:
            subject = "No Subject"

        msg["Subject"] = subject
        # Add both plain text and HTML parts
        text_part = MIMEText(full_body, 'plain')
        msg.attach(text_part)

        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        message_body = {"raw": raw_message}

        if thread_id:
            message_body['threadId'] = thread_id

        try:
            sent_message = (
                service.users()
                .messages()
                .send(userId='me', body=message_body)
                .execute()
            )
            return sent_message
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def get_thread_messages(self, thread_id: str):
        """
        Get all messages from a thread in a clean format and mark the thread as read.

        Args:
            thread_id (str): The ID of the thread to fetch messages from.

        Returns:
            list: A list of dictionaries containing message information.

        Raises:
        ThreadNotFoundException: If the specified thread_id is not found.
        """
        service = build('gmail', 'v1', credentials=self.credentials)
        try:
            thread = service.users().threads().get(userId='me', id=thread_id).execute()
        except Exception as e:
            if 'Not Found' in str(e):
                raise ValueError(f"Thread with ID {thread_id} not found.") from e
            raise  # Re-raise other exceptions

        messages = []

        for msg in thread['messages']:
            message_data = service.users().messages().get(userId='me', id=msg['id']).execute()

            headers = message_data['payload']['headers']
            sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown')
            subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
            date = next((header['value'] for header in headers if header['name'].lower() == 'date'), 'Unknown')

            body = self._get_message_body(message_data['payload'])

            messages.append({
                'message_id': msg['id'],
                'sender': sender.split('<')[-1].strip('>') if '<' in sender else sender,
                'subject': subject,
                'date': date,
                'body': body
            })

        # Mark the thread as read
        try:
            service.users().threads().modify(
                userId='me',
                id=thread_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logging.info(f"Thread {thread_id} marked as read.")
        except Exception as e:
            logging.error(f"Failed to mark thread {thread_id} as read: {str(e)}")

        return messages

    def _get_message_body(self, payload):
        """Helper method to extract message body, handling all types of content."""
        if 'body' in payload and payload['body'].get('data'):
            return self._decode_and_clean(payload['body']['data'])
        elif 'parts' in payload:
            text_content = ""
            html_content = ""
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    text_content = self._decode_and_clean(part['body']['data'])
                elif part['mimeType'] == 'text/html':
                    html_content = self._decode_and_clean(part['body']['data'])
                elif 'parts' in part:
                    # Handle nested multipart messages
                    nested_content = self._get_message_body(part)
                    if nested_content:
                        return nested_content

            # Prefer plain text over HTML if both are available
            return text_content if text_content else html_content
        return "No readable content"

    def _decode_and_clean(self, encoded_content):
        """Decode and clean the content."""
        content = base64.urlsafe_b64decode(encoded_content).decode('utf-8')

        # Remove HTML tags if present
        content = re.sub(r'<[^>]+>', '', content)

        # Remove quoted text and extra information
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            if not line.strip().startswith('>') and not re.match(r'^On .+wrote:$', line.strip()):
                cleaned_lines.append(line)

        # Join the cleaned lines and remove any leading/trailing whitespace
        cleaned_content = '\n'.join(cleaned_lines).strip()

        # Remove any remaining empty lines
        cleaned_content = re.sub(r'\n\s*\n', '\n', cleaned_content)

        return cleaned_content

    def send_watch_request(self, topic_name: str):
        # Create credentials object from tokens
        # Build the Gmail API service
        service = build('gmail', 'v1', credentials=self.credentials)

        # Prepare the watch request body
        watch_request = {
            'topicName': topic_name,
            'labelIds': ['INBOX'],
            'labelFilterAction': 'include'
        }

        try:
            # Send the watch request
            response = service.users().watch(userId='me', body=watch_request).execute()
            print(f"Watch request sent successfully. Response: {response}")
            return response
        except Exception as e:
            print(f"Error sending watch request: {str(e)}")
            return None



def create_ai_tools_for_gmail(    
    token_storage: FirebaseOAuthStorage,
    client_id: str,
    client_secret: str,
    user_id: str,
    team_id: str
) -> List:

    @tool
    def get_user_gmails(page_number: int = 1, batch_size: int = 10, unread_only: bool = False) -> str:
        """
        Retrieve user's Gmail messages from their inbox.

        This function fetches a specific page of emails from the user's Gmail inbox.
        It can optionally filter for unread emails only.

        Args:
            page_number (int): The page number of emails to fetch. Defaults to 1.
            batch_size (int): The number of emails to fetch per page. Defaults to 10.
            unread_only (bool): If True, fetch only unread emails. Defaults to False.

        Returns:
            str: A string representation of the list of email data dictionaries.
                 Each dictionary contains information about an email such as sender,
                 subject, snippet, date sent, etc.

        Raises:
            Exception: If there's an error in fetching the emails. The error message
                       is returned as a string.
        """
        try:
            handler = GmailHandler(
                token_storage=token_storage,
                client_id=client_id,
                client_secret=client_secret,
                user_id=user_id,
                team_id=team_id
            )
            return handler.get_inbox_emails(page_number=page_number, batch_size=batch_size, unread_only=unread_only)
        except Exception as e:
            import traceback
            traceback.print_exception(e)
            return f"Failed to get emails: Error: {e}"

    @tool
    def send_email(recipient: str, body: str, thread_id: str | None = None, message_id: str | None = None, subject: str | None = None, sure: str = "") -> str:
        """
        Send an email using the user's Gmail account.

        Args:
            recipient (str): The email address of the recipient.
            body (str): The body of the email.
            thread_id (str, optional): The ID of the thread to reply to.
            message_id (str, optional): The ID of the message to reply to.
            subject (str, optional): The subject of the email. If not provided and replying, the original subject will be used.

        Returns:
            str: A string indicating the success or failure of sending the email.

        Raises:
            Exception: If there's an error in sending the email or if a placeholder is found in the body.
        """
        try:
            # Check if the first word is "Subject"
            if body.strip().lower().startswith("subject"):
                raise ValueError("Subject has its own parameter. Please use the 'subject' argument instead of including it in the body.")

            # Check for placeholders in the body
            placeholder_match = re.search(r'\[([^\]]+)\]', body)
            if placeholder_match:
                placeholder = placeholder_match.group(1)
                raise ValueError(f"Failed to send email because a placeholder '{placeholder}' was found. Please fill it.")

            # Check if thread_id and message_id are None
            if not sure:
                raise ValueError("You're trying to send someone a new email. Set sure parameter to 'yes' if you want to continue. Ask the user to confirm, also show them draft and who are you sending to.")

            if thread_id is None and message_id is None and not sure:
                raise ValueError("You're trying to send someone a new email. Are you sure you don't want to send a reply? Set sure parameter to 'yes' if you want to continue. Ask the user to confirm if they dont want to send a reply instead, also show them draft.")

            handler = GmailHandler(
                token_storage=token_storage,
                client_id=client_id,
                client_secret=client_secret,
                user_id=user_id,
                team_id=team_id
            )
            result = handler.send_email(recipient, body, thread_id, message_id, subject)
            return f"Email sent successfully. Message ID: {result['id']}" if result else "Failed to send email."
        except ValueError as ve:
            return str(ve)
        except Exception as e:
            import traceback
            traceback.print_exception(e)
            return f"Failed to send email: Error: {e}"
    @tool
    def list_thread_messages(thread_id: str) -> str:
        """
        Get all messages from a specific thread in the user's Gmail account.

        Args:
            thread_id (str): The ID of the thread to fetch messages from.

        Returns:
            str: A string representation of the list of message data dictionaries.
                 Each dictionary contains information about a message such as sender,
                 subject, date, and body.

        Raises:
            Exception: If there's an error in fetching the thread messages. The error message
                       is returned as a string.
        """
        try:
            handler = GmailHandler(
                token_storage=token_storage,
                client_id=client_id,
                client_secret=client_secret,
                user_id=user_id,
                team_id=team_id
            )
            return handler.get_thread_messages(thread_id)
        except Exception as e:
            import traceback
            traceback.print_exception(e)
            return f"Failed to get thread messages: Error: {e}"

    return [get_user_gmails, send_email, list_thread_messages]
