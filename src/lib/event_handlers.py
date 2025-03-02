from ..database.api_keystore import APIKeyRepository, APIKey


def upsert_jira_key(team_id: str, user_id: str, integration_name: str, metadata: dict, form_values: dict):
    assert form_values.get("key") is not None, "Key is required"
    APIKeyRepository().create_key(
        APIKey(
            user_id=user_id,
            team_id=team_id,
            integration_name=integration_name,
            key=form_values.get("key"),
        )
    )


FORM_EVENT_HANDLERS = {
    "upsert_jira_key": upsert_jira_key,
}