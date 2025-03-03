from ..lib.platforms import Platform
from ..lib.tools import ToolName
from ..database.api_keystore import APIKeyRepository, APIKey
from typing import Tuple
from atlassian import Jira

def verify_jira_api_key(api_key: str, jira_domain: str, jira_email: str) -> Tuple[bool, str]:
    """
    Verify the Jira API key by making a test request using the atlassian-python-api package.
    
    Args:
        api_key: The Jira API key.
        jira_domain: The Jira domain (e.g., "your-domain.atlassian.net").
        jira_email: The Jira account email.
    
    Returns:
        A tuple (is_valid, message) indicating whether the API key is valid.
    """
    try:
        jira_url = f"{jira_domain}"
        jira = Jira(url=jira_url, username=jira_email, password=api_key)
        user = jira.myself()
        if user:
            return True, "API key verified successfully"
        return False, "Failed to verify API key: No user details returned."
    except Exception as e:
        return False, f"Error verifying API key: {str(e)}"

def upsert_jira_key(
    team_id: str,
    user_id: str,
    app_name: Platform,
    metadata: dict,
    form_values: dict
):
    api_key = form_values.get("jira_api_key")
    assert api_key is not None, "Key is required"

    # Verify the key before storing it
    jira_domain = form_values.get("jira_domain")
    assert jira_domain is not None, "Jira domain is required"

    jira_email = form_values.get("jira_email")
    assert jira_email is not None, "Jira email is required"

    is_valid, message = verify_jira_api_key(api_key, jira_domain, jira_email)
    if not is_valid:
        raise ValueError(f"Invalid Jira API key: {message}")

    # If verification succeeds, store the key
    APIKeyRepository().create_key(
        APIKey(
            user_id=None,
            team_id=team_id,
            integration_name=ToolName.JIRA.value.lower(),
            app_name=app_name.value.lower(),
            api_key=api_key,
            metadata={"jira_domain" : jira_domain, "jira_email": jira_email}
        )
    )

    return {"status": "success", "message": "Jira API key verified and stored successfully"}

FORM_EVENT_HANDLERS = {
    "jira_api_key": upsert_jira_key,
}