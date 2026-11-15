"""
ANA - Laptop Voice Assistant (floating Siri-style UI)

Run:  python ana.py      (ek baar: python ana.py --install-startup  -> laptop on hote hi apne aap chalegi)
Jagane ke liye bolo:  "Hey Anna"  (ya sirf "Anna")
Ya neeche text box mein command type karo.
"""

import array
import datetime
import difflib
import json
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

ASSISTANT_NAME = "Anna"
# Mic "ana" ko aksar alag sunta hai (anna, aana...). Bina bulaye chalne lage
# to is list se extra naam hata do.
WAKE_WORDS = ["ana", "anna", "aana", "anaa", "anah", "ena", "enna", "ann", "anne", "annie",
              "hana", "hanna", "hannah", "heyana", "heyanna", "heyhanna"]
# in ke alawa milte-julte lafz (hannah, anah...) bhi pakad liye jaate hain. Ye lafz kabhi wake nahi karte:
NOT_WAKE = {"and", "an", "any", "anal", "can", "man", "hand", "nana", "banana", "gana", "han"}
MIC_INDEX = None            # galat mic chuna ho to: python ana.py --test-mic se number dekho aur yahan likho
DEBUG_SHOW_HEARD = True     # True: so rahi ho tab bhi jo suna wo dikhata hai. Sab theek chale to False kar do
LANGUAGE = "en-IN"          # Hinglish ke liye best chalta hai
FOLLOWUP_SECONDS = 15       # wake ke baad itni der tak bina "Hey Anna" bole sunta rahega
OS = platform.system()      # Windows / Darwin / Linux

# --pick-mic se chuna hua mic yahan save hota hai (har baar file edit nahi karni padegi)
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".anna_config.json")


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)


if load_config().get("mic_index") is not None:
    MIC_INDEX = load_config()["mic_index"]

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
def is_wake_word(w):
    """Exact list ya 'anna' se milta-julta lafz (Google mic ke bigde spelling ke liye)."""
    if w in WAKE_WORDS:
        return True
    if w in NOT_WAKE or len(w) < 3:
        return False
    return difflib.SequenceMatcher(None, w, "anna").ratio() >= 0.74


