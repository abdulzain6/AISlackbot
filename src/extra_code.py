@pubsub_fn.on_message_published(topic="slackbotai-gamil")
def handle_gmail_notification(event: pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]) -> None:
    """
    Receives Pub/Sub notifications for Gmail, stores the history ID,
    and prints new messages.
    
    Args:
        event (pubsub_fn.CloudEvent[pubsub_fn.MessagePublishedData]): The Pub/Sub event.
    """
    try:
        message_data = event.data.message.data
        decoded_message = base64.b64decode(message_data).decode('utf-8')
        logger.info(f"Received Gmail notification: {decoded_message}")
        
        # Parse the decoded message
        notification_data = json.loads(decoded_message)
        email_address = notification_data['emailAddress']
        new_history_id = int(notification_data['historyId'])
        
        # Initialize Firestore client
        db = firestore.Client()        
        # Get the last processed history ID from Firestore
        doc_ref = db.collection('gmail_history').document(email_address)
        doc = doc_ref.get()
        last_history_id = 0
        if doc.exists:
            last_history_id = doc.to_dict().get('last_history_id', 0)
        
        # Update the history ID in Firestore
        doc_ref.set({'last_history_id': new_history_id}, merge=True)
        bot = SlackBot(os.getenv("SLACK_BOT_TOKEN"))
        user = FirestoreUserStorage().get_first_user_by_email(email_address)
        if not user:
            print("User not found")
            return

        # Fetch new messages if there's a new history ID
        if new_history_id > last_history_id:
            print(f"New history ID detected. Fetching messages for {email_address}")
            message_string = fetch_and_print_new_messages(email_address, last_history_id, new_history_id)
            if message_string:
                response = generate_llm_response(
                    user_name=bot.get_user_real_name(user_id=user.user_id, team_id=user.team_name),
                    emails=message_string
                )
                if response.send:
                    print(f"Sending {response.message} .")
                    bot.send_direct_message(user.user_id, message=response.message, team_id=user.team_name)
                else:
                    print("Skipping emails because they aren't important.")
        else:
            print(f"No new changes for {email_address}")
        
    except Exception as e:
        logger.error(f"Error processing Gmail notification: {str(e)}", exc_info=True)
        print(f"Error processing Gmail notification: {str(e)}")


def fetch_and_print_new_messages(email_address: str, start_history_id: str, end_history_id: str) -> str:
    try:
        # Get the OAuth tokens
        token_manager = FirebaseOAuthStorage()
        user = FirestoreUserStorage().get_first_user_by_email(email_address)
        if not user:
            logger.warning("User not found!")
            return

        tokens = token_manager.get_tokens(user.user_id, user.team_name, "google")
        if not tokens:
            logger.warning("Tokens not found")
            return

        # Create credentials
        creds = Credentials(
            token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
        )
        
        # Build the Gmail API service
        service = build('gmail', 'v1', credentials=creds)
        
        # Fetch the history
        results = service.users().history().list(
            userId='me',
            startHistoryId=start_history_id
        ).execute()
        
        changes = results.get('history', [])
        
        new_messages = []
        for change in changes:
            messages_added = change.get('messagesAdded', [])
            for msg_added in messages_added:
                msg = msg_added.get('message', {})
                thread_id = msg.get('threadId', 'Unknown Thread ID')
                msg_id = msg.get('id', 'Unknown Message ID')
                label_ids = msg.get('labelIds', [])
                user_replied = 'SENT' in label_ids
                if 'UNREAD' not in label_ids:
                    continue
                # Fetch the complete message
                full_message = service.users().messages().get(userId='me', id=msg_id).execute()
                
                # Extract subject and sender
                headers = full_message.get('payload', {}).get('headers', [])
                subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), 'No Subject')
                sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), 'Unknown Sender')
                
                # Extract message body
                message_body = ''
                content_type = 'text/plain'
                if 'parts' in full_message.get('payload', {}):
                    for part in full_message['payload']['parts']:
                        if part.get('mimeType') in ['text/plain', 'text/html']:
                            message_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                            content_type = part.get('mimeType')
                            break
                elif 'body' in full_message.get('payload', {}):
                    message_body = base64.urlsafe_b64decode(full_message['payload']['body']['data']).decode('utf-8')
                    content_type = full_message['payload'].get('mimeType', 'text/plain')
                
                # Convert HTML to markdown if necessary
                if content_type == 'text/html':
                    h = html2text.HTML2Text()
                    h.ignore_links = False
                    message_body = h.handle(message_body)
                
                # Format the email information
                email_info = f"## Email Details\n\n"
                email_info += f"**Thread ID:** {thread_id}\n"
                email_info += f"**Subject:** {subject}\n"
                email_info += f"**From:** {sender}\n\n"
                email_info += f"### Message Content\n\n{message_body}\n"
                if user_replied:
                    email_info += "\n**Note:** The user has replied in this thread so it might be important.\n"
                new_messages.append(email_info)

        # Combine all new messages into one presentable string
        if new_messages:
            combined_messages = "# New Emails\n\n"
            for i, message in enumerate(new_messages, 1):
                combined_messages += f"## Email #{i}\n\n{message}\n\n---\n\n"
            
            logger.info(combined_messages)
            return combined_messages
        else:
            logger.info("No new messages found.")
            return "No new messages found."
        
    except Exception as e:
        logger.error(f"Error fetching new messages: {str(e)}", exc_info=True)
        return f"Error fetching new messages: {str(e)}"


def generate_llm_response(user_name: str, emails: str) -> RequestChatMessage:
    messages = [
        SystemMessage(
            content="""You are SlackbotAI, a helpful AI assistant. You will look at the new messages from users inbox and ask them if you can help generate a draft and reply them automatically.
            Only pick very important messages. THe user is a very busy man and has no time to address useless marketing emails or spam. Pick only important ones.
            PICK ONLY URGENT EMAILS, you have been picking very useless emails lately so lets change that.
            Make sure to include the thread id in your message and the draft also include what emails you can help with and what they contain.
            Note the message your gonna generate is going to be a chat message. Dont be too formal!"""
        ),
        HumanMessage(
            content=f"""The users name is {user_name}.
            Here is their inbox:
            {emails}
            Generate a slack chat message (not too formal) that mentions the super important emails they got and also offer them assistance in drafting and replying to them.
            You will only provide summary of important mails and request them thats it. Dont draft as of yet.
            Use emojis and be cheerful.
            Only send the request if the user has important messages. They are a busy person.
            Include thread ID.
            """
        )
    ]
    return ChatOpenAI(model="gpt-4o-mini").with_structured_output(RequestChatMessage).invoke(messages)

