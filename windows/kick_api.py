"""Kick resmi Public API istemcisi (OAuth 2.1 + PKCE).

Uygulama kaydı: https://kick.com/settings/developer
Redirect URI olarak config.json'daki redirect_uri değerini (varsayılan
http://localhost:8765/callback) Kick geliştirici panelinde eklemelisiniz.
"""
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

AUTH_URL = "https://id.kick.com/oauth/authorize"
TOKEN_URL = "https://id.kick.com/oauth/token"
API = "https://api.kick.com/public/v1"
SCOPES = "user:read channel:read channel:write chat:write moderation:ban events:subscribe"


class KickAuthError(Exception):
    pass


class KickAPI:
    def __init__(self, client_id, client_secret, redirect_uri, token_path):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_path = token_path
        self.tokens = self._load()

    # ---------- token saklama ----------
    def _load(self):
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _save(self, data):
        data["expires_at"] = time.time() + int(data.get("expires_in", 3600)) - 60
        self.tokens = data
        with open(self.token_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def logout(self):
        self.tokens = None
        if os.path.exists(self.token_path):
            os.remove(self.token_path)

    @property
    def logged_in(self):
        return bool(self.tokens and self.tokens.get("access_token"))

    # ---------- OAuth ----------
    def login(self, timeout=180):
        """Tarayıcıda Kick giriş sayfasını açar, yerel callback'i bekler (bloklar)."""
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        result = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result["code"] = q.get("code", [None])[0]
                result["state"] = q.get("state", [None])[0]
                result["error"] = q.get("error", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h2>KickStudio: giriş tamamlandı, bu pencereyi kapatabilirsiniz.</h2>".encode())

            def log_message(self, *a):
                pass

        u = urllib.parse.urlparse(self.redirect_uri)
        server = HTTPServer((u.hostname or "localhost", u.port or 80), Handler)
        server.timeout = timeout
        webbrowser.open(AUTH_URL + "?" + urllib.parse.urlencode(params))
        server.handle_request()
        server.server_close()

        if result.get("error") or not result.get("code"):
            raise KickAuthError(result.get("error") or "Giriş zaman aşımına uğradı")
        if result.get("state") != state:
            raise KickAuthError("State uyuşmadı")

        r = requests.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code_verifier": verifier,
            "code": result["code"],
        }, timeout=20)
        if r.status_code != 200:
            raise KickAuthError(f"Token alınamadı: {r.status_code} {r.text}")
        self._save(r.json())

    def _refresh(self):
        if not self.tokens or not self.tokens.get("refresh_token"):
            raise KickAuthError("Oturum yok, tekrar giriş yapın")
        r = requests.post(TOKEN_URL, data={
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.tokens["refresh_token"],
        }, timeout=20)
        if r.status_code != 200:
            self.logout()
            raise KickAuthError("Oturum süresi doldu, tekrar giriş yapın")
        self._save(r.json())

    # ---------- istek yardımcısı ----------
    def _req(self, method, path, **kw):
        if not self.logged_in:
            raise KickAuthError("Giriş yapılmadı")
        if time.time() > self.tokens.get("expires_at", 0):
            self._refresh()
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {self.tokens['access_token']}",
                       "Accept": "application/json"}
            r = requests.request(method, API + path, headers=headers, timeout=20, **kw)
            if r.status_code == 401 and attempt == 0:
                self._refresh()
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Kick API {r.status_code}: {r.text[:300]}")
            return r.json() if r.content else {}

    # ---------- uç noktalar ----------
    def me(self):
        return self._req("GET", "/users")["data"][0]

    def channel(self, slug=None):
        params = {"slug": slug} if slug else None
        data = self._req("GET", "/channels", params=params)["data"]
        return data[0] if data else None

    def update_channel(self, title=None, category_id=None):
        body = {}
        if title is not None:
            body["stream_title"] = title
        if category_id is not None:
            body["category_id"] = int(category_id)
        return self._req("PATCH", "/channels", json=body)

    def search_categories(self, query):
        return self._req("GET", "/categories", params={"q": query}).get("data", [])

    def send_chat(self, broadcaster_user_id, text):
        return self._req("POST", "/chat", json={
            "broadcaster_user_id": int(broadcaster_user_id),
            "content": text[:500],
            "type": "user",
        })

    def ban(self, broadcaster_user_id, user_id, duration_min=None, reason=""):
        body = {"broadcaster_user_id": int(broadcaster_user_id),
                "user_id": int(user_id), "reason": reason or "KickStudio"}
        if duration_min:
            body["duration"] = int(duration_min)  # dakika = timeout
        return self._req("POST", "/moderation/bans", json=body)

    def unban(self, broadcaster_user_id, user_id):
        return self._req("DELETE", "/moderation/bans", json={
            "broadcaster_user_id": int(broadcaster_user_id), "user_id": int(user_id)})
