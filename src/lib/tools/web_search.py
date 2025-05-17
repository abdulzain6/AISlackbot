import ipaddress
from urllib.parse import urlparse
from duckduckgo_search import DDGS
from typing import List
import redis
from sqlalchemy.orm import Session
from langchain.tools import tool, BaseTool
from ...lib.integrations.auth.oauth_handler import OAuthClient
from ...lib.platforms.platform_helper import PlatformHelper
from .tool_maker import ToolMaker, ToolConfig
import requests
import html2text


class WebSearchConfig(ToolConfig):
    proxy: str | None = None

class WebSearch(ToolMaker):
    DESCRIPTION: str = """
Provides utilities to perform web search.
"""

    def __init__(
        self, 
        tool_config: WebSearchConfig,
        platform_helper: PlatformHelper,
        oauth_integrations: dict[str, OAuthClient],
        session: Session,
        redis_client: redis.Redis,
    ):
        self.ddgs = DDGS(
            proxy=tool_config.proxy
        )
    
    def search_results(self, query: str, max_results: int = 10) -> List[dict]:
        return list(self.ddgs.text(query, max_results=max_results))
    
    def search_images(self, query: str, max_results: int = 10) -> List[str]:
        return [img["image"] for img in self.ddgs.images(query, max_results=max_results)]
    
    def http_get_request(self, url: str) -> str:
        try:
            # Parse the URL to extract its components
            parsed_url = urlparse(url)

            # Prevent accessing private or local IP ranges
            if parsed_url.hostname:
                ip = None
                try:
                    ip = ipaddress.ip_address(parsed_url.hostname)
                except ValueError:
                    # Handle non-IP hostnames (e.g., domain names), which may resolve to private IPs.
                    pass
                
                if ip:
                    if ip.is_loopback or ip.is_private:  # Block localhost and private IP ranges
                        return "Error: Accessing private or local network URLs is forbidden."

            # Prevent `file://` protocol
            if url.startswith("file://"):
                return "Error: Accessing local files is forbidden by policy."

            # Handle HTTP/HTTPS URLs
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            html_content = response.text
            markdown_content = html2text.html2text(html_content)
            return markdown_content
        except requests.RequestException as e:
            return f"Error in HTTP GET request: {e}"
        except Exception as e:
            return f"Unexpected error: {e}"
    
   
    def create_ai_tools(self) -> list[BaseTool]:
        @tool
        def search_text_tool(keywords: List[str], max_results_per_query: int = 5) -> List[dict]:
            """Search DuckDuckGo for text results based on a list of keywords."""
            aggregated_results = []
            for keyword in keywords:
                results = list(self.ddgs.text(keyword, max_results=max_results_per_query))
                aggregated_results.extend(results)
            return aggregated_results
        
        @tool
        def search_image_tool(query: str, max_results: int = 10) -> List[str]:
            """Search DuckDuckGo for images based on the query."""
            return [img["image"] for img in self.ddgs.images(query, max_results=max_results)]
        
        @tool
        def http_get_tool(url: str) -> str:
            """Perform an HTTP GET request with a 5-second timeout."""
            try:
                return self.http_get_request(url)[:20000]
            except requests.RequestException as e:
                return "Error opening page"
        
        return [search_text_tool, search_image_tool, http_get_tool]
