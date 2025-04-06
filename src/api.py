from .database.engine import get_db
from .database.oauth_tokens import OAuthTokens
from .database.slack_tokens import SlackToken
from .database.users import User
from .globals import OAUTH_INTEGRATIONS
from sqlalchemy.orm import Session
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
import logging, dotenv



dotenv.load_dotenv("src/.env.api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI()


@app.get("/slack/oauth_redirect")
def slack_oauth_callback(code: str, session: Session = Depends(get_db)):
    logger.info("Received Slack OAuth callback request")
    if not code:
        logger.error("Missing 'code' parameter in callback")
        raise HTTPException(status_code=400, detail="Missing 'code' parameter in callback")

    client = OAUTH_INTEGRATIONS["slack"]

    token_response = client.exchange_code_for_token(code, validate=False)
    team_data = token_response.get('team', {})
    SlackToken(
        team_id=team_data.get('id'),
        team_name=team_data.get('name'),
        bot_user_id=token_response.get('bot_user_id'),
        bot_access_token=token_response.get('access_token'),
        is_enterprise_install=token_response.get('is_enterprise_install', False)
    ).save(session)

    logger.info(f"Successfully stored Slack token for team {team_data.get('name')}")

    return JSONResponse(content={"message": "Authorization successful"}, status_code=200)

@app.get("/google/oauth_redirect")
def google_oauth_callback(code: str, state: str, session: Session = Depends(get_db)):
    logger.info("Received Google OAuth callback request")
    if not code or not state:
        logger.error("Missing required parameters in callback")
        raise HTTPException(status_code=400, detail="Missing 'code' or 'state' in callback")

    google_client = OAUTH_INTEGRATIONS["google"]

    try:
        logger.info("Decoding state parameter")
        decoded_state = google_client.decode_jwt_token(state)
        if "team_id" not in decoded_state or "team_user_id" not in decoded_state:
            logger.error("Invalid state format")
            raise HTTPException(status_code=400, detail="Invalid state")

        team_id = decoded_state["team_id"]
        team_user_id = decoded_state["team_user_id"]
        app_name = decoded_state["app_name"]
        logger.info(f"Processing OAuth for user_id: {team_user_id}, team_id: {team_id}")
        logger.info("Exchanging code for tokens")

        tokens = google_client.exchange_code_for_token(code)
        user = User.get_user(session, app_name, team_id, team_user_id)
        if user:
            User.update_associated_google_email(
                session,
                user.app_name,
                user.app_team_id,
                user.app_user_id,
                tokens.get("email")
            )
        else:
            User(
                app_user_id=team_user_id,
                app_team_id=team_id,
                associated_google_email=tokens.get("email"),
                app_name=app_name
            ).upsert_user(session)
        
        logger.info("Saving tokens")
        OAuthTokens(
            user_id=team_user_id,
            team_id=team_id,
            integration_type="google",
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_at=tokens["expires_at"],
            app_name=app_name
        ).save(session)
        logger.info("OAuth flow completed successfully")
        return JSONResponse(content={"message": "OAuth flow completed successfully"}, status_code=200)
    except Exception as e:
        logger.error(f"Error in OAuth callback: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error handling callback: {str(e)}")