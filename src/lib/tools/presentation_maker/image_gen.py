import hashlib
import random
from typing import Optional, Dict
from urllib.parse import urlparse
import os
import requests
from PIL import Image
from io import BytesIO

from typing import Optional, Dict, List
from urllib.parse import urlparse
import os
import requests
from PIL import Image
from io import BytesIO

class PexelsImageSearch:
    def __init__(self, api_key: str = None, image_cache_dir: str = ".image_cache"):
        if not api_key:
            api_key = os.getenv("PEXELS_API_KEY")
            
        self.api_key = api_key
        self.image_cache_dir = image_cache_dir
        self.used_images: List[str] = []
        
        # Create image cache directory if it doesn't exist
        if not os.path.exists(self.image_cache_dir):
            os.makedirs(self.image_cache_dir)

    def get_extension_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        root, ext = os.path.splitext(parsed.path)
        return ext

    def hash_url(self, url: str, width: int, height: int) -> str:
        return hashlib.md5(f"{url}_{width}_{height}".encode()).hexdigest()

    def download_and_resize_image(self, image_url: str, target_width: int, target_height: int) -> str:
        hash_value = self.hash_url(image_url, target_width, target_height)
        ext = self.get_extension_from_url(image_url)
        cached_file_path = os.path.join(self.image_cache_dir, f"{hash_value}{ext}")

        # Check if image already exists in cache
        if os.path.exists(cached_file_path):
            print(f"Image fetched from cache: {cached_file_path}")
            return cached_file_path

        print(f"Downloading {image_url}")
        response = requests.get(image_url, timeout=5)
        img_data = BytesIO(response.content)
        with Image.open(img_data) as img:
            img = img.resize((target_width, target_height), Image.LANCZOS)
            img.save(cached_file_path)
            print(f"Image saved at {cached_file_path}")

        return cached_file_path
            

    def search_download_and_resize(self, query: str, target_width: Optional[int], target_height: Optional[int], per_page: int = 15) -> str:
        target_width = target_width if target_width is not None else 200
        target_height = target_height if target_height is not None else 200

        if closest_image := self.search_images(query, target_width, target_height, per_page):
            image_url = closest_image['src']['original']
            return self.download_and_resize_image(image_url, target_width, target_height)
        else:
            print("No suitable image found.")
            return os.path.join(self.image_cache_dir(random.choice(os.listdir(self.image_cache_dir))))
            
    def search_images(self, query: str, target_width: int, target_height: int, per_page: int = 15) -> Optional[Dict]:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page={per_page}"
        headers = {"Authorization": self.api_key}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        if photos := data.get('photos', []):
            for photo in sorted(
                photos,
                key=lambda x: abs(x['width'] - target_width) + abs(x['height'] - target_height),
            ):
                if photo['src']['original'] not in self.used_images:
                    self.used_images.append(photo['src']['original'])
                    if len(self.used_images) > 10:
                        self.used_images.pop(0)
                    return photo
        return None