def split_wake_word(text):
    """Wake word mila to (True, uske baad ka command), warna (False, text)."""
    words = re.findall(r"[\w']+", text.lower())
    for i, w in enumerate(words):
        if is_wake_word(w):
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
        return "Theek hai, jab zaroorat ho to Hey Anna bolna"

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
                # Anna ke liye female awaaz chuno agar available ho (Windows pe Zira/Heera)
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
    def clamp_threshold(self):
        """Sensitivity apne aap bahut oonchi na ho jaaye, warna awaaz sunayi hi nahi deti."""
        self.rec.energy_threshold = max(120, min(self.rec.energy_threshold, 900))

    def listen_once(self, mic, timeout, limit):
        self.clamp_threshold()
        try:
            audio = self.rec.listen(mic, timeout=timeout, phrase_time_limit=limit)
        except sr.WaitTimeoutError:
            return None
        if self.is_awake():
            self.q.put(("state", "thinking"))
        try:
            return self.rec.recognize_google(audio, language=LANGUAGE).lower()
        except sr.UnknownValueError:
            print("[mic] awaaz aayi par samajh nahi aayi", flush=True)
            if DEBUG_SHOW_HEARD:
                self.q.put(("debug", "(awaaz aayi par samajh nahi aayi)"))
            return None
        except sr.RequestError as e:
            print("[mic] Google speech service nahi mili:", e, flush=True)
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
            mic = sr.Microphone(device_index=MIC_INDEX)
        except Exception as e:
            print(f"[mic] mic {MIC_INDEX} nahi khula ({e}), default try kar rahi hoon", flush=True)
            try:
                mic = sr.Microphone()
            except Exception as e2:
                print("[mic] Mic nahi mila:", e2, flush=True)
                self.q.put(("reply", "Mic nahi mila. python ana.py --pick-mic chalao"))
                return
        with mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)
        self.clamp_threshold()
        print(f"[mic] chalu. energy_threshold={self.rec.energy_threshold:.0f}", flush=True)
        if not self.quiet:
            self.speak(f"{ASSISTANT_NAME} ready hai. Hey Anna bolkar jagao")

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
            print(f"[heard] {text!r}  wake={woke}  awake={self.is_awake()}", flush=True)
            if not woke and not self.is_awake():
                if DEBUG_SHOW_HEARD:
                    self.q.put(("debug", text))
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
ORB_R, ORB_S = 38, 150          # orb ka radius aur uska region
ORB_C = (W // 2, H - ORB_S // 2 - 6)
BUBBLE_BOTTOM = 112             # text bubble ka neeche ka kinara (orb ke upar)
BUBBLE_FILL, BUBBLE_EDGE = "#0c0f1d", "#2b3354"

C_CYAN = (34, 211, 238)
C_SKY = (56, 189, 248)
C_BLUE = (99, 102, 241)
C_PURPLE = (168, 85, 247)
C_MAGENTA = (217, 70, 239)
C_PINK = (244, 63, 140)

# state ke hisaab se rim ki roshni, rang, ghoomna aur size
BLUE = (110, 170, 255)
WARM = (255, 178, 100)
PAL = {
    "sleeping":  dict(top=0.55, bot=0.35, glow=0.35, inner=0.00, spin=0,   sway=0,  scale=0.72, ctop=BLUE, cbot=WARM),
    "listening": dict(top=1.00, bot=0.65, glow=0.80, inner=0.22, spin=0,   sway=0,  scale=1.00, ctop=BLUE, cbot=WARM),
    "thinking":  dict(top=1.00, bot=0.50, glow=0.80, inner=0.26, spin=230, sway=0,  scale=1.00, ctop=(150, 130, 255), cbot=WARM),
    "speaking":  dict(top=1.00, bot=0.75, glow=1.00, inner=0.50, spin=0,   sway=14, scale=1.00, ctop=(90, 200, 255), cbot=WARM),
    "muted":     dict(top=0.30, bot=0.15, glow=0.10, inner=0.00, spin=0,   sway=0,  scale=0.72, ctop=(120, 126, 140), cbot=(110, 112, 120)),
}


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


def cut(img, k=1.0, off=7):
    """Mask ki bahut halki tail ko 0 kar do (warna transparent window pe kaala daag dikhta hai)."""
    return img.point([max(0, min(255, int((v - off) * k))) for v in range(256)])


def tint(mask, color, size):
    """L mask ko rang ke saath RGB layer banao (mask ke bahar kaala)."""
    return Image.composite(Image.new("RGB", size, ci(color)), Image.new("RGB", size, (0, 0, 0)), mask)


class Renderer:
    """Dark glass orb: kaala chamakdaar gola, upar neeli glow wali rim, neeche halki sunehri kinari."""

    def __init__(self):
        S, R = ORB_S, ORB_R
        c = S / 2
        self.key = Image.new("RGB", (S, S), KEY)
        self.sphere_mask = disc_mask((S, S), c, c, R)

        # gola: beech gehra kaala, kinare par halka neela (glass jaisa)
        body = Image.composite(Image.new("RGB", (S, S), (11, 18, 40)),
                               Image.new("RGB", (S, S), (3, 5, 13)), radial_L(R, S, power=1.7))
        sheen = Image.new("L", (S, S), 0)
        ImageDraw.Draw(sheen).ellipse([c - 0.80 * R, c - 0.95 * R, c + 0.55 * R, c - 0.05 * R], fill=34)
        sheen = sheen.filter(ImageFilter.GaussianBlur(7))
        self.body = ImageChops.screen(body, tint(sheen, (70, 110, 190), (S, S)))

        # patli double rim (image jaisi do line wali kinari)
        outer = ImageChops.subtract(disc_mask((S, S), c, c, R), disc_mask((S, S), c, c, R - 1.3))
        inner = ImageChops.subtract(disc_mask((S, S), c, c, R - 3.4), disc_mask((S, S), c, c, R - 4.3))
        self.ring_out = lut_scale(outer, 0.55)
        self.ring_in = lut_scale(inner, 0.28)

        # upar ka crescent (neeli roshni) aur uska glow jo bahar tak failta hai
        top = ImageChops.subtract(disc_mask((S, S), c, c, R + 0.6), disc_mask((S, S), c, c + 4.2, R + 0.6))
        self.top = top.filter(ImageFilter.GaussianBlur(1.3))
        self.top_glow = cut(lut_scale(top.filter(ImageFilter.GaussianBlur(2.4)), 1.6), 1.2, 22)
        # neeche ki patli sunehri kinari
        bot = ImageChops.subtract(disc_mask((S, S), c, c, R + 0.6), disc_mask((S, S), c, c - 2.6, R + 0.6))
        self.bot = bot.filter(ImageFilter.GaussianBlur(0.8))
        self.bot_glow = cut(lut_scale(bot.filter(ImageFilter.GaussianBlur(1.8)), 0.9), 1.2, 22)
        # andar ka glow
        self.core = radial_L(int(R * 0.95), S, power=1.3, invert=True)

        th = PAL["sleeping"]
        self.cur = dict(top=th["top"], bot=th["bot"], glow=th["glow"], inner=th["inner"],
                        spin=th["spin"], sway=th["sway"], scale=th["scale"],
                        ctop=th["ctop"], cbot=th["cbot"])
        self.angle = 0.0
        self.t = 0.0
        self.ring = None            # jaagne par phailne wali ring (0..1)

    def _blend_state(self, state, dt):
        th = PAL.get(state, PAL["sleeping"])
        k = 1 - math.exp(-dt * 7.0)
        for key in ("top", "bot", "glow", "inner", "spin", "sway", "scale"):
            self.cur[key] += (th[key] - self.cur[key]) * k
        self.cur["ctop"] = lerp3(self.cur["ctop"], th["ctop"], k)
        self.cur["cbot"] = lerp3(self.cur["cbot"], th["cbot"], k)
        self.t += dt
        if th["spin"] > 0:
            self.angle = (self.angle + self.cur["spin"] * dt) % 360
        else:                                           # ghoomna band: shortest raste se upar wapas
            err = ((self.angle + 180) % 360) - 180
            self.angle = err * math.exp(-dt * 7.0)
        if self.ring is not None:
            self.ring += dt * 1.2
            if self.ring >= 1:
                self.ring = None

    def render_orb(self):
        S, R = ORB_S, ORB_R
        c = S / 2
        cur = self.cur
        wave = 0.5 + 0.5 * math.sin(self.t * 6.0)            # bolte waqt dhadkan
        breath = 0.5 + 0.5 * math.sin(self.t * 1.6)           # halki saans
        spin_pos = self.angle + cur["sway"] * math.sin(self.t * 2.4)
        k_top = cur["top"] * (0.85 + 0.15 * breath)

        # 1) gola + andar ka glow
        base = self.body.copy()
        inner_k = cur["inner"] * (0.55 + 0.45 * wave) if cur["sway"] > 5 else cur["inner"] * (0.8 + 0.2 * breath)
        base = ImageChops.screen(base, tint(lut_scale(self.core, inner_k), cur["ctop"], (S, S)))
        base = ImageChops.screen(base, tint(self.ring_in, cur["ctop"], (S, S)))

        bg = self.key.copy()
        # 2) gola
        bg.paste(base, (0, 0), self.sphere_mask)

        # 3) rim: upar neeli (ghoomti hui), neeche sunehri
        top, top_glow = self.top, self.top_glow
        if abs(spin_pos) > 0.5:
            top = top.rotate(-spin_pos, resample=Image.BICUBIC)
            top_glow = top_glow.rotate(-spin_pos, resample=Image.BICUBIC)
        bg = ImageChops.screen(bg, tint(lut_scale(top_glow, 0.85 * k_top), cur["ctop"], (S, S)))
        bg = ImageChops.screen(bg, tint(lut_scale(top, 1.6 * k_top), lerp3(cur["ctop"], (255, 255, 255), 0.35),
                                        (S, S)))
        bg = ImageChops.screen(bg, tint(lut_scale(self.bot_glow, 0.6 * cur["bot"]), cur["cbot"], (S, S)))
        bg = ImageChops.screen(bg, tint(lut_scale(self.bot, 1.3 * cur["bot"]), cur["cbot"], (S, S)))
        bg = ImageChops.screen(bg, tint(lut_scale(self.ring_out, 0.9 + 0.5 * cur["glow"]),
                                        lerp3(cur["ctop"], cur["cbot"], 0.35), (S, S)))

        # 4) jaagne ki ring
        if self.ring is not None:
            p = self.ring
            rm = Image.new("L", (S, S), 0)
            rr = R + 4 + p * (S / 2 - R - 8)
            ImageDraw.Draw(rm).ellipse([c - rr, c - rr, c + rr, c + rr], outline=255, width=2)
            rm = lut_scale(rm.filter(ImageFilter.GaussianBlur(0.8)), (1 - p) * 1.1)
            bg = ImageChops.screen(bg, tint(rm, lerp3(cur["ctop"], (255, 255, 255), 0.3), (S, S)))
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
        self.cur.update(scale=1.0)
        self._blend_state("listening", 0.0)
        for _ in range(25):
            self._blend_state("listening", 0.05)
        orb = self.render_orb()
        icon = Image.new("RGBA", (ORB_S, ORB_S), (0, 0, 0, 0))
        icon.paste(orb, (0, 0), self.sphere_mask)
        m = ORB_S // 2 - ORB_R - 3
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
        items.append(pystray.MenuItem("Quit Anna", lambda: put(("cmd", "quit"))))
        icon = pystray.Icon("Anna", app.r.tray_icon(), ASSISTANT_NAME, pystray.Menu(*items))
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

        # caption bubble (jo bola + Anna ka jawab)
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
        self.menu.add_command(label="Quit Anna", command=self.close)

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
            self.show_note("Startup band: ab Anna apne aap nahi chalegi")
        else:
            install_startup()
            self.show_note("Ab Anna laptop on hote hi apne aap chalegi")

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
            elif kind == "debug":
                self.heard = val
                self.reply = "Wake word nahi mila. “Hey Anna” bolo"
                self.convo_until = time.time() + 3
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


def rms_level(data):
    a = array.array("h")
    a.frombytes(data[: len(data) // 2 * 2])
    if not a:
        return 0.0
    return math.sqrt(sum(x * x for x in a) / len(a))


def pick_mic():
    """python ana.py --pick-mic : har mic ko sunke sabse sahi wala dhoondho aur save karo."""
    import pyaudio
    pa = pyaudio.PyAudio()
    cands = []
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            cands.append((i, info["name"], int(info["defaultSampleRate"])))
    if not cands:
        print("Koi mic mila hi nahi! Windows Settings -> System -> Sound -> Input mein mic check karo.")
        return
    print(f"{len(cands)} mic mile. Ab har mic 2 second sunega.")
    print(">>> Is poore time LAGATAR zor se bolte raho, jaise: 'one two three four five' <<<\n")
    time.sleep(2)
    results = []
    for i, name, rate in cands:
        print(f"[{i:>2}] {name[:44]:<44}", end=" ", flush=True)
        try:
            st = pa.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True,
                         input_device_index=i, frames_per_buffer=1024)
            peak, end = 0.0, time.time() + 2
            while time.time() < end:
                peak = max(peak, rms_level(st.read(1024, exception_on_overflow=False)))
            st.close()
        except Exception:
            print("-> khul nahi paya")
            continue
        print("#" * min(36, int(peak / 100)) + f"  ({int(peak)})")
        results.append((peak, i, name))
    pa.terminate()
    good = [r for r in results if not any(k in r[2].lower() for k in ("stereo mix", "loopback", "what u hear"))]
    if not good or max(good)[0] < 150:
        print("\nKoi bhi mic awaaz nahi pakad paya. Ye karo:")
        print("1) Windows Settings -> Privacy & security -> Microphone -> 'Let desktop apps access your microphone' ON")
        print("2) Settings -> System -> Sound -> Input mein sahi mic chuno aur uski Volume badhao")
        print("3) Phir ye command dobara chalao.")
        return
    peak, best, name = max(good)
    print(f"\nSabse zyada awaaz: [{best}] {name}")
    ans = input("Isko Anna ke liye save karun? (Enter = haan, ya koi aur number likho, n = nahi): ").strip().lower()
    if ans in ("n", "no"):
        return
    idx = int(ans) if ans.isdigit() else best
    cfg = load_config()
    cfg["mic_index"] = idx
    save_config(cfg)
    print(f"Save ho gaya: mic [{idx}]. Ab Anna band karke dobara chalao (ya python ana.py --install-startup).")


def test_mic():
    """python ana.py --test-mic : mic aur wake word ki jaanch."""
    print("Microphones:")
    for i, n in enumerate(sr.Microphone.list_microphone_names()):
        print(f"  [{i}] {n}")
    rec = sr.Recognizer()
    mic = sr.Microphone(device_index=MIC_INDEX)
    print("\nEk second chup raho (noise check)...")
    with mic as src:
        rec.adjust_for_ambient_noise(src, duration=1)
    print(f"Energy threshold: {rec.energy_threshold:.0f}")
    print("\nAb 8 baar bolo: 'Hey Anna' ya kuch bhi. (Ctrl+C se band)\n")
    for _ in range(8):
        print("Sun rahi hoon...")
        try:
            with mic as src:
                audio = rec.listen(src, timeout=6, phrase_time_limit=5)
        except sr.WaitTimeoutError:
            print("  -> kuch nahi suna (mic ki awaaz kam hai ya galat mic chuna hai)")
            continue
        try:
            text = rec.recognize_google(audio, language=LANGUAGE).lower()
        except sr.UnknownValueError:
            print("  -> awaaz aayi par samajh nahi aayi")
            continue
        except sr.RequestError as e:
            print("  -> Google speech service nahi mili (internet check karo):", e)
            return
        woke, rest = split_wake_word(text)
        print(f"  -> suna: {text!r}   wake word: {'HAAN' if woke else 'NAHI'}")


def main():
    if "--test-mic" in sys.argv:
        test_mic()
        return
    if "--pick-mic" in sys.argv:
        pick_mic()
        return
    if "--install-startup" in sys.argv:
        if install_startup():
            launch_detached()
            print("Ho gaya! Anna abhi background mein chalu ho gayi hai,")
            print("aur ab har baar laptop on hote hi apne aap chalu hogi.")
            print("Band karne ke liye: tray icon -> Quit Anna")
        else:
            print("Ye option sirf Windows pe hai.")
        return
    if "--remove-startup" in sys.argv:
        remove_startup()
        print("Startup hata diya. Ab Anna apne aap nahi chalegi.")
        return

    if sys.stdout is None or sys.stderr is None:      # pythonw: console nahi, to log file
        log = open(os.path.join(os.path.expanduser("~"), "ana.log"), "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log

    lock = acquire_lock()
    if lock is None:
        print("Anna pehle se chal rahi hai. (Band karne ke liye: tray icon -> Quit Anna,")
        print("ya Task Manager mein pythonw.exe ko End task karo.)")
        return

    pyautogui.FAILSAFE = True   # mouse ko corner mein le jao to automation ruk jayega
    app = App(quiet="--quiet" in sys.argv)
    app.can_hide = HIDE_WHEN_SLEEPING and start_tray(app)
    app.run()
    lock.close()


if __name__ == "__main__":
    main()
