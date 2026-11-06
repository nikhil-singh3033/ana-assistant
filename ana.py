"""
ANA - Laptop Voice Assistant (floating Siri-style UI)

Run:  python ana.py
Jagane ke liye bolo:  "Hey Ana"  (ya sirf "Ana")
Ya neeche text box mein command type karo.
"""

import datetime
import math
import os
import platform
import queue
import random
import re
import subprocess
import threading
import time
import tkinter as tk
import urllib.parse
import webbrowser

import psutil
import pyautogui
import pyttsx3
import speech_recognition as sr
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ASSISTANT_NAME = "Ana"
# Mic "ana" ko aksar alag sunta hai (anna, aana...). Bina bulaye chalne lage
# to is list se extra naam hata do.
WAKE_WORDS = ["ana", "anna", "aana", "anaa", "anah", "ena", "ann",
              "heyana", "heyanna"]
LANGUAGE = "en-IN"          # Hinglish ke liye best chalta hai
FOLLOWUP_SECONDS = 15       # wake ke baad itni der tak bina "Hey Ana" bole sunta rahega
OS = platform.system()      # Windows / Darwin / Linux

SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "github": "https://github.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
    "canva": "https://www.canva.com",
}

APPS = {
    "Windows": {
        "notepad": "notepad", "calculator": "calc", "paint": "mspaint",
        "chrome": "chrome", "word": "winword", "excel": "excel",
        "powerpoint": "powerpnt", "cmd": "cmd", "explorer": "explorer",
        "task manager": "taskmgr", "settings": "ms-settings:",
        "vs code": "code", "vscode": "code",
    },
    "Darwin": {
        "notes": "Notes", "calculator": "Calculator", "chrome": "Google Chrome",
        "safari": "Safari", "terminal": "Terminal", "vs code": "Visual Studio Code",
    },
    "Linux": {
        "calculator": "gnome-calculator", "terminal": "gnome-terminal",
        "chrome": "google-chrome", "vs code": "code", "files": "nautilus",
    },
}

JOKES = [
    "Programmer ko bola gaya ki bahar dhoop hai, usne kaha, mera screen brightness already full hai.",
    "Python seekhna easy hai, bas indentation se dosti kar lo.",
    "Bug nahi hai boss, wo toh feature hai.",
]


# ----------------------------------------------------------------- actions --
def split_wake_word(text):
    """Wake word mila to (True, uske baad ka command), warna (False, text)."""
    words = re.findall(r"[\w']+", text.lower())
    for i, w in enumerate(words):
        if w in WAKE_WORDS:
            return True, " ".join(words[i + 1:])
    return False, text


def beep():
    """Jaagne ki chhoti awaaz (sirf Windows pe)."""
    if OS != "Windows":
        return
    try:
        import winsound
        winsound.Beep(1000, 80)
        winsound.Beep(1450, 90)
    except Exception:
        pass


def open_app(name):
    apps = APPS.get(OS, {})
    for key, target in apps.items():
        if key in name:
            try:
                if OS == "Windows":
                    os.system(f'start "" {target}')
                elif OS == "Darwin":
                    subprocess.Popen(["open", "-a", target])
                else:
                    subprocess.Popen([target])
                return f"{key} khol rahi hoon"
            except Exception:
                return f"{key} nahi khul paya"
    for key, url in SITES.items():
        if key in name:
            webbrowser.open(url)
            return f"{key} khol rahi hoon"
    return None


def system_lock():
    if OS == "Windows":
        os.system("rundll32.exe user32.dll,LockWorkStation")
    elif OS == "Darwin":
        os.system("pmset displaysleepnow")
    else:
        os.system("loginctl lock-session")


def take_screenshot():
    folder = os.path.join(os.path.expanduser("~"), "Pictures")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"ana_{int(time.time())}.png")
    pyautogui.screenshot(path)
    return path


