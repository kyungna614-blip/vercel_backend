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
user = client.user().get()
print("Type:", type(user))
print("User:", user)
print("APIFY CONNECTED!")
