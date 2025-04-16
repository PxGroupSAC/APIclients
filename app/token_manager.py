import httpx
import base64
import time

# OAuth2 client credentials
CLIENT_ID = "51m0in6ld1osumq6rd7it5dvc5"
CLIENT_SECRET = "vgncvm0o518aic3gt5lg3ifgtnpe9t4a9asjeagido31kmfuhdo"
TOKEN_URL = "https://oauth.pxgroup.io/oauth2/token"
SCOPE = "apiauthdentifier/json.read"

# Cache
_token_cache = {
    "access_token": None,
    "expires_at": 0
}

def get_bearer_token():
    current_time = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > current_time:
        return _token_cache["access_token"]

    # Prepare request
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_header = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "client_credentials",
        "scope": SCOPE
    }

    # Request token
    response = httpx.post(TOKEN_URL, headers=headers, data=data)
    if response.status_code != 200:
        raise Exception("Failed to get access token")

    token_data = response.json()
    access_token = token_data["access_token"]
    expires_in = token_data["expires_in"]

    # Cache it
    _token_cache["access_token"] = access_token
    _token_cache["expires_at"] = current_time + expires_in - 30  # buffer

    print("✅ Bearer token generado:", access_token[:60], "...")

    return access_token