def handle(cmd, assistant):
    """Command text -> reply text. 'EXIT' return karne par band ho jata hai."""
    c = cmd.lower().strip()
    if not c:
        return None

    if any(w in c for w in ("so ja", "go to sleep", "sleep mode", "chup ho ja", "rest kar")):
        assistant.force_sleep = True
        return "Theek hai, jab zaroorat ho to Hey Ana bolna"

    if any(w in c for w in ("exit", "quit", "band ho ja", "bye", "alvida")):
        return "EXIT"

    if any(w in c for w in ("time", "samay", "kitne baje")):
        return datetime.datetime.now().strftime("Abhi %I:%M %p ho raha hai")

    if any(w in c for w in ("date", "aaj kya", "tarikh", "today")):
        return datetime.datetime.now().strftime("Aaj %A, %d %B %Y hai")

    if "battery" in c:
        b = psutil.sensors_battery()
        if b is None:
            return "Battery info nahi mil rahi"
        plug = "charging mein hai" if b.power_plugged else "charging pe nahi hai"
        return f"Battery {int(b.percent)} percent hai aur {plug}"

    if "cpu" in c or "ram" in c or "system" in c:
        return (f"CPU {psutil.cpu_percent(interval=0.5)} percent aur "
                f"RAM {psutil.virtual_memory().percent} percent use ho rahi hai")

    if "volume" in c or "awaz" in c or "awaaz" in c:
        if any(w in c for w in ("up", "badha", "increase", "zyada")):
            for _ in range(5):
                pyautogui.press("volumeup")
            return "Volume badha diya"
        if any(w in c for w in ("down", "kam", "ghata", "decrease", "low")):
            for _ in range(5):
                pyautogui.press("volumedown")
            return "Volume kam kar diya"
        if "mute" in c:
            pyautogui.press("volumemute")
            return "Mute toggle kar diya"

    if "screenshot" in c:
        take_screenshot()
        return "Screenshot Pictures folder mein save ho gaya"

    if "lock" in c:
        system_lock()
        return "Laptop lock kar rahi hoon"

    if "joke" in c or "mazak" in c or "hasa" in c:
        return random.choice(JOKES)

    if c.startswith(("search ", "google ")) or "search for" in c:
        q = c.replace("search for", "").replace("search", "").replace("google", "").strip()
        if q:
            webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(q))
            return f"{q} search kar rahi hoon"

    if "play" in c and ("youtube" in c or "song" in c or "gana" in c):
        q = c.replace("play", "").replace("on youtube", "").replace("youtube", "").strip()
        if q:
            webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
            return f"YouTube pe {q} dhoond rahi hoon"

    if c.startswith(("open ", "kholo ", "start ")) or " khol" in c:
        name = c
        for w in ("open", "kholo", "start", "khol do", "khol", "please", "karo"):
            name = name.replace(w, "")
        name = name.strip()
        res = open_app(name)
        return res or f"{name} ka mujhe pata nahi hai"

    if "type " in c:
        text = c.split("type ", 1)[1]
        pyautogui.write(text, interval=0.03)
        return "Type kar diya"

    if any(w in c for w in ("who are you", "tum kaun", "tera naam", "apna naam", "your name")):
        return f"Main {ASSISTANT_NAME} hoon, aapki laptop assistant"

    if any(w in c for w in ("hello", "hi ", "namaste", "hey")):
        return "Namaste! Boliye, kya karna hai?"

    return "Ye command abhi mujhe samajh nahi aaya"


# ------------------------------------------------------------------- voice --
class Voice:
    def __init__(self, ui_queue):
        self.q = ui_queue
        self.rec = sr.Recognizer()
        self.rec.dynamic_energy_threshold = True
        self.rec.pause_threshold = 0.8
        self.muted = False
        self.running = True
        self.awake_until = 0
        self.force_sleep = False
        self.ignore_until = 0       # apni hi awaaz na sun le
        self.lock = threading.Lock()

    # ---- awake helpers
    def is_awake(self):
        return time.time() < self.awake_until

    def idle_state(self):
        return "listening" if self.is_awake() else "sleeping"

    def set_awake(self, secs=FOLLOWUP_SECONDS):
        if not self.is_awake():
            self.q.put(("pulse", None))     # UI mein jaagne ka ring
        self.awake_until = time.time() + secs

    # ---- speaking
    def speak(self, text):
        with self.lock:
            self.q.put(("state", "speaking"))
            self.q.put(("reply", text))
            try:
                engine = pyttsx3.init()      # har baar naya engine = thread-safe
                engine.setProperty("rate", 175)
                # Ana ke liye female awaaz chuno agar available ho (Windows pe Zira/Heera)
                for v in engine.getProperty("voices"):
                    if any(k in v.name.lower() for k in ("zira", "heera", "female", "hazel")):
                        engine.setProperty("voice", v.id)
                        break
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print("TTS error:", e)
            self.ignore_until = time.time() + 0.7
            self.q.put(("state", self.idle_state()))

    # ---- listening
    def listen_once(self, mic, timeout, limit):
        try:
            audio = self.rec.listen(mic, timeout=timeout, phrase_time_limit=limit)
        except sr.WaitTimeoutError:
            return None
        if self.is_awake():
            self.q.put(("state", "thinking"))
        try:
            return self.rec.recognize_google(audio, language=LANGUAGE).lower()
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            self.q.put(("reply", "Internet check karo, speech service nahi chal rahi"))
            return None

    # ---- ek command ko chalana (voice aur typed dono ke liye)
    def process(self, cmd):
        """True return kare to app band ho rahi hai."""
        reply = handle(cmd, self)
        if self.force_sleep:
            self.awake_until = 0
            self.force_sleep = False
        else:
            self.set_awake()
        if reply == "EXIT":
            self.speak("Theek hai, bye!")
            self.q.put(("quit", None))
            return True
        if reply:
            self.speak(reply)
        return False

    def process_typed(self, text):
        self.q.put(("heard", text))
        self.process(text)

    def activate(self):
        beep()
        self.set_awake()
        self.speak(random.choice(["Ji boliye", "Haan boliye", "Boliye"]))

    def loop(self):
        try:
            mic = sr.Microphone()
        except Exception as e:
            self.q.put(("reply", f"Mic nahi mila: {e}"))
            return
        with mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)
        self.speak(f"{ASSISTANT_NAME} ready hai. Hey Ana bolkar jagao")

        while self.running:
            if self.muted:
                self.q.put(("state", "muted"))
                time.sleep(0.3)
                continue

            self.q.put(("state", self.idle_state()))
            awake = self.is_awake()
            with mic as src:
                text = self.listen_once(src, timeout=3, limit=8 if awake else 5)
            if not text or time.time() < self.ignore_until:
                continue

            woke, cmd = split_wake_word(text)
            if not woke and not self.is_awake():
                continue                      # so rahi hai, ye bakwaas ignore

            self.q.put(("heard", text))
            if woke:
                if not cmd:
                    self.activate()
                    continue
                self.set_awake()
            else:
                cmd = text

            if self.process(cmd):
                return


