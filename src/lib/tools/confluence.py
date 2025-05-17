from atlassian import Confluence

confluence = Confluence(
    url='https://your-domain.atlassian.net/wiki',
    username='your-email@example.com',
    password='your-api-token'
)

space_key = 'YOURSPACEKEY'
pages = confluence.get_all_pages_from_space(space=space_key, start=0, limit=500, status='current')

# Build a dictionary of pages by ID
page_dict = {page['id']: page for page in pages}

# Build parent-to-children map
from collections import defaultdict

tree = defaultdict(list)
for page in pages:
    ancestors = page.get('ancestors')
    parent_id = ancestors[-1]['id'] if ancestors else None
    tree[parent_id].append(page)

# Recursive function to print tree
def print_tree(parent_id=None, indent=0):
    for page in sorted(tree[parent_id], key=lambda x: x['title']):
        print("  " * indent + f"- {page['title']}")
        print_tree(page['id'], indent + 1)

# Print the hierarchy
print_tree()
