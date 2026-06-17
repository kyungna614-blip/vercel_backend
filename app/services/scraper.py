"""
Public profile scraper — YouTube, Instagram, TikTok.
Only reads publicly visible page data. No login, no private info.
"""
import json
import re
import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _num(s: str) -> int:
    """Parse '2.4M', '890K', '1,234' → int."""
    if not s:
        return 0
    s = s.strip().replace(",", "").replace(" subscribers", "").replace(" followers", "")
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        return int(float(s))
    except Exception:
        return 0


def scrape_youtube(handle: str) -> dict:
    """
    Scrape a YouTube channel using YouTube Data API v3 for content metadata
    and Apify dataovercoffee/youtube-channel-business-email-scraper for business email.
    """
    from app.config import settings
    import urllib.parse

    handle = handle.strip()
    # If handle is a full URL, extract the handle/channel ID
    # Otherwise strip leading @
    channel_id = None
    query_handle = handle

    if "youtube.com" in handle or "youtu.be" in handle:
        # Extract from URL
        yt_patterns = [
            r"youtube\.com/@([^/?&\s]+)",
            r"youtube\.com/channel/([^/?&\s]+)",
            r"youtube\.com/c/([^/?&\s]+)",
            r"youtube\.com/user/([^/?&\s]+)",
        ]
        for pat in yt_patterns:
            m = re.search(pat, handle)
            if m:
                extracted = m.group(1)
                if handle.index(extracted) == handle.find("channel/") + len("channel/"):
                    channel_id = extracted
                else:
                    query_handle = extracted
                break
    else:
        query_handle = handle.lstrip("@")

    result = {
        "handle": f"@{query_handle}" if not query_handle.startswith("@") else query_handle,
        "platform": "youtube",
        "profile_url": f"https://www.youtube.com/@{query_handle}" if not channel_id else f"https://www.youtube.com/channel/{channel_id}",
        "display_name": query_handle,
        "bio": "",
        "avatar_url": "",
        "follower_count": 0,
        "video_count": 0,
        "total_views": 0,
        "niche": [],
        "email_public": "",
        "website": "",
        "social_links": [],
        "recent_posts": [],
        "engagement_rate": 3.5,
    }

    # ── 1. YouTube Data API ──
    api_key = settings.YOUTUBE_API_KEY
    if not api_key:
        return {"error": "YOUTUBE_API_KEY not set", "handle": query_handle, "platform": "youtube"}

    headers = {"Accept": "application/json"}
    ch_data = None

    try:
        # If we have channel_id, fetch directly
        if channel_id:
            ch_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics,contentDetails&id={channel_id}&key={api_key}"
            r = httpx.get(ch_url, headers=headers, timeout=12)
            if r.status_code == 200 and r.json().get("items"):
                ch_data = r.json()["items"][0]
        
        # Else, try forHandle
        if not ch_data:
            clean_handle = query_handle if query_handle.startswith("@") else f"@{query_handle}"
            ch_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics,contentDetails&forHandle={clean_handle}&key={api_key}"
            r = httpx.get(ch_url, headers=headers, timeout=12)
            if r.status_code == 200 and r.json().get("items"):
                ch_data = r.json()["items"][0]

        # Fallback: search query
        if not ch_data:
            search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={urllib.parse.quote(query_handle)}&key={api_key}&maxResults=1"
            r = httpx.get(search_url, headers=headers, timeout=12)
            if r.status_code == 200 and r.json().get("items"):
                found_id = r.json()["items"][0]["snippet"]["channelId"]
                ch_url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics,contentDetails&id={found_id}&key={api_key}"
                r2 = httpx.get(ch_url, headers=headers, timeout=12)
                if r2.status_code == 200 and r2.json().get("items"):
                    ch_data = r2.json()["items"][0]

        if not ch_data:
            return {"error": "Channel not found in YouTube Data API", "handle": query_handle, "platform": "youtube"}

        channel_id = ch_data["id"]
        snippet = ch_data["snippet"]
        stats = ch_data["statistics"]
        uploads_playlist = ch_data.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

        result["display_name"] = snippet.get("title", query_handle)
        result["bio"] = snippet.get("description", "")
        result["profile_url"] = f"https://www.youtube.com/channel/{channel_id}"
        result["avatar_url"] = snippet.get("thumbnails", {}).get("high", {}).get("url", "") or snippet.get("thumbnails", {}).get("medium", {}).get("url", "")
        result["follower_count"] = int(stats.get("subscriberCount", 0))
        result["video_count"] = int(stats.get("videoCount", 0))
        result["total_views"] = int(stats.get("viewCount", 0))
        result["handle"] = snippet.get("customUrl", f"@{query_handle}")

        # Fetch recent uploads to compute engagement and build recent posts list
        recent_videos = []
        if uploads_playlist:
            pl_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_playlist}&maxResults=5&key={api_key}"
            r_pl = httpx.get(pl_url, headers=headers, timeout=12)
            if r_pl.status_code == 200:
                items = r_pl.json().get("items", [])
                video_ids = [item["snippet"]["resourceId"]["videoId"] for item in items]
                
                if video_ids:
                    v_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={','.join(video_ids)}&key={api_key}"
                    r_v = httpx.get(v_url, headers=headers, timeout=12)
                    if r_v.status_code == 200:
                        v_items = r_v.json().get("items", [])
                        
                        total_likes = 0
                        total_comments = 0
                        
                        for idx, v in enumerate(v_items):
                            v_stats = v.get("statistics", {})
                            likes = int(v_stats.get("likeCount", 0))
                            comments = int(v_stats.get("commentCount", 0))
                            views = int(v_stats.get("viewCount", 0))
                            
                            total_likes += likes
                            total_comments += comments
                            
                            thumbs = v.get("snippet", {}).get("thumbnails", {})
                            thumb_url = thumbs.get("medium", {}).get("url", "") or thumbs.get("default", {}).get("url", "")
                            
                            def format_num(num):
                                if num >= 1_000_000: return f"{num/1_000_000:.1f}M".replace('.0M', 'M')
                                if num >= 1_000: return f"{num/1_000:.1f}K".replace('.0K', 'K')
                                return str(num)
                            
                            recent_videos.append({
                                "title": v.get("snippet", {}).get("title", ""),
                                "thumbnail": thumb_url,
                                "videoId": v["id"],
                                "views": format_num(views),
                                "likes": format_num(likes),
                                "comments": format_num(comments),
                                "hue": 0
                            })
                        
                        if result["follower_count"] > 0 and recent_videos:
                            avg_eng = (total_likes + total_comments) / len(recent_videos)
                            result["engagement_rate"] = float(min(25.0, round((avg_eng / result["follower_count"]) * 100, 2)))
                        else:
                            result["engagement_rate"] = 3.5

        result["recent_posts"] = recent_videos

    except Exception as e:
        print(f"YouTube Data API error: {e}")
        # Proceed to scrape via Apify even if YouTube Data API fails partially

    # ── 2. Apify Scraper (dataovercoffee~youtube-channel-business-email-scraper) ──
    apify_key = settings.APIFY_API_KEY
    if apify_key and channel_id:
        try:
            apify_url = f"https://api.apify.com/v2/actors/dataovercoffee~youtube-channel-business-email-scraper/run-sync-get-dataset-items?token={apify_key}&timeout=60"
            payload = {
                "channels": [
                    f"https://www.youtube.com/channel/{channel_id}"
                ]
            }
            # Execute synchronously
            print(f"Calling Apify business email scraper for channel {channel_id}...")
            r_apify = httpx.post(apify_url, json=payload, headers={"Content-Type": "application/json"}, timeout=75)
            if r_apify.status_code == 200 or r_apify.status_code == 201:
                items = r_apify.json()
                if isinstance(items, list) and len(items) > 0:
                    apify_result = items[0]
                    # The actor returns business email
                    email = apify_result.get("email") or apify_result.get("businessEmail")
                    if email and "@" in email:
                        result["email_public"] = email.strip()
                        print(f"Apify email found: {result['email_public']}")
        except Exception as e:
            print(f"Apify email scraping error: {e}")

    # Fallback email extraction from bio
    if not result["email_public"] and result["bio"]:
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
        if emails:
            result["email_public"] = emails[0]

    # Guess niche from bio keywords
    bio_lower = (result["bio"] or "").lower()
    niche_map = {
        "Fitness & Gym": ["fitness", "workout", "gym", "health", "exercise"],
        "Cooking & Food": ["cook", "recipe", "food", "kitchen", "chef"],
        "Tech & Gadgets": ["tech", "technology", "software", "coding", "developer", "programming", "ai"],
        "Finance & Investing": ["finance", "invest", "money", "wealth", "stock", "crypto"],
        "Gaming": ["gaming", "gamer", "twitch", "esport", "playthrough"],
        "Beauty & Style": ["beauty", "makeup", "skincare", "cosmetic", "fashion"],
        "Travel & Nomad": ["travel", "explore", "adventure", "nomad", "vlog"],
        "Education": ["learn", "teach", "tutorial", "course", "education"],
        "Lifestyle": ["lifestyle", "vlog", "daily", "routine"],
        "Business & Marketing": ["entrepreneur", "business", "startup", "founder", "marketing"],
    }
    for tag, keywords in niche_map.items():
        if any(k in bio_lower for k in keywords):
            result["niche"].append(tag)

    if not result["niche"]:
        result["niche"].append("Lifestyle & Creativity")

    return result


