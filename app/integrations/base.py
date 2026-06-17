"""
Base integration interface.

All platform integrations return normalized dicts so service code
stays platform-agnostic. Each integration class should:
  - raise IntegrationNotConfiguredError if credentials missing
  - raise IntegrationError on API failures
  - never store private/hidden contact info — only public profile data
"""
from typing import Any, Optional


class IntegrationError(Exception):
    pass


class IntegrationNotConfiguredError(IntegrationError):
    pass


class BasePlatformIntegration:
    platform: str = "base"

    def is_configured(self) -> bool:
        raise NotImplementedError

    def search_creators(
        self, query: str, min_followers: int = 100_000, max_results: int = 20
    ) -> list[dict]:
        """
        Returns list of normalized creator dicts:
        {handle, display_name, platform, follower_count, bio,
         profile_url, avatar_url, niche_tags}
        """
        raise NotImplementedError

    def get_creator_profile(self, handle: str) -> dict:
        raise NotImplementedError

    def get_recent_posts(self, handle: str, limit: int = 20) -> list[dict]:
        """
        Returns list of normalized content dicts:
        {content_url, content_type, caption, likes, comments,
         shares, views, posted_at}
        """
        raise NotImplementedError

    def get_public_contact_info(self, handle: str) -> dict:
        """
        Extracts ONLY publicly listed contact info from the profile
        (bio email, linktree, website — never DM scraping).
        Returns {email, website, linktree_url, management_email}
        """
        raise NotImplementedError
