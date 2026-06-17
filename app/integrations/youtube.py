"""
YouTube Data API v3 integration stub.
Replace stub methods with real API calls once YOUTUBE_API_KEY is set.
"""
from app.config import settings
from app.integrations.base import BasePlatformIntegration, IntegrationNotConfiguredError


class YouTubeIntegration(BasePlatformIntegration):
    platform = "youtube"

    def is_configured(self) -> bool:
        return bool(settings.YOUTUBE_API_KEY)

    def search_creators(self, query: str, min_followers: int = 100_000, max_results: int = 20) -> list[dict]:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("YOUTUBE_API_KEY not set")
        # TODO: GET https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={query}&key={key}
        # Then GET channels?part=statistics,snippet&id={channel_id} to get subscriber count
        # Filter by subscriber_count >= min_followers
        return []

    def get_creator_profile(self, handle: str) -> dict:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("YOUTUBE_API_KEY not set")
        # TODO: resolve channel by handle, fetch snippet + statistics + brandingSettings
        return {}

    def get_recent_posts(self, handle: str, limit: int = 20) -> list[dict]:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("YOUTUBE_API_KEY not set")
        # TODO: GET playlistItems for uploads playlist, then videos?part=statistics for each
        return []

    def get_public_contact_info(self, handle: str) -> dict:
        if not self.is_configured():
            raise IntegrationNotConfiguredError("YOUTUBE_API_KEY not set")
        # TODO: GET channels?part=snippet — check snippet.customUrl, snippet.description for email regex
        return {}


youtube = YouTubeIntegration()