def _clean_url(url: str) -> str:
    """Decode JSON/unicode escapes in URLs (e.g. \\u002F → /)."""
    if not url:
        return url
    try:
        import json as _json
        return _json.loads(f'"{url}"')
    except Exception:
        return url.replace("\\u002F", "/").replace("\\u0026", "&").replace("\\/", "/")


def _apify_run(actor_id: str, run_input: dict, api_key: str) -> list:
    """
    Run an Apify actor synchronously via direct HTTP API.
    No SDK needed — avoids import errors on Vercel.
    """
    actor_url_id = actor_id.replace("/", "~")
    api_url = (
        f"https://api.apify.com/v2/acts/{actor_url_id}"
        f"/run-sync-get-dataset-items?token={api_key}&timeout=90"
    )
    r = httpx.post(
        api_url,
        json=run_input,
        headers={"Content-Type": "application/json"},
        timeout=120,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Apify HTTP {r.status_code}: {r.text[:300]}")
    return r.json() if isinstance(r.json(), list) else []


def scrape_instagram(handle: str) -> dict:
    """Instagram scrape — uses Apify when key is configured, falls back to direct."""
    from app.config import settings
    handle = handle.lstrip("@").strip()
    url = f"https://www.instagram.com/{handle}/"
    result = {
        "handle": handle, "platform": "instagram", "profile_url": url,
        "display_name": handle, "bio": "", "avatar_url": "",
        "follower_count": 0, "niche": [], "email_public": "",
        "website": "", "social_links": [],
    }

    if settings.APIFY_API_KEY:
        try:
            items = _apify_run(
                "apify/instagram-profile-scraper",
                {"usernames": [handle]},
                settings.APIFY_API_KEY,
            )
            if items:
                d = items[0]
                result["display_name"]  = d.get("fullName") or d.get("username") or handle
                result["bio"]           = d.get("biography") or ""
                result["follower_count"]= d.get("followersCount") or d.get("followedBy") or 0
                result["avatar_url"]    = d.get("profilePicUrlHD") or d.get("profilePicUrl") or ""
                result["website"]       = d.get("externalUrl") or d.get("websiteUrl") or ""
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
                if emails:
                    result["email_public"] = emails[0]
            return result
        except Exception as e:
            result["error"] = f"Apify: {e}"

    # Direct fallback (limited — Instagram blocks most requests)
    try:
        r = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
        html = r.text
        for pat, key in [
            (r'"edge_followed_by":\{"count":(\d+)\}', "follower_count"),
            (r'"biography":"([^"]*)"', "bio"),
            (r'"full_name":"([^"]*)"', "display_name"),
            (r'"profile_pic_url":"([^"]*)"', "avatar_url"),
            (r'"external_url":"([^"]*)"', "website"),
        ]:
            m = re.search(pat, html)
            if m:
                val = m.group(1).replace("\\/", "/")
                if key == "follower_count":
                    result[key] = int(val)
                else:
                    result[key] = val
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
        if emails:
            result["email_public"] = emails[0]
    except Exception as e:
        result["error"] = str(e)
    return result


def scrape_tiktok(handle: str) -> dict:
    """TikTok scrape — uses Apify when key is configured, falls back to direct."""
    from app.config import settings
    handle = handle.lstrip("@").strip()
    url = f"https://www.tiktok.com/@{handle}"
    result = {
        "handle": handle, "platform": "tiktok", "profile_url": url,
        "display_name": handle, "bio": "", "avatar_url": "",
        "follower_count": 0, "niche": [], "email_public": "",
        "website": "", "social_links": [],
    }

    if settings.APIFY_API_KEY:
        try:
            items = _apify_run(
                "clockworks/tiktok-profile-scraper",
                {"profiles": [f"https://www.tiktok.com/@{handle}"], "resultsPerPage": 1},
                settings.APIFY_API_KEY,
            )
            if items:
                d = items[0]
                result["display_name"]  = d.get("nickname") or d.get("authorMeta", {}).get("name") or handle
                result["bio"]           = d.get("signature") or d.get("authorMeta", {}).get("signature") or ""
                result["follower_count"]= d.get("followerCount") or d.get("authorMeta", {}).get("fans") or 0
                raw_av = d.get("avatarLarger") or d.get("avatarMedium") or d.get("authorMeta", {}).get("avatar") or ""
                result["avatar_url"]    = _clean_url(raw_av)
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
                if emails:
                    result["email_public"] = emails[0]
            return result
        except Exception as e:
            result["error"] = f"Apify: {e}"

    # Direct fallback
    try:
        r = httpx.get(url, headers=HEADERS, timeout=12, follow_redirects=True)
        html = r.text
        for pat, key in [
            (r'"followerCount":(\d+)', "follower_count"),
            (r'"desc":"([^"]*)"', "bio"),
            (r'"nickname":"([^"]*)"', "display_name"),
            (r'"avatarLarger":"([^"]*)"', "avatar_url"),
        ]:
            m = re.search(pat, html)
            if m:
                val = m.group(1).replace("\\/", "/")
                if key == "follower_count":
                    result[key] = int(val)
                elif key == "avatar_url":
                    result[key] = _clean_url(val)
                else:
                    result[key] = val
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", result["bio"])
        if emails:
            result["email_public"] = emails[0]
    except Exception as e:
        result["error"] = str(e)
    return result


def scrape_profile(platform: str, handle: str) -> dict:
    """Dispatch to correct scraper."""
    if platform == "youtube":
        return scrape_youtube(handle)
    elif platform == "instagram":
        return scrape_instagram(handle)
    elif platform == "tiktok":
        return scrape_tiktok(handle)
    else:
        return {"error": f"No scraper for platform: {platform}", "handle": handle, "platform": platform}
