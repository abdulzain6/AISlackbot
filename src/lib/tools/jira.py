import logging
import redis
from sqlalchemy.orm import Session
from langchain_core.tools import Tool, tool
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms.platform_helper import PlatformHelper, TextFormElement
from ...database.api_keystore import APIKey
from .tool_maker import ToolMaker, ToolConfig
from atlassian import Jira


class JiraConfig(ToolConfig): ...


class InvalidKeyException(Exception): ...


class JiraTools(ToolMaker):
    REQUESTED_OAUTH_INTEGRATIONS = []

    def __init__(
        self,
        tool_config: JiraConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        session: Session,
        redis_client: redis.Redis,
    ):
        self.session = session
        self.platform_helper = platform_helper

    def send_api_key_request_form(self):
        try:
            success = self.platform_helper.send_form_dm(
                "jira_api_key",
                elements=[
                    TextFormElement(
                        type="text",
                        label="Jira Domain",
                        action_id="jira_domain",
                        placeholder="Enter your Jira Domain",
                    ),
                    TextFormElement(
                        type="text",
                        label="Jira API Key",
                        action_id="jira_api_key",
                        placeholder="Enter your Jira API Key",
                    ),
                    TextFormElement(
                        type="text",
                        label="Jira Email",
                        action_id="jira_email",
                        placeholder="Enter your Jira Email",
                    ),
                ],
                title=":key: Please provide your Jira API Key. This allows me to interact with your Jira account and do some interesting stuff. :rocket:.",
                user_id=self.platform_helper.owner_uid,
                extra_context=" Instructions here : https://id.atlassian.com/manage-profile/security/api-tokens :rocket:",
            )
            assert success is True, "Failed to send form DM"
            return "Successfully sent form DM to workplace owner"
        except Exception as e:
            logging.error(f"Failed to send form DM: {e}")
            return f":warning: Failed to send form DM: {e}"

    def get_available_projects_and_issue_types(self, jira: Jira) -> str:
        """Fetches all Jira projects and their available issue types, returning a formatted string."""

        projects = jira.projects()
        issue_types = jira.get_issue_types()

        # Create project info string
        project_info = "\n".join(
            [f"- {p['key']}: {p['name']} ({p['projectTypeKey']})" for p in projects]
        )

        # Create a mapping from project ID to project name and key
        project_id_to_details = {
            p["id"]: {"name": p["name"], "key": p["key"]} for p in projects
        }

        # Group issue types by project
        project_issue_types = {}

        for issue_type in issue_types:
            # Check if the issue type has a project scope
            scope = issue_type.get("scope", {})
            project_id = scope.get("project", {}).get("id")

            # Skip issue types without a project
            if not project_id or project_id not in project_id_to_details:
                continue

            # Add issue type to the project's list
            project_key = project_id_to_details[project_id]["key"]
            if project_key not in project_issue_types:
                project_issue_types[project_key] = []
            project_issue_types[project_key].append(issue_type["name"])

        # Format the project issue types
        issue_types_info = ""
        for project_key, types in project_issue_types.items():
            project_name = next(
                (p["name"] for p in projects if p["key"] == project_key), "Unknown"
            )
            issue_types_info += f"\n**{project_key}: {project_name}**\n"
            issue_types_info += "\n".join([f"- {t}" for t in types])
            issue_types_info += "\n"

        return (
            f"**Available Jira Projects:**\n{project_info}\n\n"
            f"**Available Issue Types by Project:**{issue_types_info}"
        )

    def search_users(self, jira: Jira, query: str, min_results: int = 10) -> str:
        """
        Searches for Jira users matching a query string (typically an email).
        Returns a formatted string with display names and account IDs of Atlassian accounts.

        Args:
            jira: The Jira client
            query: The search query (email or name to match against)
            min_results: Minimum number of results to target

        Returns:
            A formatted string with user information
        """
        import difflib

        # Start with initial batch of users
        start = 0
        batch_size = 50
        all_users = []

        # Keep fetching all available users
        while True:
            try:
                users_batch = jira.users_get_all(start=start, limit=batch_size)
                if not users_batch:
                    break  # No more users to process

                # Filter for Atlassian accounts
                for user in users_batch:
                    # Skip non-Atlassian accounts
                    if user.get("accountType") != "atlassian":
                        continue

                    # Get values to match against
                    display_name = user.get("displayName", "").lower()
                    email = user.get("emailAddress", "").lower()

                    query_lower = query.lower()

                    # If the query looks like an email, extract the username part for better matching
                    if "@" in query_lower:
                        query_name_part = query_lower.split("@")[0]
                        # For name similarity, use the extracted username part
                        name_similarity = difflib.SequenceMatcher(
                            None, display_name, query_name_part
                        ).ratio()
                        # For direct email matching, still use the full email
                        email_similarity = difflib.SequenceMatcher(
                            None, email, query_lower
                        ).ratio()
                    else:
                        # If not an email, just do direct comparison
                        name_similarity = difflib.SequenceMatcher(
                            None, display_name, query_lower
                        ).ratio()
                        email_similarity = difflib.SequenceMatcher(
                            None, email, query_lower
                        ).ratio()

                    # Use the highest similarity score
                    similarity = max(name_similarity, email_similarity)

                    all_users.append(
                        {
                            "displayName": user.get("displayName", "Unknown"),
                            "accountId": user.get("accountId", "Unknown"),
                            "similarity": similarity,
                        }
                    )

                # If no more users to fetch, break
                if len(users_batch) < batch_size:
                    break

                # Move to next batch
                start += batch_size

            except Exception as e:
                logging.error(f"Error fetching Jira users: {e}")
                break

        # Sort all users by similarity (highest first)
        all_users.sort(key=lambda x: x["similarity"], reverse=True)

        # Get at least min_results users if available (or all users if less than min_results)
        result_users = all_users[:min_results]
        # Format the results as a string
        if not result_users:
            return "No matching users found"

        result = "**Matching Jira Users:**\n"
        for i, user in enumerate(result_users, 1):
            similarity_percentage = int(user["similarity"] * 100)
            result += f"{i}. **{user['displayName']}** (Account ID: {user['accountId']}, Match: {similarity_percentage}%)\n"
        return result

    def create_issue(
        self,
        jira: Jira,
        summary: str,
        project_key: str,
        issue_type: str,
        description: str = None,
        assignee_account_id: str = None,
    ):
        """
        Creates a new Jira issue with the provided details.

        Args:
            jira: The Jira client
            summary: Summary/title of the issue
            project_key: Project key where the issue will be created
            issue_type: Type of issue to create
            description: Optional description for the issue
            assignee_account_id: Optional account ID of the user to assign the issue to

        Returns:
            The created issue object
        """
        fields = dict(
            summary=summary,
            project=dict(key=project_key),
            issuetype=dict(name=issue_type),
            description=description,
        )

        # Add assignee to fields if provided
        if assignee_account_id:
            fields["assignee"] = dict(accountId=assignee_account_id)

        return jira.create_issue(fields=fields)

    def search_issues(
        self, jira: Jira, jql: str, max_results: int = 10, add_description: bool = False
    ):
        """
        Searches for Jira issues using JQL and returns a formatted string of results.

        Args:
            jira: The Jira client
            jql: JQL search query string
            max_results: Maximum number of results to return (default: 10)
            add_description: Whether to include issue descriptions in the output (default: False)

        Returns:
            A formatted string with issue information
        """
        issues = jira.jql(jql, limit=max_results)
        lines = []

        for issue in issues["issues"]:
            key = issue.get("key", "N/A")
            fields = issue.get("fields", {})
            summary = fields.get("summary", "N/A")
            status = fields.get("status", {}).get("name", "N/A")
            project = fields.get("project", {})
            project_name = project.get("name", "N/A")
            project_key = project.get("key", "N/A")
            assignee = fields.get("assignee", {})
            priority = fields.get("priority", {}).get("name", "N/A")

            if not assignee:
                assignee = {}
            assignee_name = assignee.get("displayName", "Unassigned")
            assignee_account = assignee.get("accountId", "N/A")

            issue_info = (
                f"Issue {key}:\n"
                f"  Summary: {summary}\n"
                f"  Status: {status}\n"
                f"  Project: {project_name} ({project_key})\n"
                f"  Assignee: {assignee_name} (Account ID: {assignee_account})\n"
                f"  Priority: {priority}\n"
            )

            # Only include description if add_description is True
            if add_description:
                description = fields.get("description", "N/A")
                issue_info = issue_info.replace(
                    f"  Summary: {summary}\n",
                    f"  Summary: {summary}\n  Description: {description}\n",
                )

            lines.append(issue_info)

        return "\n".join(lines)

    def make_jira_object(self, key: APIKey) -> Jira:
        try:
            jira = Jira(
                url=key.metadata.get("jira_domain"),
                username=key.metadata.get("jira_email"),
                password=key.api_key,
            )
            jira.myself()
        except Exception as e:
            raise InvalidKeyException(
                f"Invalid Jira API Key: {e}. Please contact the owner to update the API Key."
            )
        return jira

    def delete_issue(self, jira: Jira, issue_key: str):
        return jira.delete_issue(issue_key)

    def create_ai_tools(self) -> list[Tool]:

        @tool
        def ask_owner_for_jira_api_key():
            "Used to request the owner's Jira API Key."
            return self.send_api_key_request_form()

        @tool
        def search_jira_users(query: str):
            "Used to search for users in Jira."
            key = APIKey.read(
                self.session,
                team_id=self.platform_helper.team_id,
                app_name=self.platform_helper.platform_name,
                integration_name="jira",
            )
            if not key:
                self.send_api_key_request_form()
                return "Jira is not configured yet, A message has been sent to the owner to configure it."

            try:
                jira = self.make_jira_object(key)
            except InvalidKeyException:
                return "Invalid Jira API Key. Please contact the owner to update the API Key."

            return self.search_users(jira, query, min_results=5)

        @tool
        def get_available_jira_projects_and_issue_types():
            "Used to get all available Jira projects and issue types."
            key = APIKey.read(
                self.session,
                team_id=self.platform_helper.team_id,
                app_name=self.platform_helper.platform_name,
                integration_name="jira",
            )
            if not key:
                self.send_api_key_request_form()
                return "Jira is not configured yet, A message has been sent to the owner to configure it."

            try:
                jira = self.make_jira_object(key)
            except InvalidKeyException:
                return "Invalid Jira API Key. Please contact the owner to update the API Key."

            return self.get_available_projects_and_issue_types(jira)

        @tool
        def search_jira_issues(jql: str, add_description: bool = False):
            "Used to search for jira issues, it returns only 5 results max. Takes in jql query as input."
            key = APIKey.read(
                self.session,
                team_id=self.platform_helper.team_id,
                app_name=self.platform_helper.platform_name,
                integration_name="jira",
            )
            if not key:
                self.send_api_key_request_form()
                return "Jira is not configured yet, A message has been sent to the owner to configure it."

            try:
                jira = self.make_jira_object(key)
            except InvalidKeyException:
                return "Invalid Jira API Key. Please contact the owner to update the API Key."

            if "currentUser" in jql:
                return "currentUser is not supported in jql query. Search users first then use the account id from there."

            return self.search_issues(
                jira, jql=jql, add_description=add_description, max_results=5
            )
        
        @tool
        def create_jira_issue(
            summary: str,
            project_key: str,
            issue_type: str,
            description: str = None,
            assignee_account_id: str = None,
        ):
            "Used to create a new issue in Jira."
            key = APIKey.read(
                self.session,
                team_id=self.platform_helper.team_id,
                app_name=self.platform_helper.platform_name,
                integration_name="jira",
            )
            if not key:
                self.send_api_key_request_form()
                return "Jira is not configured yet, A message has been sent to the owner to configure it."

            try:
                jira = self.make_jira_object(key)
            except InvalidKeyException:
                return "Invalid Jira API Key. Please contact the owner to update the API Key."

            return self.create_issue(
                jira=jira,
                summary=summary,
                project_key=project_key,
                issue_type=issue_type,
                description=description,
                assignee_account_id=assignee_account_id,
            )
        
        @tool
        def delete_jira_issue(issue_key: str):
            "Used to delete a Jira issue."
            key = APIKey.read(
                self.session,
                team_id=self.platform_helper.team_id,
                app_name=self.platform_helper.platform_name,
                integration_name="jira",
            )
            if not key:
                self.send_api_key_request_form()
                return "Jira is not configured yet, A message has been sent to the owner to configure it."

            try:
                jira = self.make_jira_object(key)
            except InvalidKeyException:
                return "Invalid Jira API Key. Please contact the owner to update the API Key."

            return self.delete_issue(jira=jira, issue=issue_key)

        return [
            ask_owner_for_jira_api_key,
            get_available_jira_projects_and_issue_types,
            search_jira_issues,
            search_jira_users,
            create_jira_issue,
            delete_jira_issue
        ]


if __name__ == "__main__":
    jira = JiraTools(
        JiraConfig(), None, {}
    )
    print(
        jira.delete_issue(
            Jira(
                url="https://altodia.atlassian.net/",
                username="abdul.zian@altodia.com",
                password="ATATT3xFfGF0gjBK2MAYTnHSsQ9eJZeKq96Q_q_fwuacFH8QYXv1s__filmFUDuqQyr6nOafd_IaEFKOMRhbbVFFe_-sYeoyySS2bBOCPGIh4pL6SLYPAfB2ThGIn1P9Zchsl-RFssP_c3klXX0Xf9zkkGzO7i2_smSz1ElOkj-xHIrphuKpr7c=51B57A25",
            ),
            issue_key="UTKAI-142"
        )
    )