# ---------------------------------------------------------------------- UI --
# Poora UI Pillow se draw hota hai (glow, gradient, glass orb), tkinter sirf dikhata hai.
LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
BILINEAR = getattr(Image, "Resampling", Image).BILINEAR

KEY = (1, 1, 1)                 # window ke bahar ka transparent rang
KEY_HEX = "#010101"
W, H = 380, 610
CARD_BOX = (10, 10, 370, 600)
RADIUS = 64

C_CYAN = (34, 211, 238)
C_SKY = (56, 189, 248)
C_BLUE = (99, 102, 241)
C_PURPLE = (168, 85, 247)
C_MAGENTA = (217, 70, 239)
C_PINK = (244, 63, 140)

ORB_C, ORB_R, ORB_S = (190, 222), 94, 300
BAR_C, BAR_W, BAR_H = (190, 462), 300, 70
MIC_C, MIC_M = (190, 540), 116
KBD_C, GEAR_C, SIDE_R = (102, 540), (278, 540), 24

# state ke hisaab se orb ke 3 petal-groups ke rang, roshni, speed...
PAL = {
    "sleeping":  dict(c=(C_CYAN, C_PINK, C_PURPLE), inten=0.42, pulse=0.03, speed=0.35, bars=0.0, glow=0.35),
    "listening": dict(c=(C_CYAN, C_PINK, C_PURPLE), inten=0.95, pulse=0.10, speed=1.00, bars=18.0, glow=0.85),
    "thinking":  dict(c=(C_PURPLE, C_BLUE, C_CYAN), inten=0.90, pulse=0.06, speed=2.60, bars=7.0, glow=0.80),
    "speaking":  dict(c=(C_PINK, C_CYAN, C_PURPLE), inten=1.00, pulse=0.28, speed=1.50, bars=30.0, glow=1.00),
    "muted":     dict(c=((107, 114, 128), (75, 85, 99), (55, 65, 81)), inten=0.30, pulse=0.0,
                      speed=0.15, bars=0.0, glow=0.12),
}
OMEGA = (0.9, -0.7, 0.45)       # har group kitni tezi se ghoomta hai
BAR_STOPS = [(0.0, C_CYAN), (0.35, (59, 130, 246)), (0.55, (124, 92, 250)),
             (0.78, C_MAGENTA), (1.0, C_PINK)]


def lerp3(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def ci(c):
    return tuple(max(0, min(255, int(round(v)))) for v in c)


def ramp(frac):
    for (f0, c0), (f1, c1) in zip(BAR_STOPS, BAR_STOPS[1:]):
        if frac <= f1:
            return lerp3(c0, c1, (frac - f0) / (f1 - f0))
    return BAR_STOPS[-1][1]


def corner_gradient(size, tl, tr, br, bl):
    """4 corners ke rang se smooth gradient."""
    w, h = size
    hm = Image.linear_gradient("L").rotate(90).resize((w, h))     # left kaala -> right safed
    vm = Image.linear_gradient("L").resize((w, h))                # upar kaala -> neeche safed
    top = Image.composite(Image.new("RGB", (w, h), tr), Image.new("RGB", (w, h), tl), hm)
    bot = Image.composite(Image.new("RGB", (w, h), br), Image.new("RGB", (w, h), bl), hm)
    return Image.composite(bot, top, vm)


def rr_mask(size, box, r, width=None, ss=4):
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(m)
    b = [v * ss for v in box]
    if width is None:
        d.rounded_rectangle(b, radius=r * ss, fill=255)
    else:
        d.rounded_rectangle(b, radius=r * ss, outline=255, width=int(width * ss))
    return m.resize((w, h), LANCZOS)


def disc_mask(size, cx, cy, r, ss=4):
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).ellipse([(cx - r) * ss, (cy - r) * ss, (cx + r) * ss, (cy + r) * ss], fill=255)
    return m.resize((w, h), LANCZOS)


