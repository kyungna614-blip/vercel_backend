"""
Instagram Graph API integration stub.
Requires a Facebook Developer App with instagram_basic permission.
Only accesses public profile data — no private message scraping.
"""
from app.config import settings
from app.integrations.base import BasePlatformIntegration, IntegrationNotConfiguredError


class InstagramIntegration(BasePlatformIntegration):
    platform = "instagram"

    def is_configured(self) -> bool:
        return bool(settings.INSTAGRAM_ACCESS_TOKEN)

    def search_creators(self, query: str, min_followers: int = 100_000, max_results: int = 20) -> list[dict]:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("INSTAGRAM_ACCESS_TOKEN not set")
        # NOTE: Instagram Graph API does not support general creator search.
        # Use third-party social listening APIs (Modash, HypeAuditor, Creator.co)
        # or manual import CSVs for discovery.
        return []

    def get_creator_profile(self, handle: str) -> dict:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("INSTAGRAM_ACCESS_TOKEN not set")
        # TODO: GET graph.facebook.com/v18.0/{username}?fields=biography,followers_count,website
        return {}

    def get_recent_posts(self, handle: str, limit: int = 20) -> list[dict]:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("INSTAGRAM_ACCESS_TOKEN not set")
        # TODO: GET media?fields=id,caption,like_count,comments_count,timestamp,permalink
        return []

    def get_public_contact_info(self, handle: str) -> dict:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("INSTAGRAM_ACCESS_TOKEN not set")
        # Extract from biography field and website field only
        return {}


instagram = InstagramIntegration()
