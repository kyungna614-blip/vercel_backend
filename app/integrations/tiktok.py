"""
TikTok Research API integration stub.
Requires approved Research API access (academic/business).
"""
from app.config import settings
from app.integrations.base import BasePlatformIntegration, IntegrationNotConfiguredError


class TikTokIntegration(BasePlatformIntegration):
    platform = "tiktok"

    def is_configured(self) -> bool:
        return bool(settings.TIKTOK_API_KEY)

    def search_creators(self, query: str, min_followers: int = 100_000, max_results: int = 20) -> list[dict]:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("TIKTOK_API_KEY not set")
        # TODO: POST /v2/research/user/search/ with keyword
        return []

    def get_creator_profile(self, handle: str) -> dict:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("TIKTOK_API_KEY not set")
        # TODO: GET /v2/research/user/info/?username={handle}
        return {}

    def get_recent_posts(self, handle: str, limit: int = 20) -> list[dict]:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("TIKTOK_API_KEY not set")
        # TODO: POST /v2/research/video/query/ filtered by author username
        return []

    def get_public_contact_info(self, handle: str) -> dict:
        # TikTok profiles show website in bio — extract from bio_link field
        return {}


tiktok = TikTokIntegration()
