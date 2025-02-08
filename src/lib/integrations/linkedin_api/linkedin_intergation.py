import linkedin
from linkedin import linkedin

class LinkedInPoster:
    def __init__(self, api_key, api_secret, user_token, user_secret):
        self.authentication = linkedin.LinkedInDeveloperAuthentication(
            api_key,
            api_secret,
            user_token,
            user_secret,
            'http://localhost:8000',
            linkedin.PERMISSIONS.enums.values()
        )
        self.application = linkedin.LinkedInApplication(self.authentication)

    def post_update(self, message):
        return self.application.submit_share(message)

    def post_with_link(self, message, link_url, link_title, link_description, link_thumbnail_url):
        return self.application.submit_share(
            comment=message,
            title=link_title,
            description=link_description,
            submitted_url=link_url,
            submitted_image_url=link_thumbnail_url
        )

# Usage example:
# poster = LinkedInPoster('your_api_key', 'your_api_secret', 'your_user_token', 'your_user_secret')
# poster.post_update("Hello, LinkedIn!")
# poster.post_with_link("Check out this link!", "https://example.com", "Example Title", "Example Description", "https://example.com/thumbnail.jpg")
