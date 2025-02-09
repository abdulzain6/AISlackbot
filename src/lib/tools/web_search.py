from duckduckgo_search import DDGS
from typing import List
from langchain.tools import tool, Tool
from .tool_maker import ToolMaker
import requests
import html2text

class WebSearch(ToolMaker):
    def __init__(self):
        self.ddgs = DDGS()
    
    def search_results(self, query: str, max_results: int = 10) -> List[dict]:
        return list(self.ddgs.text(query, max_results=max_results))
    
    def search_images(self, query: str, max_results: int = 10) -> List[str]:
        return [img["image"] for img in self.ddgs.images(query, max_results=max_results)]
    
    def http_get_request(self, url: str) -> str:
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            html_content = response.text
            markdown_content = html2text.html2text(html_content)
            return markdown_content
        except requests.RequestException as e:
            return "Error in get request"
    
    def create_ai_tools(self) -> list[Tool]:
        @tool
        def search_text_tool(query: str, max_results: int = 10) -> List[dict]:
            """Search DuckDuckGo for text results based on the query."""
            return list(self.ddgs.text(query, max_results=max_results))
        
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

# Example usage
# searcher = DuckDuckGoSearch("FastAPI")
# print(searcher.search_results())
# print(searcher.search_images())
# print(searcher.http_get_request("https://www.example.com"))
