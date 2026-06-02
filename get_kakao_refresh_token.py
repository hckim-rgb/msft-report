import json
import os
import sys
import urllib.parse
import urllib.request


REDIRECT_URI = "http://localhost"


def post_form(url, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    rest_api_key = os.getenv("KAKAO_REST_API_KEY")
    if not rest_api_key:
        rest_api_key = input("Kakao REST API key: ").strip()

    auth_url = (
        "https://kauth.kakao.com/oauth/authorize?"
        + urllib.parse.urlencode(
            {
                "client_id": rest_api_key,
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": "talk_message",
            }
        )
    )

    print("\nOpen this URL in your browser, approve, then copy the code from the redirected URL:")
    print(auth_url)
    code = input("\nAuthorization code: ").strip()
    if not code:
        print("No code provided.", file=sys.stderr)
        sys.exit(1)

    payload = {
        "grant_type": "authorization_code",
        "client_id": rest_api_key,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }
    client_secret = os.getenv("KAKAO_CLIENT_SECRET")
    if client_secret:
        payload["client_secret"] = client_secret

    token = post_form("https://kauth.kakao.com/oauth/token", payload)

    print("\nToken response:")
    print(json.dumps(token, ensure_ascii=False, indent=2))
    if "refresh_token" in token:
        print("\nSave this in your .env:")
        print(f"KAKAO_REFRESH_TOKEN={token['refresh_token']}")


if __name__ == "__main__":
    main()
