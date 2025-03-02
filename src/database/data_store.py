from firebase_admin import storage

class FirebaseStorageHandler:
    @staticmethod
    def upload_file(local_file_path: str, storage_file_path: str):
        bucket = storage.bucket()
        blob = bucket.blob(storage_file_path)
        blob.upload_from_filename(local_file_path)
        blob.make_public()
        return blob.public_url
