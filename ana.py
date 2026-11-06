"""
ANA - Laptop Voice Assistant (floating Siri-style UI)

Run:  python ana.py      (ek baar: python ana.py --install-startup  -> laptop on hote hi apne aap chalegi)
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
import socket
import subprocess
import sys
import threading
import time
import traceback
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
    def __init__(self, ui_queue, quiet=False):
        self.q = ui_queue
        self.quiet = quiet          # startup par 'ready hai' na bole
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
        if not self.quiet:
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
# Siri jaisa chhota gol orb. Pillow se draw hota hai, tkinter sirf dikhata hai.
LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
BILINEAR = getattr(Image, "Resampling", Image).BILINEAR

HIDE_WHEN_SLEEPING = True       # True: so rahi ho to orb chhup jata hai (tray icon se control)
KEY = (1, 1, 1)                 # window ka transparent rang
KEY_HEX = "#010101"
W, H = 340, 240
ORB_R, ORB_S = 36, 150          # orb ka radius aur uska region
ORB_C = (W // 2, H - ORB_S // 2 - 6)
BUBBLE_BOTTOM = 112             # text bubble ka neeche ka kinara (orb ke upar)
BUBBLE_FILL, BUBBLE_EDGE = "#0c0f1d", "#2b3354"

C_CYAN = (34, 211, 238)
C_SKY = (56, 189, 248)
C_BLUE = (99, 102, 241)
C_PURPLE = (168, 85, 247)
C_MAGENTA = (217, 70, 239)
C_PINK = (244, 63, 140)

# state ke hisaab se petal-groups ke rang, roshni, speed, size
PAL = {
    "sleeping":  dict(c=(C_CYAN, C_PINK, C_PURPLE), inten=0.55, pulse=0.03, speed=0.35, scale=0.72),
    "listening": dict(c=(C_CYAN, C_PINK, C_PURPLE), inten=0.95, pulse=0.10, speed=1.00, scale=1.00),
    "thinking":  dict(c=(C_PURPLE, C_BLUE, C_CYAN), inten=0.90, pulse=0.06, speed=2.60, scale=1.00),
    "speaking":  dict(c=(C_PINK, C_CYAN, C_PURPLE), inten=1.00, pulse=0.28, speed=1.50, scale=1.00),
    "muted":     dict(c=((107, 114, 128), (75, 85, 99), (55, 65, 81)), inten=0.35, pulse=0.0,
                      speed=0.15, scale=0.72),
}
OMEGA = (0.9, -0.7, 0.45)       # har group kitni tezi se ghoomta hai


def lerp3(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def ci(c):
    return tuple(max(0, min(255, int(round(v)))) for v in c)


def corner_gradient(size, tl, tr, br, bl):
    """4 corners ke rang se smooth gradient."""
    w, h = size
    hm = Image.linear_gradient("L").rotate(90).resize((w, h))     # left kaala -> right safed
    vm = Image.linear_gradient("L").resize((w, h))                # upar kaala -> neeche safed
    top = Image.composite(Image.new("RGB", (w, h), tr), Image.new("RGB", (w, h), tl), hm)
    bot = Image.composite(Image.new("RGB", (w, h), br), Image.new("RGB", (w, h), bl), hm)
    return Image.composite(bot, top, vm)


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


class Renderer:
    def __init__(self):
        S, R = ORB_S, ORB_R
        c = S / 2
        self.key = Image.new("RGB", (S, S), KEY)
        self.black = Image.new("RGB", (S, S), (0, 0, 0))
        self.sphere_mask = disc_mask((S, S), c, c, R)

        base_c = Image.new("RGB", (S, S), (2, 4, 16))
        base_e = Image.new("RGB", (S, S), (6, 22, 54))
        self.sphere_base = Image.composite(base_e, base_c, radial_L(R, S, power=1.7))
        og = corner_gradient((S, S), C_SKY, C_MAGENTA, C_CYAN, C_PINK)
        rim_soft = Image.composite(og, self.black, lut_scale(radial_L(R, S, power=6.5), 0.55))
        ring_m = ImageChops.subtract(disc_mask((S, S), c, c, R), disc_mask((S, S), c, c, R - 1.7))
        rim_ring = Image.composite(og, self.black, ring_m)
        hl = Image.new("L", (S, S), 0)
        ImageDraw.Draw(hl).ellipse([c - 0.72 * R, c - 0.82 * R, c - 0.05 * R, c - 0.30 * R], fill=42)
        hl = hl.filter(ImageFilter.GaussianBlur(3.5))
        self.rim = ImageChops.screen(ImageChops.screen(rim_soft, rim_ring),
                                     Image.composite(Image.new("RGB", (S, S), (200, 230, 255)), self.black, hl))
        self.center_mask = radial_L(int(R * 0.52), S, power=1.8, invert=True)

        th = PAL["sleeping"]
        self.cur = dict(c=[tuple(x) for x in th["c"]], inten=th["inten"], pulse=th["pulse"],
                        speed=th["speed"], scale=th["scale"])
        self.phase = [0.0, 2.0, 4.0]
        self.t = 0.0
        self.ring = None            # jaagne par phailne wali ring (0..1)

    def _blend_state(self, state, dt):
        th = PAL.get(state, PAL["sleeping"])
        k = 1 - math.exp(-dt * 7.0)
        self.cur["c"] = [lerp3(a, b, k) for a, b in zip(self.cur["c"], th["c"])]
        for key in ("inten", "pulse", "speed", "scale"):
            self.cur[key] += (th[key] - self.cur[key]) * k
        self.t += dt
        for i in range(3):
            self.phase[i] += OMEGA[i] * self.cur["speed"] * dt
        if self.ring is not None:
            self.ring += dt * 1.2
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
            m = lut_scale(m.filter(ImageFilter.GaussianBlur(1.3)), al * cur["inten"])
            base = ImageChops.screen(base, tint(m, cur["c"][gi], (S, S)))

        flick = 0.88 + 0.12 * math.sin(self.t * 2.3)
        cg = lut_scale(self.center_mask, min(1.0, (0.25 + 0.75 * cur["inten"] ** 1.4) * flick))
        base = ImageChops.screen(base, tint(cg, (235, 250, 255), (S, S)))
        base = ImageChops.screen(base, Image.blend(self.black, self.rim, 0.40 + 0.60 * cur["inten"]))

        bg = self.key.copy()
        if self.ring is not None:                       # jaagne ki ring
            p = self.ring
            rm = Image.new("L", (S, S), 0)
            rr = R + 4 + p * (S / 2 - R - 8)
            ImageDraw.Draw(rm).ellipse([c - rr, c - rr, c + rr, c + rr], outline=255, width=2)
            rm = lut_scale(rm.filter(ImageFilter.GaussianBlur(0.8)), (1 - p) * 1.1)
            bg = ImageChops.screen(bg, tint(rm, lerp3(cur["c"][0], (255, 255, 255), 0.3), (S, S)))
        bg.paste(base, (0, 0), self.sphere_mask)
        return bg

    def render(self, state, dt, muted):
        self._blend_state("muted" if muted else state, dt)
        orb = self.render_orb()
        sc = self.cur["scale"]
        if abs(sc - 1) > 0.01:                          # so rahi ho to chhota orb
            n = max(8, int(ORB_S * sc))
            small = orb.resize((n, n), LANCZOS)
            out = self.key.copy()
            off = (ORB_S - n) // 2
            out.paste(small, (off, off))
            return out
        return orb

    def tray_icon(self):
        for _ in range(25):
            self._blend_state("listening", 0.05)
        orb = self.render_orb()
        icon = Image.new("RGBA", (ORB_S, ORB_S), (0, 0, 0, 0))
        icon.paste(orb, (0, 0), self.sphere_mask)
        m = ORB_S // 2 - ORB_R - 1
        return icon.crop((m, m, ORB_S - m, ORB_S - m)).resize((64, 64), LANCZOS)


# ---- background mein chalna: startup, single instance, tray ---------------
STARTUP_FILE = "ana_assistant.vbs"
LOCK_PORT = 47653


def script_path():
    return os.path.abspath(__file__)


def pythonw_path():
    exe = sys.executable
    if OS == "Windows":
        pw = os.path.join(os.path.dirname(exe), "pythonw.exe")      # bina console window ke
        if os.path.exists(pw):
            return pw
    return exe


def startup_path():
    base = os.environ.get("APPDATA", "")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", STARTUP_FILE)


def is_startup_enabled():
    return OS == "Windows" and os.path.exists(startup_path())


def launch_detached():
    flags = 0x00000008 | 0x00000200 if OS == "Windows" else 0     # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([pythonw_path(), script_path(), "--quiet"], cwd=os.path.dirname(script_path()),
                     creationflags=flags, close_fds=True)


def install_startup():
    if OS != "Windows":
        return False
    pw, sp = pythonw_path(), script_path()
    vbs = ('Set s = CreateObject("WScript.Shell")\n'
           f's.CurrentDirectory = "{os.path.dirname(sp)}"\n'
           f's.Run """{pw}"" ""{sp}"" --quiet", 0, False\n')
    os.makedirs(os.path.dirname(startup_path()), exist_ok=True)
    with open(startup_path(), "w", encoding="utf-8") as f:
        f.write(vbs)
    return True


