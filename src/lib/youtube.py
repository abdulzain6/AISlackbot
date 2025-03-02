import os
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse
from langchain.document_loaders.base import BaseLoader
from youtube_transcript_api import YouTubeTranscriptApi
from langchain.schema import Document

ALLOWED_SCHEMAS = {"http", "https"}
ALLOWED_NETLOCK = {
    "youtu.be",
    "m.youtube.com",
    "youtube.com",
    "www.youtube.com",
    "www.youtube-nocookie.com",
    "vid.plus",
}

class YoutubeLoader(BaseLoader):
    def __init__(self, video_url: str) -> None:
        self.video_url = video_url

    def _parse_video_id(self, url: str) -> Optional[str]:
        """Parse a youtube url and return the video id if valid, otherwise None."""
        parsed_url = urlparse(url)

        if parsed_url.scheme not in ALLOWED_SCHEMAS:
            return None

        if parsed_url.netloc not in ALLOWED_NETLOCK:
            return None

        path = parsed_url.path

        if path.endswith("/watch"):
            query = parsed_url.query
            parsed_query = parse_qs(query)
            if "v" in parsed_query:
                ids = parsed_query["v"]
                video_id = ids if isinstance(ids, str) else ids[0]
            else:
                return None
        else:
            path = parsed_url.path.lstrip("/")
            video_id = path.split("/")[-1]

        if len(video_id) != 11:  # Video IDs are 11 characters long
            return None

        return video_id
    
    def load(self):
        proxy: str = os.getenv("PROXY")
        print(f"Using proxy: {proxy}")
        
        for _ in range(5):
            try:
                video_id: str = self._parse_video_id(self.video_url)
                if not video_id:
                    raise ValueError("Video ID extraction failed")
                
                try:
                    # Attempt to fetch the transcript in the requested language
                    transcript = YouTubeTranscriptApi.get_transcript(
                        video_id, languages=("eng",), proxies={"http": proxy, "https": proxy}
                    )
                except Exception:
                    # Fetch the available transcripts when the requested language is not found
                    available_transcripts = YouTubeTranscriptApi.list_transcripts(video_id, proxies={"http": proxy, "https": proxy})
                    fallback_transcript = available_transcripts.find_transcript(
                        available_transcripts._manually_created_transcripts or 
                        available_transcripts._generated_transcripts
                    )
                    fallback_language = fallback_transcript.language_code
                    
                    # Retry fetching transcript with the fallback language
                    transcript = YouTubeTranscriptApi.get_transcript(
                        video_id, languages=(fallback_language,), proxies={"http": proxy, "https": proxy}
                    )
                
                # Combine the transcript text
                transcript_text = " ".join([entry['text'] for entry in transcript])
                return [Document(page_content=transcript_text)]
            
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(1)
        
        raise Exception("Failed to get transcript")
    