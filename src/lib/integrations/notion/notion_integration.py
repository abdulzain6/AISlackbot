from notion_client import Client
from typing import Dict, Any, List, Optional
import markdown2

class NotionAPI:
    def __init__(self, token: str) -> None:
        self.client = Client(auth=token)

    def _md_to_blocks(self, md_content: str) -> List[Dict[str, Any]]:
        html = markdown2.markdown(md_content)
        return [
            {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": html}}]
                    }
                }
            ]

    def create_page(self, parent_id: str, title: str, content: str) -> Dict[str, Any]:
        return self.client.pages.create(
            parent={"database_id": parent_id},
            properties={
                "title": {"title": [{"text": {"content": title}}]}
            },
            children=self._md_to_blocks(content)
        )
    
    def update_page(self, page_id: str, title: Optional[str] = None, content: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if title:
            data["properties"] = {"title": {"title": [{"text": {"content": title}}]}}
        if content:
            data["children"] = self._md_to_blocks(content)
        return self.client.pages.update(page_id=page_id, **data)
    
    def read_page(self, page_id: str) -> Dict[str, Any]:
        return self.client.pages.retrieve(page_id=page_id)

    def list_pages(self, database_id: str, filter: Optional[Dict[str, Any]] = None, sort: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        query_params: Dict[str, Any] = {"database_id": database_id}
        if filter:
            query_params["filter"] = filter
        if sort:
            query_params["sorts"] = sort
        
        response = self.client.databases.query(**query_params)
        return response["results"]
   
    def create_database(self, title: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        # Use the root Notion workspace as the parent
        parent = {"type": "workspace", "workspace": True}
        
        return self.client.databases.create(
            parent=parent,
            title=[{"type": "text", "text": {"content": title}}],
            properties=properties
        )
            
    def list_databases(self) -> List[Dict[str, Any]]:
        databases = []
        start_cursor = None

        try:
            while True:
                response = self.client.search(
                    filter={"property": "object", "value": "database"},
                    start_cursor=start_cursor
                )
                
                print(f"Response: {response}")  # Debug print
                if not response.get("results"):
                    print("No results found in the response")
                    break

                for result in response["results"]:
                    databases.append({
                        "id": result["id"],
                    "title": result["title"][0]["plain_text"] if result["title"] else "Untitled"
                })
            
                if not response.get("has_more"):
                    break
            
                start_cursor = response.get("next_cursor")

            print(f"Total databases found: {len(databases)}")  # Debug print
            return databases

        except Exception as e:
            print(f"An error occurred: {str(e)}")
            return []

if __name__ == "__main__":
    tok = "ntn_q54267579208mYxdodrtEkMR2j6c5yF8XPeWsK6s53ldYa"
    from notion_client import Client
    import random
    import string

        # Setup
    notion = NotionAPI(tok)

    # Function to generate a random title
    def generate_random_title(length=10):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    # Function to generate random content
    def generate_random_content(length=100):
        return ' '.join(''.join(random.choices(string.ascii_lowercase, k=random.randint(3, 10))) for _ in range(length))

    # Get list of databases
    databases = notion.list_databases()

    if databases:
        # Choose a random database
        random_database = random.choice(databases)
        database_id = random_database['id']

        # Create a random page
        title = generate_random_title()
        content = generate_random_content()
        new_page = notion.create_page(database_id, title, content)

        # Print the link to the new page
        page_id = new_page['id']
        page_link = f"https://www.notion.so/{page_id.replace('-', '')}"
        print(f"Random page created. Link: {page_link}")
    else:
        print("No databases found. Cannot create a page.")