def remove_startup():
    try:
        os.remove(startup_path())
    except OSError:
        pass


def acquire_lock():
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        return s
    except OSError:
        return None


def start_tray(app):
    """System tray icon (pystray ho to). True return kare to tray chal raha hai."""
    try:
        import pystray
    except Exception:
        return False
    try:
        put = app.q.put
        items = [
            pystray.MenuItem("Always show orb", lambda: put(("cmd", "pin")), checked=lambda i: app.pinned,
                             default=True),
            pystray.MenuItem("Mute mic", lambda: put(("cmd", "mute")), checked=lambda i: app.voice.muted),
        ]
        if OS == "Windows":
            items.append(pystray.MenuItem("Start with Windows", lambda: put(("cmd", "startup")),
                                          checked=lambda i: is_startup_enabled()))
        items.append(pystray.MenuItem("Quit Ana", lambda: put(("cmd", "quit"))))
        icon = pystray.Icon("Ana", app.r.tray_icon(), "Ana", pystray.Menu(*items))
        icon.run_detached()
        app.tray = icon
        return True
    except Exception as e:
        print("Tray start nahi hua:", e)
        return False


# ---- window ----------------------------------------------------------------
PLACEHOLDER = "Type a command…"


class App:
    def __init__(self, quiet=False):
        from PIL import ImageTk

        self.root = tk.Tk()
        self.root.title(ASSISTANT_NAME)
        self.root.overrideredirect(True)            # bina title bar ke
        self.root.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{W}x{H}+{sw - W - 24}+{max(10, sh - H - 70)}")
        self.root.configure(bg=KEY_HEX)
        try:
            self.root.attributes("-transparentcolor", KEY_HEX)   # orb ke bahar sab transparent (Windows)
        except tk.TclError:
            pass
        self.topmost = tk.BooleanVar(value=True)

        self.r = Renderer()
        c = self.canvas = tk.Canvas(self.root, width=W, height=H, bg=KEY_HEX, highlightthickness=0)
        c.pack()
        self.p_orb = ImageTk.PhotoImage(self.r.key)
        c.create_image(ORB_C[0] - ORB_S // 2, ORB_C[1] - ORB_S // 2, image=self.p_orb, anchor="nw")

        # caption bubble (jo bola + Ana ka jawab)
        self.bubble = c.create_polygon(0, 0, 0, 0, 0, 0, smooth=True, fill=BUBBLE_FILL,
                                       outline=BUBBLE_EDGE, width=1, state="hidden")
        self.heard_id = c.create_text(W / 2, 90, text="", anchor="s", fill="#8a90a2", width=300,
                                      justify="center", font=("Segoe UI", 10, "italic"), state="hidden")
        self.reply_id = c.create_text(W / 2, 100, text="", anchor="s", fill="#f3f4f6", width=300,
                                      justify="center", font=("Segoe UI", 12), state="hidden")
        self._bubble_shown = None

        # typed command ka text box
        self.entry = tk.Entry(self.root, bg="#0d1120", fg="#6b7280", insertbackground="#e5e7eb",
                              relief="flat", font=("Segoe UI", 12), highlightthickness=1,
                              highlightbackground="#2a3150", highlightcolor="#38bdf8")
        self.entry.insert(0, PLACEHOLDER)
        self.entry.bind("<FocusIn>", self.entry_focus_in)
        self.entry.bind("<FocusOut>", self.entry_focus_out)
        self.entry.bind("<Button-1>", lambda e: self.entry.focus_force())
        self.entry.bind("<Return>", self.submit_text)
        self.entry.bind("<Escape>", lambda e: self.toggle_entry())
        self.entry_win = c.create_window(W / 2, 96, window=self.entry, width=290, height=36, state="hidden")

        self.menu = tk.Menu(self.root, tearoff=0, bg="#0e1220", fg="#e5e7eb", bd=0,
                            activebackground="#1d2540", activeforeground="#ffffff")
        self.menu.add_command(label="Type a command", command=self.toggle_entry)
        self.menu.add_command(label="Mute / Unmute mic", command=self.toggle_mute)
        self.menu.add_checkbutton(label="Always on top", variable=self.topmost, command=self.apply_topmost)
        if OS == "Windows":
            self.menu.add_command(label="Start with Windows (on/off)", command=self.toggle_startup)
        self.menu.add_separator()
        self.menu.add_command(label="Quit Ana", command=self.close)

        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self._press = None

        self.state = "sleeping"
        self.heard = ""
        self.reply = ""
        self.convo_until = 0.0
        self.pinned = False
        self.can_hide = False        # tray chalu hone par True hota hai
        self.hidden = False
        self.tray = None
        self.last_wanted = time.time()
        self.last = time.time()

        self.q = queue.Queue()
        self.voice = Voice(self.q, quiet=quiet)
        threading.Thread(target=self.voice.loop, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    # ---- mouse: click = jagao, drag = hilao
    @staticmethod
    def _near(x, y, centre, r):
        return (x - centre[0]) ** 2 + (y - centre[1]) ** 2 <= r * r

    def on_press(self, e):
        self._press = (e.x, e.y, self.root.winfo_x(), self.root.winfo_y(), e.x_root, e.y_root, False)

    def on_drag(self, e):
        if not self._press:
            return
        px, py, wx, wy, rx, ry, _ = self._press
        if abs(e.x_root - rx) + abs(e.y_root - ry) > 4:
            self._press = (px, py, wx, wy, rx, ry, True)
        if self._press[6]:
            self.root.geometry(f"+{wx + e.x_root - rx}+{wy + e.y_root - ry}")

    def on_release(self, e):
        if self._press and not self._press[6] and self._near(e.x, e.y, ORB_C, ORB_R + 10):
            self.tap()
        self._press = None

    def tap(self):
        if self.voice.muted:
            self.toggle_mute()
        else:
            threading.Thread(target=self.voice.activate, daemon=True).start()

    def apply_topmost(self):
        self.root.attributes("-topmost", self.topmost.get())

    def toggle_mute(self):
        self.voice.muted = not self.voice.muted

    def toggle_startup(self):
        if is_startup_enabled():
            remove_startup()
            self.show_note("Startup band: ab Ana apne aap nahi chalegi")
        else:
            install_startup()
            self.show_note("Ab Ana laptop on hote hi apne aap chalegi")

    def show_note(self, text):
        self.reply = text
        self.heard = ""
        self.convo_until = time.time() + 6

    def close(self):
        self.voice.running = False
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.destroy()

    # ---- text box
    def toggle_entry(self):
        showing = self.canvas.itemcget(self.entry_win, "state") == "normal"
        self.canvas.itemconfig(self.entry_win, state="hidden" if showing else "normal")
        if not showing:
            self.show()
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
        self.canvas.itemconfig(self.entry_win, state="hidden")
        threading.Thread(target=self.voice.process_typed, args=(text,), daemon=True).start()

    # ---- voice thread / tray se aaye messages
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
            elif kind == "cmd":
                if val == "pin":
                    self.pinned = not self.pinned
                elif val == "mute":
                    self.toggle_mute()
                elif val == "startup":
                    self.toggle_startup()
                elif val == "quit":
                    self.close()
                    return
            elif kind == "quit":
                self.root.after(900, self.close)

    # ---- bubble
    @staticmethod
    def _cut(s, n):
        return s if len(s) <= n else s[:n - 1] + "…"

    def bubble_texts(self):
        if self.voice.muted or self.canvas.itemcget(self.entry_win, "state") == "normal":
            return None
        convo = time.time() < self.convo_until
        heard = "“" + self._cut(self.heard, 44) + "”" if (convo and self.heard) else ""
        reply = self._cut(self.reply, 80)
        if self.state == "thinking":
            return heard, "Thinking…"
        if convo or self.state == "speaking":
            if heard or reply:
                return heard, reply or "…"
        if self.state == "listening":
            return "", "Listening…"
        return None

    def update_bubble(self):
        texts = self.bubble_texts()
        if texts == self._bubble_shown:
            return
        self._bubble_shown = texts
        c = self.canvas
        if texts is None:
            for i in (self.bubble, self.heard_id, self.reply_id):
                c.itemconfig(i, state="hidden")
            return
        heard, reply = texts
        c.itemconfig(self.reply_id, text=reply, state="normal")
        c.coords(self.reply_id, W / 2, 100)
        bb = c.bbox(self.reply_id) or (W / 2 - 40, 80, W / 2 + 40, 100)
        left, top, right, bottom = bb
        if heard:
            c.itemconfig(self.heard_id, text=heard, state="normal")
            c.coords(self.heard_id, W / 2, top - 3)
            b2 = c.bbox(self.heard_id) or (left, top - 16, right, top - 3)
            left, top, right = min(left, b2[0]), b2[1], max(right, b2[2])
        else:
            c.itemconfig(self.heard_id, state="hidden")
        pad, r = 12, 16
        x1, y1, x2, y2 = left - pad, top - pad + 2, right + pad, bottom + pad - 2
        c.coords(self.bubble, x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                 x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1)
        c.itemconfig(self.bubble, state="normal")
        c.tag_raise(self.heard_id)
        c.tag_raise(self.reply_id)

    # ---- dikhana / chhupana
    def wants_visible(self):
        if not self.can_hide or self.pinned or self.voice.muted:
            return True
        if self.state != "sleeping" or time.time() < self.convo_until:
            return True
        return self.canvas.itemcget(self.entry_win, "state") == "normal"

    def show(self):
        if self.hidden:
            self.hidden = False
            self.root.deiconify()
            self.root.attributes("-topmost", self.topmost.get())
            self.root.lift()
        self.last_wanted = time.time()

    def hide(self):
        self.hidden = True
        self.root.withdraw()

    def tick(self):
        t0 = time.time()
        delay = 33
        try:
            dt = min(0.1, t0 - self.last)
            self.last = t0
            self.poll()
            if self.wants_visible():
                self.show()
            elif not self.hidden and t0 - self.last_wanted > 1.6:
                self.hide()
            if self.hidden:
                delay = 120
            else:
                self.p_orb.paste(self.r.render(self.state, dt, self.voice.muted))
                self.update_bubble()
                delay = max(1, 33 - int((time.time() - t0) * 1000))
        except tk.TclError:
            return                                   # window band ho chuki hai
        except Exception:
            traceback.print_exc()
        self.root.after(delay, self.tick)

    def run(self):
        self.root.mainloop()


def main():
    if "--install-startup" in sys.argv:
        if install_startup():
            launch_detached()
            print("Ho gaya! Ana abhi background mein chalu ho gayi hai,")
            print("aur ab har baar laptop on hote hi apne aap chalu hogi.")
            print("Band karne ke liye: tray icon -> Quit Ana")
        else:
            print("Ye option sirf Windows pe hai.")
        return
    if "--remove-startup" in sys.argv:
        remove_startup()
        print("Startup hata diya. Ab Ana apne aap nahi chalegi.")
        return

    if sys.stdout is None or sys.stderr is None:      # pythonw: console nahi, to log file
        log = open(os.path.join(os.path.expanduser("~"), "ana.log"), "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log

    lock = acquire_lock()
    if lock is None:
        print("Ana pehle se chal rahi hai.")
        return

    pyautogui.FAILSAFE = True   # mouse ko corner mein le jao to automation ruk jayega
    app = App(quiet="--quiet" in sys.argv)
    app.can_hide = HIDE_WHEN_SLEEPING and start_tray(app)
    app.run()
    lock.close()


if __name__ == "__main__":
    main()
