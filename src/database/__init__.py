from .api_keystore import APIKeyRepository
from .gmail_watch_requests import WatchRequestStorage
from .lists import FirebaseListService
from .oauth_tokens import FirebaseOAuthStorage
from .user_files import FirebaseFileHandler
from .users import FirestoreUserStorage
from .data_store import FirebaseStorageHandler
from enum import Enum

class DatabaseHelpers(Enum):
    API_KEY_REPOSITORY = 'APIKeyRepository'
    WATCH_REQUEST_STORAGE = 'WatchRequestStorage'
    LIST_SERVICE = 'FirebaseListService'
    OAUTH_STORAGE = 'FirebaseOAuthStorage'
    FILE_HANDLER = 'FirebaseFileHandler'
    USER_TASKS = 'FirebaseUserTasks'
    USER_STORAGE = 'FirestoreUserStorage'
    DATA_STORE = 'FirebaseStorageHandler'

DATABASE_HELPER_MAP = {
    DatabaseHelpers.API_KEY_REPOSITORY: APIKeyRepository,
    DatabaseHelpers.WATCH_REQUEST_STORAGE: WatchRequestStorage,
    DatabaseHelpers.LIST_SERVICE: FirebaseListService,
    DatabaseHelpers.OAUTH_STORAGE: FirebaseOAuthStorage,
    DatabaseHelpers.FILE_HANDLER: FirebaseFileHandler,
    DatabaseHelpers.USER_STORAGE: FirestoreUserStorage,
    DatabaseHelpers.DATA_STORE: FirebaseStorageHandler,
}
