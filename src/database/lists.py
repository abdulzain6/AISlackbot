from typing import Optional, List as PyList, Dict, Tuple
from firebase_admin import firestore
from pydantic import BaseModel
import firebase_admin
from langchain.tools import tool


class List(BaseModel):
    user_id: str
    team_id: str
    list_name: str
    list_contents: PyList[str]
    is_private: bool
    metadata: dict = None

class ListWithId(List):
    doc_id: str

class FirebaseListService:
    def __init__(self):
        if not firebase_admin._apps:
            app = firebase_admin.initialize_app()
            
        self.db = firestore.client()
        self.collection = self.db.collection('lists')

    def create_list(self, list_data: List) -> str:
        """
        Create a new list in Firebase.
        Returns the document ID of the created list.
        """
        # Generate a unique document ID with team ID prefix
        doc_id = f"{list_data.team_id}_{self.collection.document().id}"
        doc_ref = self.collection.document(doc_id)
        doc_ref.set(list_data.model_dump())
        return doc_id

    def get_list(self, list_id: str, user_id: str, team_id: str) -> Optional[List]:
        """
        Retrieve a list by ID with proper access control.
        Returns None if list doesn't exist or user doesn't have access.
        """
        if not list_id.startswith(f"{team_id}_"):
            return None
            
        doc_ref = self.collection.document(list_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return None
            
        list_data = List(**doc.to_dict())
        
        if list_data.team_id != team_id:
            return None
            
        if list_data.is_private and list_data.user_id != user_id:
            return None
                
        return list_data

    def delete_list(self, list_id: str, user_id: str, team_id: str) -> bool:
        """
        Delete a list. Only the owner can delete the list.
        Returns True if deletion was successful.
        """
        if not list_id.startswith(f"{team_id}_"):
            return False
            
        doc_ref = self.collection.document(list_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return False
            
        list_data = List(**doc.to_dict())
        
        if list_data.team_id != team_id or list_data.user_id != user_id:
            return False
            
        doc_ref.delete()
        return True

    def get_lists(self, user_id: str, team_id: str) -> PyList[ListWithId]:
        """
        Get all lists accessible to the user within their team:
        - All lists owned by the user (private and public)
        - All public lists from team members
        """
        # Get all user's lists in the team
        user_lists_query = self.collection.where('team_id', '==', team_id)\
                                        .where('user_id', '==', user_id)\
                                        .stream()
        
        # Get all public team lists from other users
        public_team_lists_query = self.collection.where('team_id', '==', team_id)\
                                               .where('is_private', '==', False)\
                                               .where('user_id', '!=', user_id)\
                                               .stream()
        
        lists = []
        
        # Add user's own lists
        for doc in user_lists_query:
            lists.append(ListWithId(**doc.to_dict(), doc_id=doc.id))
            
        # Add public team lists
        for doc in public_team_lists_query:
            lists.append(ListWithId(**doc.to_dict(), doc_id=doc.id))
            
        return lists

    def add_to_list(self, list_id: str, user_id: str, team_id: str, item: str) -> bool:
        """
        Add an item to a list's contents. Only the owner can modify the list.
        Returns True if the operation was successful.
        """
        if not list_id.startswith(f"{team_id}_"):
            return False
            
        doc_ref = self.collection.document(list_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return False
            
        list_data = List(**doc.to_dict())
        
        if list_data.team_id != team_id or list_data.user_id != user_id:
            return False
            
        # Add the item using array_union to prevent duplicates
        doc_ref.update({
            'list_contents': firestore.ArrayUnion([item])
        })
        return True

    def pop_from_list(self, list_id: str, user_id: str, team_id: str, index: int) -> Tuple[bool, Optional[str]]:
        """
        Remove and return an item from a specific index in the list.
        Returns a tuple of (success, item) where item is None if operation failed.
        Only the owner can modify the list.
        """
        if not list_id.startswith(f"{team_id}_"):
            return False, None
            
        doc_ref = self.collection.document(list_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return False, None
            
        list_data = List(**doc.to_dict())
        
        if list_data.team_id != team_id or list_data.user_id != user_id:
            return False, None
            
        try:
            # Get the item to be removed
            item = list_data.list_contents[index]
            
            # Remove the item
            new_contents = list_data.list_contents.copy()
            new_contents.pop(index)
            
            # Update the document
            doc_ref.update({
                'list_contents': new_contents
            })
            
            return True, item
        except IndexError:
            return False, None
        
    def create_ai_tools(self, team_id: str, user_id: str):
        @tool
        def add_to_list(item: str, list_id: str):
            "Used to add an item into a list. Only the owner can modify the list"
            list = self.get_list(list_id=list_id, user_id=user_id, team_id=team_id)
            if not list:
                return "List not found"
            if not self.add_to_list(list_id=list_id, user_id=user_id, team_id=team_id, item=item):
                return "Error adding to list: Only the owner can modify the list"
            
            return f"Added to list successfully.. New contents: {list.list_contents}"

        @tool
        def remove_from_list(index: int, list_id: str):
            "Used to add an item into a list. Only the owner can modify the list...Uses 0 indexing"
            list = self.get_list(list_id=list_id, user_id=user_id, team_id=team_id)
            if not list:
                return "List not found"
            if not self.pop_from_list(list_id=list_id, user_id=user_id, team_id=team_id, index=index):
                return "Error adding to list: Only the owner can modify the list"
            
            return f"Removed to list successfully.. New contents: {list.list_contents}"

        @tool
        def delete_list(list_id: str):
            "Used to delete a list Only the owner can delete the list."
            list = self.delete_list(list_id=list_id, user_id=user_id, team_id=team_id)
            if not list:
                return "Error in deleting list.. Only the owner can delete the list."
            return "List deleted successfully."
        
        @tool
        def get_list_contents(list_id: str):
            "Used to get list contents"
            list = self.get_list(list_id=list_id, user_id=user_id, team_id=team_id)
            if not list:
                return "List not found"
            return f"List Contents:\n {list.list_contents}"

        @tool
        def create_list(list_name: str, list_contents: list[str], is_private: bool, metadata: dict = None):
            "Used to create a list, Non private lists can be seen by other team members as well."
            list_id = self.create_list(
                List(
                    user_id=user_id,
                    team_id=team_id,
                    list_name=list_name,
                    list_contents=list_contents,
                    is_private=is_private,
                    metadata=metadata or {}
                )
            )
            return f"List created with ID, {list_id}"

        @tool
        def get_user_lists():
            "Used to get lists for user includes private (team) and user lists"
            lists = self.get_lists(user_id=user_id, team_id=team_id)
            if not lists:
                return "No lists available currently"
            list_string = "Lists: "
            for list in lists:
                list_string += f"""
    =================
    List Name : {list.list_name}
    Is Team list (Accessible to team) : {'No' if list.is_private else 'Yes'}
    List ID: {list.doc_id}
    =================
"""         
            return list_string
        
        return [add_to_list, remove_from_list, delete_list, get_list_contents, create_list, get_user_lists]