def radial_L(radius, size, power=1.0, invert=False):
    g = Image.radial_gradient("L").resize((2 * radius, 2 * radius), BILINEAR)
    g = g.point([min(255, int(v * 1.4142)) for v in range(256)])   # kinare par poora 255
    if power != 1.0:
        g = g.point([int(255 * ((v / 255.0) ** power)) for v in range(256)])
    if invert:
        g = ImageChops.invert(g)
    canvas = Image.new("L", (size, size), 0)
    canvas.paste(g, (size // 2 - radius, size // 2 - radius))
    return canvas


def lut_scale(img, k):
    k = max(0.0, k)
    return img.point([min(255, int(v * k)) for v in range(256)])


def tint(mask, color, size):
    """L mask ko rang ke saath RGB layer banao (mask ke bahar kaala)."""
    return Image.composite(Image.new("RGB", size, ci(color)), Image.new("RGB", size, (0, 0, 0)), mask)


def small_patch(size, draw_fn, ss=4):
    """Chhote icon ko supersample karke L mask banao."""
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    draw_fn(ImageDraw.Draw(m), ss)
    return m.resize((w, h), LANCZOS)


# ---- icons (sab L masks) -----------------------------------------------
def star_mask(size, cx, cy, r_out, r_in):
    def fn(d, ss):
        pts = []
        for k in range(8):
            ang = math.pi / 4 * k - math.pi / 2
            rr = r_out if k % 2 == 0 else r_in
            pts.append(((cx + rr * math.cos(ang)) * ss, (cy + rr * math.sin(ang)) * ss))
        d.polygon(pts, fill=255)
    return small_patch(size, fn)


def keyboard_mask(size):
    def fn(d, ss):
        d.rounded_rectangle([7 * ss, 14 * ss, 41 * ss, 34 * ss], radius=5 * ss, outline=255, width=2 * ss)
        for row, y in enumerate((18.5, 23.5)):
            for i in range(6):
                x = 11.5 + i * 4.6 + (2.3 if row else 0)
                if x < 37:
                    d.rounded_rectangle([x * ss, y * ss, (x + 2) * ss, (y + 2) * ss], radius=ss * 0.5, fill=255)
        d.rounded_rectangle([14 * ss, 28.2 * ss, 34 * ss, 30.4 * ss], radius=ss, fill=255)
    return small_patch(size, fn)


def gear_mask(size):
    def fn(d, ss):
        c = 24 * ss
        d.ellipse([c - 9.5 * ss, c - 9.5 * ss, c + 9.5 * ss, c + 9.5 * ss], fill=255)
        for k in range(8):
            ang = k * math.pi / 4
            ca, sa = math.cos(ang), math.sin(ang)
            pts = []
            for (u, v) in ((8, -2.6), (13, -2.6), (13, 2.6), (8, 2.6)):
                pts.append((c + (u * ca - v * sa) * ss, c + (u * sa + v * ca) * ss))
            d.polygon(pts, fill=255)
        d.ellipse([c - 4.4 * ss, c - 4.4 * ss, c + 4.4 * ss, c + 4.4 * ss], fill=0)
    return small_patch(size, fn)


def mic_icon_mask(size, slash=False):
    def fn(d, ss):
        c = size[0] / 2
        d.rounded_rectangle([(c - 6.5) * ss, (c - 18) * ss, (c + 6.5) * ss, (c + 4) * ss],
                            radius=6.5 * ss, fill=255)
        d.arc([(c - 12.5) * ss, (c - 11) * ss, (c + 12.5) * ss, (c + 14) * ss], 0, 180, fill=255, width=2 * ss)
        d.line([c * ss, (c + 14) * ss, c * ss, (c + 20) * ss], fill=255, width=2 * ss)
        d.line([(c - 6) * ss, (c + 20) * ss, (c + 6) * ss, (c + 20) * ss], fill=255, width=2 * ss)
        if slash:
            d.line([(c - 15) * ss, (c - 16) * ss, (c + 15) * ss, (c + 18) * ss], fill=255, width=3 * ss)
    return small_patch(size, fn)


# ---- static background (ek baar banta hai) -------------------------------
def build_static():
    size = (W, H)
    grad = corner_gradient(size, C_SKY, C_MAGENTA, C_CYAN, C_PINK)

    vm = Image.linear_gradient("L").resize(size)
    card = Image.composite(Image.new("RGB", size, (5, 6, 14)), Image.new("RGB", size, (8, 10, 22)), vm)

    inner = lut_scale(rr_mask(size, CARD_BOX, RADIUS, width=16).filter(ImageFilter.GaussianBlur(15)), 0.38)
    card = Image.composite(grad, card, inner)
    soft = lut_scale(rr_mask(size, CARD_BOX, RADIUS, width=5).filter(ImageFilter.GaussianBlur(2)), 0.65)
    card = Image.composite(grad, card, soft)
    card = Image.composite(grad, card, rr_mask(size, CARD_BOX, RADIUS, width=2))

    # header: sparkle star
    sg = corner_gradient(size, C_PURPLE, C_SKY, C_CYAN, C_BLUE)
    star = star_mask(size, 59, 54, 17, 4.2)
    star_glow = lut_scale(star.filter(ImageFilter.GaussianBlur(5)), 0.55)
    card = Image.composite(sg, card, star_glow)
    card = Image.composite(sg, card, star)

    # "Online" pill
    pill_box = (266, 41, 336, 67)
    card = Image.composite(Image.new("RGB", size, (11, 14, 26)), card, rr_mask(size, pill_box, 13))
    card = Image.composite(Image.new("RGB", size, (38, 44, 62)), card, rr_mask(size, pill_box, 13, width=1))

    # side buttons (keyboard, gear)
    for (cx, cy), icon in ((KBD_C, keyboard_mask((2 * SIDE_R, 2 * SIDE_R))), (GEAR_C, gear_mask((2 * SIDE_R, 2 * SIDE_R)))):
        card = Image.composite(Image.new("RGB", size, (11, 14, 26)), card,
                               disc_mask(size, cx, cy, SIDE_R))
        ring = ImageChops.subtract(disc_mask(size, cx, cy, SIDE_R), disc_mask(size, cx, cy, SIDE_R - 1.2))
        card = Image.composite(Image.new("RGB", size, (34, 40, 58)), card, ring)
        full = Image.new("L", size, 0)
        full.paste(icon, (cx - SIDE_R, cy - SIDE_R))
        card = Image.composite(Image.new("RGB", size, (190, 196, 212)), card, full)

    # card ke bahar ka hissa transparent key rang
    return Image.composite(card, Image.new("RGB", size, KEY), rr_mask(size, CARD_BOX, RADIUS))


# ---- dynamic renderer ----------------------------------------------------
class Renderer:
    def __init__(self):
        self.static = build_static()
        S = ORB_S
        self.black = Image.new("RGB", (S, S), (0, 0, 0))

        # orb ke assets
        c, R = S / 2, ORB_R
        self.sphere_mask = disc_mask((S, S), c, c, R)
        base_c = Image.new("RGB", (S, S), (2, 4, 16))
        base_e = Image.new("RGB", (S, S), (6, 22, 54))
        self.sphere_base = Image.composite(base_e, base_c, radial_L(R, S, power=1.7))
        og = corner_gradient((S, S), C_SKY, C_MAGENTA, C_CYAN, C_PINK)
        rim_soft = Image.composite(og, self.black, lut_scale(radial_L(R, S, power=6.5), 0.55))
        ring_m = ImageChops.subtract(disc_mask((S, S), c, c, R), disc_mask((S, S), c, c, R - 2.4))
        rim_ring = Image.composite(og, self.black, ring_m.filter(ImageFilter.GaussianBlur(0.6)))
        hl = Image.new("L", (S, S), 0)
        ImageDraw.Draw(hl).ellipse([c - 0.72 * R, c - 0.82 * R, c - 0.05 * R, c - 0.30 * R], fill=42)
        hl = hl.filter(ImageFilter.GaussianBlur(9))
        self.rim = ImageChops.screen(ImageChops.screen(rim_soft, rim_ring),
                                     Image.composite(Image.new("RGB", (S, S), (200, 230, 255)), self.black, hl))
        self.glow_mask = radial_L(S // 2 - 1, S, power=2.2, invert=True)
        self.center_mask = radial_L(int(R * 0.52), S, power=1.8, invert=True)

        # waveform / mic ke assets
        self.bar_bg = self.static.crop((BAR_C[0] - BAR_W // 2, BAR_C[1] - BAR_H // 2,
                                        BAR_C[0] + BAR_W // 2, BAR_C[1] + BAR_H // 2)).convert("RGBA")
        M = MIC_M
        mc = M / 2
        self.mic_bg = self.static.crop((MIC_C[0] - M // 2, MIC_C[1] - M // 2,
                                        MIC_C[0] + M // 2, MIC_C[1] + M // 2))
        self.mic_disc = disc_mask((M, M), mc, mc, 31)
        self.mic_ring = ImageChops.subtract(disc_mask((M, M), mc, mc, 34), disc_mask((M, M), mc, mc, 31.2))
        self.mic_icon = mic_icon_mask((M, M))
        self.mic_icon_muted = mic_icon_mask((M, M), slash=True)
        self.mic_grad = corner_gradient((M, M), C_CYAN, C_BLUE, C_PURPLE, C_SKY)
        self.mic_grad_muted = corner_gradient((M, M), (248, 113, 113), (220, 60, 60), (185, 28, 28), (239, 90, 90))
        self.orb_bg = self.static.crop((ORB_C[0] - S // 2, ORB_C[1] - S // 2,
                                        ORB_C[0] + S // 2, ORB_C[1] + S // 2))

        # animation state
        th = PAL["sleeping"]
        self.cur = dict(c=[tuple(x) for x in th["c"]], inten=th["inten"], pulse=th["pulse"],
                        speed=th["speed"], bars=th["bars"], glow=th["glow"])
        self.phase = [0.0, 2.0, 4.0]
        self.t = 0.0
        self.ring = None            # jaagne par phailne wali ring (0..1)

    def _blend_state(self, state, dt):
        th = PAL.get(state, PAL["sleeping"])
        k = 1 - math.exp(-dt * 6.0)
        self.cur["c"] = [lerp3(a, b, k) for a, b in zip(self.cur["c"], th["c"])]
        for key in ("inten", "pulse", "speed", "bars", "glow"):
            self.cur[key] += (th[key] - self.cur[key]) * k
        self.t += dt
        for i in range(3):
            self.phase[i] += OMEGA[i] * self.cur["speed"] * dt
        if self.ring is not None:
            self.ring += dt * 1.1
            if self.ring >= 1:
                self.ring = None

    def render_orb(self):
        S, R = ORB_S, ORB_R
        c = S / 2
        cur = self.cur
        base = self.sphere_base.copy()
        groups = ((3, 0.52, 0.19, 0.95), (3, 0.52, 0.19, 0.90), (3, 0.54, 0.26, 0.65))
        for gi, (n, la, wb, al) in enumerate(groups):
            m = Image.new("L", (S, S), 0)
            d = ImageDraw.Draw(m)
            for j in range(n):
                ang = self.phase[gi] + j * 2 * math.pi / n
                wob = 1 + cur["pulse"] * math.sin(self.t * 3.1 + gi * 2.0 + j * 1.7)
                dist = 0.40 * R * wob
                a, b = la * R * wob, wb * R
                ex0, ey0 = c + dist * math.cos(ang), c + dist * math.sin(ang)
                ca, sa = math.cos(ang), math.sin(ang)
                pts = []
                for k in range(30):
                    th = 2 * math.pi * k / 30
                    ex, ey = a * math.cos(th), b * math.sin(th)
                    pts.append((ex0 + ex * ca - ey * sa, ey0 + ex * sa + ey * ca))
                d.polygon(pts, fill=255)
            m = lut_scale(m.filter(ImageFilter.GaussianBlur(3.2)), al * cur["inten"])
            base = ImageChops.screen(base, tint(m, cur["c"][gi], (S, S)))

        flick = 0.88 + 0.12 * math.sin(self.t * 2.3)
        cg = lut_scale(self.center_mask, min(1.0, (0.25 + 0.75 * cur["inten"] ** 1.4) * flick))
        base = ImageChops.screen(base, tint(cg, (235, 250, 255), (S, S)))
        base = ImageChops.screen(base, Image.blend(self.black, self.rim, 0.35 + 0.65 * cur["inten"]))

        gcol = lerp3(cur["c"][0], cur["c"][2], 0.5)
        bg = self.orb_bg.copy()
        bg = ImageChops.screen(bg, tint(lut_scale(self.glow_mask, 0.42 * cur["glow"]), gcol, (S, S)))

        if self.ring is not None:                       # jaagne ki ring
            p = self.ring
            rm = Image.new("L", (S, S), 0)
            rr = R + 8 + p * 48
            ImageDraw.Draw(rm).ellipse([c - rr, c - rr, c + rr, c + rr], outline=255, width=3)
            rm = lut_scale(rm.filter(ImageFilter.GaussianBlur(1.2)), (1 - p) * 0.95)
            bg = ImageChops.screen(bg, tint(rm, lerp3(cur["c"][0], (255, 255, 255), 0.3), (S, S)))

        bg.paste(base, (0, 0), self.sphere_mask)
        return bg

    def render_bars(self):
        w, h, ss = BAR_W, BAR_H, 3
        strip = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(strip)
        amp = self.cur["bars"]
        speed = max(self.cur["speed"], 0.6)
        bw = 4.0
        for k in range(-13, 14):
            x = w / 2 + k * 10.4
            col = ramp((k + 13) / 26.0)
            if abs(k) <= 10:
                env = max(0.0, 1 - (abs(k) / 10.6) ** 1.6)
                wave = abs(math.sin(self.t * speed * 1.4 + k * 0.7) * math.sin(self.t * 1.9 + k * 0.45))
                hh = 2.2 + amp * env * (0.18 + 0.82 * wave)
                d.rounded_rectangle([(x - bw / 2) * ss, (h / 2 - hh) * ss, (x + bw / 2) * ss, (h / 2 + hh) * ss],
                                    radius=bw / 2 * ss, fill=ci(col) + (255,))
            else:
                r = 1.9
                d.ellipse([(x - r) * ss, (h / 2 - r) * ss, (x + r) * ss, (h / 2 + r) * ss],
                          fill=ci(lerp3((20, 24, 38), col, 0.35)) + (255,))
        strip = strip.resize((w, h), LANCZOS)
        glow = strip.filter(ImageFilter.GaussianBlur(3.5))
        a = glow.getchannel("A").point([int(v * 0.65) for v in range(256)])
        glow.putalpha(a)
        out = Image.alpha_composite(self.bar_bg, glow)
        out = Image.alpha_composite(out, strip)
        return out.convert("RGB")

    def render_mic(self, muted):
        M = MIC_M
        grad = self.mic_grad_muted if muted else self.mic_grad
        g = self.cur["glow"] * (0.8 + 0.2 * math.sin(self.t * 3.0))
        out = self.mic_bg.copy()
        halo = lut_scale(self.mic_ring.filter(ImageFilter.GaussianBlur(7)), 2.2 * g)
        out = ImageChops.screen(out, Image.composite(grad, Image.new("RGB", (M, M), (0, 0, 0)), halo))
        out.paste(Image.new("RGB", (M, M), (9, 12, 24)), (0, 0), self.mic_disc)
        out = Image.composite(grad, out, self.mic_ring)
        icon = self.mic_icon_muted if muted else self.mic_icon
        out = Image.composite(Image.new("RGB", (M, M), (252, 165, 165) if muted else (236, 240, 250)), out, icon)
        return out

    def render(self, state, dt, muted, want_bars=True):
        self._blend_state("muted" if muted else state, dt)
        return self.render_orb(), (self.render_bars() if want_bars else None), self.render_mic(muted)


# ---- window ----------------------------------------------------------------
PLACEHOLDER = "Type a command…"
DEFAULT_TITLE = "Hello, I'm ANA"


class App:
    def __init__(self):
        from PIL import ImageTk

        self.root = tk.Tk()
        self.root.title(ASSISTANT_NAME)
        self.root.overrideredirect(True)            # bina title bar ka floating card
        self.root.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{W}x{H}+{sw - W - 20}+{max(10, sh - H - 70)}")
        self.root.configure(bg=KEY_HEX)
        try:
            self.root.attributes("-transparentcolor", KEY_HEX)   # gol corners (Windows)
        except tk.TclError:
            pass
        self.topmost = tk.BooleanVar(value=True)

        self.r = Renderer()
        c = self.canvas = tk.Canvas(self.root, width=W, height=H, bg=KEY_HEX, highlightthickness=0)
        c.pack()

        self.p_static = ImageTk.PhotoImage(self.r.static)
        c.create_image(0, 0, image=self.p_static, anchor="nw")
        self.p_orb = ImageTk.PhotoImage(self.r.orb_bg)
        c.create_image(ORB_C[0] - ORB_S // 2, ORB_C[1] - ORB_S // 2, image=self.p_orb, anchor="nw")
        self.p_bars = ImageTk.PhotoImage(self.r.bar_bg.convert("RGB"))
        self.bars_item = c.create_image(BAR_C[0] - BAR_W // 2, BAR_C[1] - BAR_H // 2,
                                        image=self.p_bars, anchor="nw")
        self.p_mic = ImageTk.PhotoImage(self.r.mic_bg)
        c.create_image(MIC_C[0] - MIC_M // 2, MIC_C[1] - MIC_M // 2, image=self.p_mic, anchor="nw")

        # text items (sab images ke upar)
        c.create_text(83, 54, text="ANA AI", anchor="w", fill="#e8eaf2", font=("Segoe UI Semibold", 14))
        self.dot = c.create_oval(277, 50, 285, 58, fill="#22c55e", outline="")
        self.pill_txt = c.create_text(292, 54, text="Online", anchor="w", fill="#e5e7eb", font=("Segoe UI", 10))
        self.title_id = c.create_text(W / 2, 380, text=DEFAULT_TITLE, anchor="s", fill="#ffffff",
                                      width=320, justify="center", font=("Segoe UI Semibold", 20))
        self.sub_id = c.create_text(W / 2, 390, text="", anchor="n", fill="#8a90a2",
                                    width=300, justify="center", font=("Segoe UI", 12))
        self._shown = (None, None, None)

        # typed command ka text box (keyboard button se khulta hai)
        self.entry = tk.Entry(self.root, bg="#0d1120", fg="#6b7280", insertbackground="#e5e7eb",
                              relief="flat", font=("Segoe UI", 12), highlightthickness=1,
                              highlightbackground="#2a3150", highlightcolor="#38bdf8")
        self.entry.insert(0, PLACEHOLDER)
        self.entry.bind("<FocusIn>", self.entry_focus_in)
        self.entry.bind("<FocusOut>", self.entry_focus_out)
        self.entry.bind("<Button-1>", lambda e: self.entry.focus_force())
        self.entry.bind("<Return>", self.submit_text)
        self.entry_win = c.create_window(BAR_C[0], BAR_C[1], window=self.entry, width=252, height=36,
                                         state="hidden")

        self.menu = tk.Menu(self.root, tearoff=0, bg="#0e1220", fg="#e5e7eb", bd=0,
                            activebackground="#1d2540", activeforeground="#ffffff")
        self.menu.add_command(label="Mute / Unmute mic", command=self.toggle_mute)
        self.menu.add_checkbutton(label="Always on top", variable=self.topmost, command=self.apply_topmost)
        self.menu.add_separator()
        self.menu.add_command(label="Quit Ana", command=self.close)

        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<Motion>", self.on_hover)
        c.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self._dx = self._dy = 0
        self._drag = False

        self.state = "sleeping"
        self.heard = ""
        self.reply = ""
        self.convo_until = 0.0
        self.last = time.time()

        self.q = queue.Queue()
        self.voice = Voice(self.q)
        threading.Thread(target=self.voice.loop, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    # ---- clicks
    @staticmethod
    def _near(x, y, centre, r):
        return (x - centre[0]) ** 2 + (y - centre[1]) ** 2 <= r * r

    def on_press(self, e):
        self._drag = False
        if self._near(e.x, e.y, MIC_C, 36):
            self.toggle_mute()
        elif self._near(e.x, e.y, KBD_C, SIDE_R + 3):
            self.toggle_entry()
        elif self._near(e.x, e.y, GEAR_C, SIDE_R + 3):
            self.menu.tk_popup(e.x_root, e.y_root)
        else:
            self._drag = True
            self._dx, self._dy = e.x, e.y

    def on_drag(self, e):
        if self._drag:
            x = self.root.winfo_x() + e.x - self._dx
            y = self.root.winfo_y() + e.y - self._dy
            self.root.geometry(f"+{x}+{y}")

    def on_hover(self, e):
        hot = (self._near(e.x, e.y, MIC_C, 36) or self._near(e.x, e.y, KBD_C, SIDE_R + 3)
               or self._near(e.x, e.y, GEAR_C, SIDE_R + 3))
        self.canvas.config(cursor="hand2" if hot else "")

    def apply_topmost(self):
        self.root.attributes("-topmost", self.topmost.get())

    def close(self):
        self.voice.running = False
        self.root.destroy()

    # ---- text box
    def toggle_entry(self):
        showing = self.canvas.itemcget(self.entry_win, "state") == "normal"
        self.canvas.itemconfig(self.entry_win, state="hidden" if showing else "normal")
        self.canvas.itemconfig(self.bars_item, state="normal" if showing else "hidden")
        if not showing:
            self.entry.focus_force()

    def entry_focus_in(self, _e=None):
        if self.entry.get() == PLACEHOLDER:
            self.entry.delete(0, tk.END)
        self.entry.config(fg="#f3f4f6")

    def entry_focus_out(self, _e=None):
        if not self.entry.get().strip():
            self.entry.delete(0, tk.END)
            self.entry.insert(0, PLACEHOLDER)
            self.entry.config(fg="#6b7280")

    def submit_text(self, _e=None):
        text = self.entry.get().strip()
        if not text or text == PLACEHOLDER:
            return
        self.entry.delete(0, tk.END)
        threading.Thread(target=self.voice.process_typed, args=(text,), daemon=True).start()

    def toggle_mute(self):
        self.voice.muted = not self.voice.muted

    # ---- voice thread se aaye messages
    def poll(self):
        while True:
            try:
                kind, val = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                self.state = val
            elif kind == "heard":
                self.heard = val
                self.reply = ""
                self.convo_until = time.time() + 10
            elif kind == "reply":
                self.reply = val
                self.convo_until = time.time() + 10
            elif kind == "pulse":
                self.r.ring = 0.0
            elif kind == "quit":
                self.root.after(900, self.close)

    @staticmethod
    def _cut(s, n):
        return s if len(s) <= n else s[:n - 1] + "…"

    def texts(self):
        muted = self.voice.muted
        if muted:
            return "Mic is muted", "Tap the mic button to unmute", True
        convo = time.time() < self.convo_until and bool(self.heard)
        said = "“" + self._cut(self.heard, 42) + "”" if convo else DEFAULT_TITLE
        reply = self._cut(self.reply, 80)
        if self.state == "thinking":
            return said, "Thinking…", False
        if self.state == "speaking":
            return said, reply, False
        if convo:
            return said, reply, False
        if self.state == "listening":
            return "I'm listening…", "How can I help you today?", False
        return DEFAULT_TITLE, "Say “Hey Ana” to wake me up", False

    def update_texts(self):
        cur = self.texts()
        if cur == self._shown:
            return
        self._shown = cur
        title, sub, muted = cur
        self.canvas.itemconfig(self.title_id, text=title)
        self.canvas.itemconfig(self.sub_id, text=sub)
        self.canvas.itemconfig(self.dot, fill="#ef4444" if muted else "#22c55e")
        self.canvas.itemconfig(self.pill_txt, text="Muted" if muted else "Online")

    def tick(self):
        t0 = time.time()
        dt = min(0.1, t0 - self.last)
        self.last = t0
        self.poll()
        want_bars = self.canvas.itemcget(self.entry_win, "state") != "normal"
        orb, bars, mic = self.r.render(self.state, dt, self.voice.muted, want_bars)
        self.p_orb.paste(orb)
        if bars is not None:
            self.p_bars.paste(bars)
        self.p_mic.paste(mic)
        self.update_texts()
        spent = int((time.time() - t0) * 1000)
        self.root.after(max(1, 33 - spent), self.tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    pyautogui.FAILSAFE = True   # mouse ko corner mein le jao to automation ruk jayega
    App().run()
