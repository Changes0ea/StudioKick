"""KickStudio — Kick yayıncı paneli + iPhone sanal webcam (Windows)."""
import html
import json
import os
import sys
import threading
import time

import cv2
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSpinBox, QStatusBar, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from camera_receiver import DEFAULT_PORT, CameraReceiver, Discovery
from kick_api import KickAPI
from kick_chat import DEFAULT_CLUSTER, DEFAULT_KEY, LOG_PATH, KickChat, find_chatroom_id

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "KickStudio")
os.makedirs(APP_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
TOKEN_PATH = os.path.join(APP_DIR, "tokens.json")

DEFAULT_CONFIG = {
    "client_id": "",
    "client_secret": "",
    "redirect_uri": "http://localhost:8765/callback",
    "chatroom_id": "",
    "pusher_key": DEFAULT_KEY,
    "pusher_cluster": DEFAULT_CLUSTER,
    "camera_host": "",
    "camera_port": DEFAULT_PORT,
    "camera_fps": 30,
}

# ChangesCraft tasarım dili (paylaşılan palet)
PALETTE = {
    "night": "#050B0A", "forest": "#06503F", "navy": "#14284A", "line": "#0E5A4A",
    "blue": "#68ACFF", "sky": "#70C0FF", "ice": "#8AF2FF", "water": "#7CDEFF", "turq": "#2FE0C0",
    "text": "#D3E6FF", "lav": "#B4BFEE",
    "sub": "#B48CFF", "gold": "#FFCF3F", "kick": "#53FC18",
}
P = PALETTE
STYLE = f"""
QMainWindow, QWidget {{ background:{P['night']}; color:{P['text']};
  font-family:'Montserrat','Segoe UI'; font-size:13px; }}
QMainWindow {{ background: qlineargradient(x1:0,y1:1,x2:1,y2:0, stop:0 {P['forest']}, stop:0.45 {P['night']}, stop:1 {P['night']}); }}
QTabWidget > QWidget, QTabWidget QWidget#page {{ background:transparent; }}
QGroupBox {{ background: rgba(20,40,74,0.35); border:1px solid {P['navy']};
  border-left:3px solid {P['turq']}; border-radius:4px; margin-top:16px; padding:12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left:10px; padding:0 4px; color:{P['ice']};
  font-weight:600; letter-spacing:2px; }}
QLabel {{ background:transparent; }}
QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {P['turq']}, stop:1 {P['blue']});
  color:{P['night']}; border:none; border-radius:4px; padding:8px 16px; font-weight:700; letter-spacing:1px; }}
QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {P['ice']}, stop:1 {P['sky']}); }}
QPushButton:disabled {{ background:{P['navy']}; color:#5a6b85; }}
QPushButton#secondary {{ background:rgba(20,40,74,0.6); color:{P['text']}; border:1px solid {P['navy']}; }}
QPushButton#secondary:hover {{ border-color:{P['turq']}; color:{P['ice']}; }}
QLineEdit, QComboBox, QSpinBox, QListWidget, QTextBrowser {{
  background: rgba(5,11,10,0.75); border:1px solid {P['navy']}; border-radius:4px; padding:6px;
  selection-background-color:{P['line']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color:{P['turq']}; }}
QListWidget::item {{ padding:4px 2px; border-bottom:1px solid rgba(20,40,74,0.5); }}
QCheckBox {{ background:transparent; }}
QCheckBox::indicator:checked {{ background:{P['turq']}; border:1px solid {P['turq']}; }}
QCheckBox::indicator:unchecked {{ background:{P['night']}; border:1px solid {P['navy']}; }}
QTabWidget::pane {{ border:none; background:transparent; }}
QTabBar::tab {{ background:transparent; color:{P['lav']}; padding:10px 20px; margin-right:4px;
  border-bottom:2px solid transparent; letter-spacing:2px; font-weight:600; }}
QTabBar::tab:selected {{ color:{P['ice']}; border-bottom:2px solid {P['turq']}; }}
QTabBar::tab:hover {{ color:{P['ice']}; }}
QStatusBar {{ background:rgba(5,11,10,0.9); color:{P['lav']}; border-top:1px solid {P['navy']}; }}
QMenu {{ background:{P['night']}; border:1px solid {P['navy']}; }}
QMenu::item:selected {{ background:{P['line']}; }}
QScrollBar:vertical {{ background:transparent; width:8px; }}
QScrollBar::handle:vertical {{ background:{P['navy']}; border-radius:4px; min-height:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
"""


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


class Bus(QObject):
    """Arka plan thread'lerinden arayüze güvenli sinyal köprüsü."""
    status = Signal(str)
    chat = Signal(dict)
    frame = Signal(object)
    channel = Signal(dict)
    error = Signal(str)
    logged_in = Signal()
    categories = Signal(list)
    camera_found = Signal(str, str, int)
    chat_sys = Signal(str)
    chat_state = Signal(str)
    cam_state = Signal(str)


def run_bg(fn, bus, on_ok=None):
    def worker():
        try:
            res = fn()
            if on_ok:
                on_ok(res)
        except Exception as e:
            bus.error.emit(str(e))
    threading.Thread(target=worker, daemon=True).start()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChangesCraft Studio — Kick Yayıncı Paneli")
        self.resize(1180, 760)
        self.cfg = load_config()
        self.bus = Bus()
        self.api = None
        self.channel_data = {}
        self.chat_client = None
        self.receiver = None
        self.discovery = None
        self._last_frame = None
        self.me = {}
        self._seen_ids = set()

        tabs = QTabWidget()
        tabs.addTab(self._build_dashboard(), "PANEL")
        tabs.addTab(self._build_camera(), "IPHONE KAMERA")
        tabs.addTab(self._build_settings(), "AYARLAR")
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(14, 10, 14, 4)
        cl.addWidget(self._build_header())
        cl.addWidget(tabs)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.ind_chat = QLabel()
        self.ind_cam = QLabel()
        for lbl in (self.ind_chat, self.ind_cam):
            lbl.setStyleSheet("padding:0 10px;")
            self.statusBar().addPermanentWidget(lbl)
        self._set_ind(self.ind_chat, "Sohbet", "stopped")
        self._set_ind(self.ind_cam, "Kamera", "stopped")

        b = self.bus
        b.status.connect(lambda s: self.statusBar().showMessage(s, 8000))
        b.error.connect(lambda s: QMessageBox.warning(self, "Hata", s))
        b.chat.connect(self._add_chat)
        b.frame.connect(self._store_frame)
        b.channel.connect(self._show_channel)
        b.logged_in.connect(self._after_login)
        b.categories.connect(self._show_categories)
        b.camera_found.connect(self._camera_found)
        b.chat_sys.connect(self._add_sys)
        b.chat_state.connect(lambda st: self._set_ind(self.ind_chat, "Sohbet", st))
        b.cam_state.connect(lambda st: self._set_ind(self.ind_cam, "Kamera", st))

        self.poll = QTimer(self, interval=30_000, timeout=self.refresh_channel)
        self.preview_timer = QTimer(self, interval=40, timeout=self._paint_preview)
        self.preview_timer.start()

        self._init_api()
        self._start_discovery()

    def _build_header(self):
        bar = QWidget(objectName="header")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setStyleSheet(f"QWidget#header {{ background:transparent; border-bottom:1px solid {P['navy']}; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(4, 4, 4, 10)
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        logo_path = os.path.join(base, "assets", "logo.png")
        if os.path.exists(logo_path):
            logo = QLabel()
            logo.setPixmap(QPixmap(logo_path).scaledToHeight(40, Qt.SmoothTransformation))
            h.addWidget(logo)
        mark = QLabel(f"<span style='color:{P['ice']}'>CHANGES</span>"
                      f"<span style='color:{P['blue']}'>CRAFT</span>")
        f = mark.font()
        f.setPointSize(20)
        f.setWeight(QFont.Light)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 6)
        mark.setFont(f)
        sub = QLabel(f"<span style='color:{P['lav']}; letter-spacing:3px'>STUDIO  ·  KICK</span>")
        h.addWidget(mark)
        h.addSpacing(12)
        h.addWidget(sub)
        h.addStretch()
        self.lbl_live_badge = QLabel("")
        h.addWidget(self.lbl_live_badge)
        return bar

    # ===================== PANEL =====================
    def _build_dashboard(self):
        w = QWidget()
        root = QHBoxLayout(w)

        left = QVBoxLayout()
        acc = QGroupBox("Hesap")
        al = QVBoxLayout(acc)
        self.lbl_user = QLabel("Giriş yapılmadı")
        self.btn_login = QPushButton("Kick ile Giriş Yap", clicked=self.login)
        self.btn_logout = QPushButton("Çıkış", objectName="secondary", clicked=self.logout)
        al.addWidget(self.lbl_user)
        row = QHBoxLayout()
        row.addWidget(self.btn_login)
        row.addWidget(self.btn_logout)
        al.addLayout(row)
        left.addWidget(acc)

        live = QGroupBox("Yayın Durumu")
        ll = QFormLayout(live)
        self.lbl_live = QLabel("—")
        self.lbl_viewers = QLabel("—")
        self.lbl_started = QLabel("—")
        self.lbl_cat = QLabel("—")
        self.lbl_title = QLabel("—")
        self.lbl_title.setWordWrap(True)
        ll.addRow("Durum:", self.lbl_live)
        ll.addRow("Başlık:", self.lbl_title)
        ll.addRow("İzleyici:", self.lbl_viewers)
        ll.addRow("Başlangıç:", self.lbl_started)
        ll.addRow("Kategori:", self.lbl_cat)
        ll.addRow(QPushButton("Yenile", objectName="secondary", clicked=self.refresh_channel))
        left.addWidget(live)

        info = QGroupBox("Yayın Bilgisi Düzenle")
        il = QVBoxLayout(info)
        self.ed_title = QLineEdit(placeholderText="Yayın başlığı")
        il.addWidget(QLabel("Başlık"))
        il.addWidget(self.ed_title)
        il.addWidget(QLabel("Kategori ara"))
        crow = QHBoxLayout()
        self.ed_cat = QLineEdit(placeholderText="örn. Just Chatting")
        self.ed_cat.returnPressed.connect(self.search_categories)
        crow.addWidget(self.ed_cat)
        crow.addWidget(QPushButton("Ara", objectName="secondary", clicked=self.search_categories))
        il.addLayout(crow)
        self.cmb_cat = QComboBox()
        il.addWidget(self.cmb_cat)
        il.addWidget(QPushButton("Güncelle", clicked=self.update_channel))
        left.addWidget(info)
        left.addStretch()

        right = QVBoxLayout()
        chat = QGroupBox("Canlı Sohbet  (kullanıcıya sağ tık: timeout / ban)")
        cl = QVBoxLayout(chat)
        self.chat_list = QListWidget()
        self.chat_list.setWordWrap(True)
        self.chat_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._chat_menu)
        cl.addWidget(self.chat_list)
        srow = QHBoxLayout()
        self.ed_msg = QLineEdit(placeholderText="Mesaj yaz ve Enter'a bas...")
        self.ed_msg.returnPressed.connect(self.send_chat)
        srow.addWidget(self.ed_msg)
        srow.addWidget(QPushButton("Gönder", clicked=self.send_chat))
        cl.addLayout(srow)
        right.addWidget(chat)

        root.addLayout(left, 4)
        root.addLayout(right, 6)
        return w

    # ===================== KAMERA =====================
    def _build_camera(self):
        w = QWidget()
        root = QHBoxLayout(w)
        side = QVBoxLayout()

        g = QGroupBox("iPhone Bağlantısı")
        f = QFormLayout(g)
        self.cmb_dev = QComboBox()
        self.cmb_dev.addItem("— Ağda bulunan iPhone'lar —", None)
        self.cmb_dev.currentIndexChanged.connect(self._device_selected)
        self.ed_host = QLineEdit(self.cfg["camera_host"], placeholderText="iPhone IP (örn. 192.168.1.34)")
        self.sp_port = QSpinBox(maximum=65535, value=int(self.cfg["camera_port"]))
        self.sp_fps = QSpinBox(minimum=5, maximum=60, value=int(self.cfg["camera_fps"]))
        self.chk_vcam = QCheckBox("Sanal webcam olarak yayınla (OBS Virtual Camera)", checked=True)
        f.addRow("Bulunanlar:", self.cmb_dev)
        f.addRow("IP:", self.ed_host)
        f.addRow("Port:", self.sp_port)
        f.addRow("FPS:", self.sp_fps)
        f.addRow(self.chk_vcam)
        self.btn_cam = QPushButton("Bağlan", clicked=self.toggle_camera)
        f.addRow(self.btn_cam)
        side.addWidget(g)

        help_ = QLabel(
            "<b>Nasıl kullanılır?</b><br>"
            "1. iPhone'da <b>KickCam</b> uygulamasını aç, Yayını Başlat'a bas.<br>"
            "2. Telefon ve bilgisayar aynı Wi‑Fi'da olmalı.<br>"
            "3. Listeden iPhone'u seç ya da ekranda yazan IP'yi gir, Bağlan.<br>"
            "4. OBS / Discord / Zoom'da kamera olarak <b>OBS Virtual Camera</b> seç.<br><br>"
            "<i>Sanal kamera için OBS Studio (28+) kurulu olmalıdır.</i>")
        help_.setWordWrap(True)
        side.addWidget(help_)
        self.lbl_fps = QLabel("FPS: —")
        side.addWidget(self.lbl_fps)
        side.addStretch()

        self.preview = QLabel("Önizleme", alignment=Qt.AlignCenter)
        self.preview.setMinimumSize(640, 360)
        self.preview.setStyleSheet(f"background:{P['night']}; color:{P['lav']}; border:3px solid {P['turq']}; border-radius:4px;")
        root.addLayout(side, 3)
        root.addWidget(self.preview, 7)
        return w

    # ===================== AYARLAR =====================
    def _build_settings(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Kick Geliştirici Uygulaması  (kick.com/settings/developer)")
        f = QFormLayout(g)
        self.ed_cid = QLineEdit(self.cfg["client_id"])
        self.ed_secret = QLineEdit(self.cfg["client_secret"], echoMode=QLineEdit.Password)
        self.ed_redirect = QLineEdit(self.cfg["redirect_uri"])
        f.addRow("Client ID:", self.ed_cid)
        f.addRow("Client Secret:", self.ed_secret)
        f.addRow("Redirect URI:", self.ed_redirect)
        lay.addWidget(g)

        g2 = QGroupBox("Sohbet")
        f2 = QFormLayout(g2)
        self.ed_room = QLineEdit(str(self.cfg["chatroom_id"]),
                                 placeholderText="Boş bırakılırsa otomatik bulunur")
        self.ed_pkey = QLineEdit(self.cfg["pusher_key"])
        self.ed_pcl = QLineEdit(self.cfg["pusher_cluster"])
        f2.addRow("Chatroom ID:", self.ed_room)
        f2.addRow("Pusher key:", self.ed_pkey)
        f2.addRow("Pusher cluster:", self.ed_pcl)
        lay.addWidget(g2)

        lay.addWidget(QPushButton("Kaydet", clicked=self.save_settings))
        lay.addWidget(QLabel(f"Ayar klasörü: {APP_DIR}\nSohbet günlüğü: {LOG_PATH}"))
        lay.addStretch()
        return w

    def save_settings(self):
        self.cfg.update({
            "client_id": self.ed_cid.text().strip(),
            "client_secret": self.ed_secret.text().strip(),
            "redirect_uri": self.ed_redirect.text().strip(),
            "chatroom_id": self.ed_room.text().strip(),
            "pusher_key": self.ed_pkey.text().strip() or DEFAULT_KEY,
            "pusher_cluster": self.ed_pcl.text().strip() or DEFAULT_CLUSTER,
        })
        save_config(self.cfg)
        self._init_api()
        self.bus.status.emit("Ayarlar kaydedildi")

    # ===================== KICK =====================
    def _init_api(self):
        if not self.cfg["client_id"]:
            self.lbl_user.setText("Önce Ayarlar sekmesinden Client ID / Secret girin")
            return
        self.api = KickAPI(self.cfg["client_id"], self.cfg["client_secret"],
                           self.cfg["redirect_uri"], TOKEN_PATH)
        if self.api.logged_in:
            self._after_login()

    def login(self):
        if not self.api:
            return self.bus.error.emit("Önce Ayarlar sekmesinden Client ID / Secret girin")
        self.bus.status.emit("Tarayıcıda Kick girişi bekleniyor...")
        run_bg(self.api.login, self.bus, lambda _: self.bus.logged_in.emit())

    def logout(self):
        if self.api:
            self.api.logout()
        if self.chat_client:
            self.chat_client.stop()
            self.chat_client = None
        self.channel_data = {}
        self.poll.stop()
        self.lbl_user.setText("Giriş yapılmadı")

    def _after_login(self):
        def fetch():
            me = self.api.me()
            ch = self.api.channel() or {}
            ch["_me"] = me
            return ch
        run_bg(fetch, self.bus, lambda ch: self.bus.channel.emit(ch))
        self.poll.start()

    def refresh_channel(self):
        if self.api and self.api.logged_in:
            run_bg(self.api.channel, self.bus, lambda ch: self.bus.channel.emit(ch or {}))

    def _show_channel(self, ch):
        first = not self.channel_data
        me = ch.pop("_me", None)
        self.channel_data.update(ch)
        if me:
            self.me = me
            self.lbl_user.setText(f"<b>{html.escape(me.get('name', ''))}</b>  (kick.com/{ch.get('slug', '')})")
        stream = ch.get("stream") or {}
        if stream.get("is_live"):
            self.lbl_live.setText(f"<span style='color:{P['kick']}'>● CANLI</span>")
            self.lbl_live_badge.setText(
                f"<span style='background:{P['kick']}; color:{P['night']}; font-weight:800;'>"
                f"&nbsp; ● CANLI · {stream.get('viewer_count', 0)} izleyici &nbsp;</span>")
        else:
            self.lbl_live.setText(f"<span style='color:{P['lav']}'>● Çevrimdışı</span>")
            self.lbl_live_badge.setText(f"<span style='color:{P['lav']}'>● ÇEVRİMDIŞI</span>")
        self.lbl_viewers.setText(str(stream.get("viewer_count", 0)))
        self.lbl_started.setText(stream.get("start_time") or "—")
        self.lbl_cat.setText((ch.get("category") or {}).get("name", "—"))
        self.lbl_title.setText(html.escape(ch.get("stream_title") or "—"))
        if first:
            self.ed_title.setText(ch.get("stream_title", ""))
            self._start_chat()

    def search_categories(self):
        q = self.ed_cat.text().strip()
        if q and self.api:
            run_bg(lambda: self.api.search_categories(q), self.bus,
                   lambda r: self.bus.categories.emit(r))

    def _show_categories(self, cats):
        self.cmb_cat.clear()
        for c in cats:
            self.cmb_cat.addItem(c.get("name", "?"), c.get("id"))
        if not cats:
            self.bus.status.emit("Kategori bulunamadı")

    def update_channel(self):
        title = self.ed_title.text().strip() or None
        cat = self.cmb_cat.currentData()
        cat_name = self.cmb_cat.currentText() if cat else None

        def do():
            self.api.update_channel(title, cat)
            ch = {}
            for _ in range(4):            # Kick bazen birkaç saniye eski veriyi döndürür
                time.sleep(1.5)
                ch = self.api.channel() or {}
                ok_t = title is None or ch.get("stream_title") == title
                ok_c = cat is None or (ch.get("category") or {}).get("id") == cat
                if ok_t and ok_c:
                    break
            if title is not None and ch.get("stream_title") != title:
                ch["stream_title"] = title     # API henüz eski değeri dönüyorsa yine de göster
            if cat is not None and (ch.get("category") or {}).get("id") != cat:
                ch["category"] = {"id": cat, "name": cat_name}
            return ch
        self.bus.status.emit("Yayın bilgisi gönderiliyor...")
        run_bg(do, self.bus, lambda ch: (self.bus.channel.emit(ch),
                                         self.bus.status.emit("Yayın bilgisi güncellendi ✓")))

    # ===================== SOHBET =====================
    def _start_chat(self):
        room = self.cfg.get("chatroom_id")

        def go(room_id):
            if not room_id:
                self.bus.chat_sys.emit("Chatroom ID otomatik bulunamadı — Ayarlar'dan elle girin (README'ye bakın)")
                return
            if self.chat_client:
                self.chat_client.stop()
            self.chat_client = KickChat(room_id, self.bus.chat.emit, self.bus.chat_sys.emit,
                                        self.cfg["pusher_key"], self.cfg["pusher_cluster"],
                                        on_state=self.bus.chat_state.emit)
            self.chat_client.start()

        if room:
            go(room)
        else:
            slug = self.channel_data.get("slug")
            run_bg(lambda: find_chatroom_id(slug), self.bus, go)

    def _add_chat(self, m):
        if m.get("id"):
            if m["id"] in self._seen_ids:
                return                     # kendi mesajımızın websocket yankısı
            self._seen_ids.add(m["id"])
        badges = [b for b in m["badges"] if b]
        icons = {"broadcaster": "★ ", "moderator": "⚔ ", "vip": "◆ ", "subscriber": "♦ ",
                 "og": "● ", "founder": "✦ "}
        prefix = "".join(icons.get(b, "") for b in badges)
        item = QListWidgetItem(f"{prefix}{m['username']}:  {m['content']}")
        item.setData(Qt.UserRole, m)
        if "broadcaster" in badges:
            item.setForeground(QColor(P["ice"]))
        elif "moderator" in badges:
            item.setForeground(QColor(P["turq"]))
        elif "vip" in badges:
            item.setForeground(QColor(P["gold"]))
        elif "subscriber" in badges or "founder" in badges:
            item.setForeground(QColor(P["sub"]))
        else:
            item.setForeground(QColor(P["text"]))
        self.chat_list.addItem(item)
        if self.chat_list.count() > 500:
            self.chat_list.takeItem(0)
        self.chat_list.scrollToBottom()

    STATES = {"connected": ("#53fc18", "Bağlı"), "connecting": ("#f5a623", "Bağlanıyor..."),
              "retrying": ("#f5a623", "Yeniden deneniyor..."), "stopped": ("#ff4d4d", "Kapalı")}

    def _set_ind(self, lbl, name, state):
        color, text = self.STATES.get(state, ("#888", state))
        lbl.setText(f"{name}: <span style='color:{color}'>●</span> {text}")

    def _add_sys(self, text):
        event_colors = {"Subscription": P["sub"], "GiftedSubscriptions": P["sub"],
                        "Kicks": P["kick"], "Donation": P["gold"], "Tip": P["gold"],
                        "StreamHost": P["blue"], "Follow": P["turq"]}
        color = next((c for k, c in event_colors.items() if k in text), None)
        item = QListWidgetItem(("✦ " if color else "⚙ ") + text)
        item.setForeground(QColor(color or P["lav"]))
        self.chat_list.addItem(item)
        self.chat_list.scrollToBottom()
        self.statusBar().showMessage(text, 8000)

    def send_chat(self):
        text = self.ed_msg.text().strip()
        bid = self.channel_data.get("broadcaster_user_id")
        if not text or not bid:
            return
        self.ed_msg.clear()
        me = self.me

        def shown(res):
            data = (res or {}).get("data") or {}
            if data.get("is_sent") is False:
                self.bus.chat_sys.emit("Mesaj Kick tarafından reddedildi (yavaş mod / yasaklı kelime olabilir)")
                return
            self.bus.chat.emit({"id": data.get("message_id"), "user_id": me.get("user_id"),
                                "username": me.get("name", "Ben"), "color": "#53fc18",
                                "badges": ["broadcaster"], "content": text})
        run_bg(lambda: self.api.send_chat(bid, text), self.bus, shown)

    def _chat_menu(self, pos):
        item = self.chat_list.itemAt(pos)
        if not item:
            return
        m = item.data(Qt.UserRole)
        if not m:
            return
        bid = self.channel_data.get("broadcaster_user_id")
        menu = QMenu(self)
        for label, dur in (("Timeout 1 dk", 1), ("Timeout 10 dk", 10), ("Timeout 1 saat", 60)):
            menu.addAction(QAction(label, self, triggered=lambda _=False, d=dur:
                                   run_bg(lambda: self.api.ban(bid, m["user_id"], d), self.bus,
                                          lambda _: self.bus.status.emit(f"{m['username']} susturuldu"))))
        menu.addSeparator()

        def do_ban():
            reason, ok = QInputDialog.getText(self, "Ban", f"{m['username']} için sebep:")
            if ok:
                run_bg(lambda: self.api.ban(bid, m["user_id"], None, reason), self.bus,
                       lambda _: self.bus.status.emit(f"{m['username']} banlandı"))
        menu.addAction(QAction("Kalıcı Ban", self, triggered=do_ban))
        menu.addAction(QAction("Banı Kaldır", self, triggered=lambda: run_bg(
            lambda: self.api.unban(bid, m["user_id"]), self.bus)))
        menu.exec(self.chat_list.mapToGlobal(pos))

    # ===================== KAMERA MANTIĞI =====================
    def _start_discovery(self):
        self.discovery = Discovery(self.bus.camera_found.emit)
        if not self.discovery.start():
            self.cmb_dev.setItemText(0, "(zeroconf yüklü değil — IP girin)")

    def _camera_found(self, name, host, port):
        if self.cmb_dev.findText(name) == -1:
            self.cmb_dev.addItem(name, (host, port))
            self.bus.status.emit(f"iPhone bulundu: {name} ({host})")

    def _device_selected(self, i):
        d = self.cmb_dev.itemData(i)
        if d:
            self.ed_host.setText(d[0])
            self.sp_port.setValue(d[1])

    def toggle_camera(self):
        if self.receiver:
            self.receiver.stop()
            self.receiver = None
            self.btn_cam.setText("Bağlan")
            return
        host = self.ed_host.text().strip()
        if not host:
            return self.bus.error.emit("iPhone IP adresini girin")
        self.cfg.update(camera_host=host, camera_port=self.sp_port.value(), camera_fps=self.sp_fps.value())
        save_config(self.cfg)
        self.receiver = CameraReceiver(host, self.sp_port.value(), self.bus.frame.emit,
                                       self.bus.status.emit, self.chk_vcam.isChecked(),
                                       self.sp_fps.value(), on_state=self.bus.cam_state.emit)
        self.receiver.start()
        self.btn_cam.setText("Bağlantıyı Kes")

    def _store_frame(self, frame):
        self._last_frame = frame

    def _paint_preview(self):
        if self._last_frame is None:
            return
        f, self._last_frame = self._last_frame, None
        rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(
            self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if self.receiver:
            self.lbl_fps.setText(f"FPS: {self.receiver.stats_fps:.1f}   Çözünürlük: {w}x{h}")

    def closeEvent(self, e):
        if self.receiver:
            self.receiver.stop()
        if self.chat_client:
            self.chat_client.stop()
        if self.discovery:
            self.discovery.stop()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
