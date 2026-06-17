import os
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from apify_client import ApifyClient

client = ApifyClient(os.getenv("APIFY_API_KEY"))

print("Running dataovercoffee/youtube-channel-business-email-scraper...")
run = client.actor("dataovercoffee/youtube-channel-business-email-scraper").call(
    run_input={
        "channels": [
            "@MrBeast",
            "https://www.youtube.com/@TheDiaryOfACEO",
        ]
    }
)

dataset_id = getattr(run, "default_dataset_id", None)
print(f"Dataset ID (v3): {dataset_id}")

items = list(client.dataset(dataset_id).iterate_items())
print(f"Got {len(items)} results\n")

for item in items:
    name = item.get("ChannelName", "?")
    email = item.get("Email", "none")
    cid = item.get("ChannelId", "?")
    subs = item.get("SubscriberCount", "?")
    handle = item.get("ChannelHandle", "?")
    print(f"  Channel: {name}")
    print(f"  Handle:  {handle}")
    print(f"  Email:   {email}")
    print(f"  ID:      {cid}")
    print(f"  Subs:    {subs}")
    print(f"  Keys:    {list(item.keys())}")
    print()

print("APIFY TEST COMPLETE")
