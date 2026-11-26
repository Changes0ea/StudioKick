"""Kick canlı sohbetini okur (Kick web sitesinin kullandığı Pusher websocket'i).

Not: Bu resmi olmayan bir yoldur; Kick anahtarı değiştirirse config.json'daki
pusher_key / pusher_cluster değerlerini güncelleyin (uygulama bilinen
yedek anahtarları da otomatik dener).
"""
import datetime
import json
import os
import threading
import time

import requests
import websocket

DEFAULT_KEY = "32cbd69e4b950bf97679"
DEFAULT_CLUSTER = "us2"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
FALLBACK_KEYS = ["32cbd69e4b950bf97679", "eb1d5f283081a78b932c"]

LOG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "KickStudio", "chat.log")

# Pusher hata kodları -> Türkçe açıklama
PUSHER_ERRORS = {
    4001: "Pusher anahtarı geçersiz (Kick anahtarı değiştirmiş olabilir)",
    4003: "Pusher uygulaması devre dışı",
    4004: "Bağlantı limiti aşıldı",
    4005: "Geçersiz adres",
    4006: "Geçersiz protokol sürümü",
    4007: "Desteklenmeyen protokol sürümü",
    4008: "Kimlik doğrulama hatası",
    4009: "Bağlantı yetkisiz",
    4100: "Sunucu dolu, biraz sonra tekrar denenecek",
    4200: "Sunucu yeniden bağlanmayı istedi",
    4201: "Ping cevabı gecikti (ağ yavaş veya kesik)",
    4202: "Bağlantı uzun süre boşta kaldı",
}


def _log(line):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {line}\n")
    except Exception:
        pass


def find_chatroom_id(slug):
    """Kanal slug'ından chatroom id bulur. Cloudflare engellerse None döner."""
    try:
        r = requests.get(f"https://kick.com/api/v2/channels/{slug}", timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
            "Accept": "application/json"})
        if r.status_code == 200:
            return r.json()["chatroom"]["id"]
        _log(f"chatroom id alınamadı: HTTP {r.status_code}")
    except Exception as e:
        _log(f"chatroom id alınamadı: {e}")
    return None


class KickChat:
    def __init__(self, chatroom_id, on_message, on_status=None,
                 key=DEFAULT_KEY, cluster=DEFAULT_CLUSTER, on_state=None):
        self.on_state = on_state or (lambda s: None)   # connecting / connected / retrying / stopped
        self.chatroom_id = str(chatroom_id).strip()
        self.on_message = on_message
        self._status_cb = on_status or (lambda s: None)
        self.cluster = cluster or DEFAULT_CLUSTER
        # kullanıcının anahtarı önce, sonra yedekler
        self.keys = [key] + [k for k in FALLBACK_KEYS if k != key]
        self.key_index = 0
        self._stop = threading.Event()
        self._ws = None
        self._backoff = 3
        self._fatal = None          # yeniden denemenin anlamsız olduğu hata
        self._subscribed = False

    def on_status(self, text):
        _log(text)
        self._status_cb(text)

    @property
    def url(self):
        return (f"wss://ws-{self.cluster}.pusher.com/app/{self.keys[self.key_index]}"
                "?protocol=7&client=js&version=8.4.0&flash=false")

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()
        self.on_state("stopped")
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def _run(self):
        _log(f"--- sohbet başlatılıyor, chatroom={self.chatroom_id}")
        while not self._stop.is_set():
            self._fatal = None
            self._subscribed = False
            self.on_state("connecting")
            self.on_status("Sohbet sunucusuna bağlanılıyor...")
            self._ws = websocket.WebSocketApp(
                self.url,
                on_message=self._safe_handle,
                on_open=lambda ws: self.on_status("Sunucuya ulaşıldı, sohbet odasına katılınıyor..."),
                on_close=self._on_close,
                on_error=lambda ws, e: self.on_status(f"Sohbet ağ hatası: {type(e).__name__}: {e}"),
                header={"User-Agent": BROWSER_UA},
            )
            # ping_interval > ping_timeout olmalı; yavaş ağlarda kopmasın diye geniş tutuldu
            # Tarayıcı gibi görün: Kick yalnızca kick.com kaynaklı bağlantılara izin veriyor olabilir
            self._ws.run_forever(ping_interval=30, ping_timeout=20, origin="https://kick.com")
            if self._stop.is_set():
                break
            self.on_state("retrying")
            if self._fatal:
                if self._fatal == 4001 and self.key_index + 1 < len(self.keys):
                    self.key_index += 1
                    self.on_status("Yedek Pusher anahtarı deneniyor...")
                    continue
                self.on_status("Sohbet durduruldu: " + PUSHER_ERRORS.get(self._fatal, str(self._fatal))
                               + " — Ayarlar'ı kontrol edip uygulamayı yeniden başlatın.")
                self.on_state("stopped")
                return
            self.on_status(f"Sohbet bağlantısı koptu, {self._backoff} sn sonra tekrar denenecek")
            self._stop.wait(self._backoff)
            self._backoff = min(self._backoff * 2, 60)

    def _on_close(self, ws, code=None, reason=None):
        self.on_status(f"Sohbet bağlantısı kapandı (kod={code}, sebep={reason or '-'})")

    def _safe_handle(self, ws, raw):
        try:
            self._handle(ws, raw)
        except Exception as e:  # tek bir bozuk mesaj bağlantıyı düşürmesin
            _log(f"mesaj işlenemedi: {e}  ham={raw[:300]}")

    def _handle(self, ws, raw):
        msg = json.loads(raw)
        ev = msg.get("event", "")
        data = msg.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                pass

        if ev == "pusher:connection_established":
            for ch in (f"chatrooms.{self.chatroom_id}.v2", f"chatrooms.{self.chatroom_id}"):
                ws.send(json.dumps({"event": "pusher:subscribe",
                                    "data": {"auth": "", "channel": ch}}))
        elif ev == "pusher_internal:subscription_succeeded":
            if not self._subscribed:
                self._subscribed = True
                self._backoff = 3
                self.on_state("connected")
                self.on_status(f"Sohbete bağlanıldı ✓ (oda {self.chatroom_id})")
        elif ev == "pusher:subscription_error":
            self.on_status(f"Sohbet odasına katılınamadı: {data}")
        elif ev == "pusher:error":
            code = (data or {}).get("code") if isinstance(data, dict) else None
            text = PUSHER_ERRORS.get(code, (data or {}).get("message") if isinstance(data, dict) else data)
            self.on_status(f"Sohbet sunucusu hatası {code}: {text}")
            if code and 4000 <= code < 4100:
                self._fatal = code
                ws.close()
            elif code and 4200 <= code < 4300:
                self._backoff = 1
        elif ev == "pusher:ping":
            ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
        elif ev == "App\\Events\\ChatMessageEvent":
            sender = data.get("sender", {})
            identity = sender.get("identity") or {}
            self.on_message({
                "id": data.get("id"),
                "user_id": sender.get("id"),
                "username": sender.get("username", "?"),
                "color": identity.get("color") or "#53fc18",
                "badges": [b.get("type") for b in identity.get("badges", [])],
                "content": data.get("content", ""),
            })
        elif ev.startswith("App\\Events\\"):
            self.on_status("Olay: " + ev.split("\\")[-1])
