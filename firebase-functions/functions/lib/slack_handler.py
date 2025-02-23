from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

class SlackBot:
    """
    A Slack bot for interacting with users and workspaces.
    """

    def __init__(self, bot_token: str):
        """
        Initialize the Slack API client with the given bot token.
        Args:
        bot_token (str): The bot token of your Slack app.
    """
        self.client = WebClient(token=bot_token)

    def get_user_real_name(self, user_id: str, team_id: str) -> str:
        """
            Fetches the real name of a user given their user ID and team ID.
        Args:
                user_id (str): User ID whose name is to be retrieved.
                team_id (str): Team ID of the workspace.
        Returns:
                str: The real name of the user or an error message if not found.
        """
        try:
            # Set team_id for the request
            response = self.client.users_info(user=user_id, team_id=team_id)
            user_info = response.get("user", {})
            return user_info.get("real_name", "Real name not found")
        except SlackApiError as e:
            error_message = e.response.get("error", "Unknown error")
            return f"Error: {error_message}"

    def send_direct_message(self, user_id: str, message: str, team_id: str) -> None:
        """
        Sends a formatted direct message to a user via Slack, using blocks for a clean and presentable look.
        Args:
            user_id (str): The Slack User ID of the recipient.
            message (str): The markdown formatted message to send.
            team_id (str): Team ID of the workspace.

        Raises:
            SlackApiError: If the Slack API call fails.
        """
        try:
            # Open a direct message (IM) channel with the user
            response = self.client.conversations_open(users=user_id, team_id=team_id)
            channel_id = response["channel"]["id"]

            # Define the blocks to format the message
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": ":sparkles: *Powered by SlackBotAI*"
                        }
                    ]
                }
            ]

            # Send the message to the channel using blocks
            self.client.chat_postMessage(
                channel=channel_id,
                blocks=blocks,
                text=message  # Fallback for notification
            )
            print(f"Message sent to user {user_id} with formatted blocks.")
        
        except SlackApiError as e:
            print(f"Error sending message: {e.response.get('error', 'Unknown error')}")

    def get_workspaces_and_users(self) -> dict[str, list[str]]:
        """
        Fetches all workspaces the bot is added to and lists their users.

        Returns:
            Dict[str, List[str]]: A dictionary mapping workspace names to lists of user names.
        """
        workspaces_users = {}

        try:
            # Get all workspaces the bot is added to
            teams_response = self.client.auth_teams_list(limit=100)
            teams = teams_response.get("teams", [])

            for team in teams:
                team_id = team["id"]
                team_name = team["name"]
                print(f"Fetching users for workspace: {team_name} (ID: {team_id})")

                # Get users for the workspace
                users_response = self.client.users_list(team_id=team_id, limit=200)
                users = users_response.get("members", [])
                user_names = [user["id"] for user in users]
                workspaces_users[team_name] = user_names

        except SlackApiError as e:
            print(f"Error: {e.response['error']}")

        return workspaces_users
