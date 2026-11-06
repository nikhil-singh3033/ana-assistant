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
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c)


def mix(c1, c2, t):
    return tuple(a + (b - a) * t for a, b in zip(c1, c2))


TRANSPARENT = "#010101"
CARD = "#0a0c16"
CARD_RGB = hex_to_rgb(CARD)
BORDER = "#1a2036"
BORDER_RGB = hex_to_rgb(BORDER)
WHITE = (255, 255, 255)

THEMES = {
    "sleeping":  dict(main="#5b7bff", dark="#161d52", speed=1.0, amp=3,  bars=2,  glow=0.30,
                      label="Say  “Hey Ana”"),
    "listening": dict(main="#22d3ee", dark="#0a566e", speed=3.2, amp=10, bars=18, glow=0.90,
                      label="Listening…"),
    "thinking":  dict(main="#a855f7", dark="#431a85", speed=6.0, amp=6,  bars=7,  glow=0.70,
                      label="Thinking…"),
    "speaking":  dict(main="#f472b6", dark="#7a1445", speed=4.6, amp=14, bars=34, glow=1.00,
                      label="Speaking…"),
    "muted":     dict(main="#6b7280", dark="#232833", speed=0.4, amp=1,  bars=1,  glow=0.12,
                      label="Mic muted"),
}
PLACEHOLDER = "Type a command…"


def rounded_rect(c, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class App:
    W, H = 360, 600

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(ASSISTANT_NAME)
        self.root.overrideredirect(True)            # bina title bar ke floating card
        self.root.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{self.W}x{self.H}+{sw - self.W - 30}+{max(20, sh - self.H - 80)}")
        self.root.configure(bg=TRANSPARENT)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)   # gol corners (Windows)
        except tk.TclError:
            pass

        c = self.canvas = tk.Canvas(self.root, width=self.W, height=self.H,
                                    bg=TRANSPARENT, highlightthickness=0)
        c.pack()
        self.card = rounded_rect(c, 4, 4, self.W - 4, self.H - 4, 34,
                                 fill=CARD, outline=BORDER, width=2)

        c.create_text(self.W / 2, 36, text="A  N  A", fill="#e5e7eb",
                      font=("Segoe UI Semibold", 12))
        close = c.create_text(self.W - 34, 34, text="✕", fill="#5b6275",
                              font=("Segoe UI", 13), tags="close")
        c.tag_bind("close", "<Enter>", lambda e: c.itemconfig(close, fill="#f87171"))
        c.tag_bind("close", "<Leave>", lambda e: c.itemconfig(close, fill="#5b6275"))
        c.tag_bind("close", "<Button-1>", lambda e: self.close())

        self.status_id = c.create_text(self.W / 2, 395, text="", font=("Segoe UI Semibold", 12))
        self.heard_id = c.create_text(self.W / 2, 422, text="", fill="#7c8499", width=self.W - 70,
                                      font=("Segoe UI", 10, "italic"), anchor="n", justify="center")
        self.reply_id = c.create_text(self.W / 2, 462, text="Starting…", fill="#f3f4f6", width=self.W - 64,
                                      font=("Segoe UI", 13), anchor="n", justify="center")

        # text box (command type karne ke liye)
        self.entry = tk.Entry(self.root, bg="#121626", fg="#6b7280", insertbackground="#e5e7eb",
                              relief="flat", font=("Segoe UI", 11), highlightthickness=1,
                              highlightbackground="#1e2540", highlightcolor="#3b82f6")
        self.entry.insert(0, PLACEHOLDER)
        self.entry.bind("<FocusIn>", self.entry_focus_in)
        self.entry.bind("<FocusOut>", self.entry_focus_out)
        self.entry.bind("<Button-1>", lambda e: self.entry.focus_force())
        self.entry.bind("<Return>", self.submit_text)
        c.create_window(self.W / 2 - 26, self.H - 50, window=self.entry,
                        width=self.W - 120, height=32)

        # mic button
        self.mic_bg = c.create_oval(self.W - 66, self.H - 68, self.W - 30, self.H - 32,
                                    fill="#121626", outline="#1e2540", width=2, tags="mic")
        self.mic_ic = c.create_text(self.W - 48, self.H - 50, text="🎙", fill="#e5e7eb",
                                    font=("Segoe UI Emoji", 12), tags="mic")
        c.tag_bind("mic", "<Button-1>", lambda e: self.toggle_mute())

        # window ko drag karne ke liye
        self._dx = self._dy = 0
        c.bind("<ButtonPress-1>", self.drag_start)
        c.bind("<B1-Motion>", self.drag_move)

        # animation state
        self.state = "sleeping"
        self.t = 0.0
        self.pulse = None
        th = THEMES["sleeping"]
        self.cur = dict(main=hex_to_rgb(th["main"]), dark=hex_to_rgb(th["dark"]),
                        speed=th["speed"], amp=th["amp"], bars=th["bars"], glow=th["glow"])

        self.q = queue.Queue()
        self.voice = Voice(self.q)
        threading.Thread(target=self.voice.loop, daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    # ---- window helpers
    def drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def close(self):
        self.voice.running = False
        self.root.destroy()

    # ---- input helpers
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
        muted = self.voice.muted
        self.canvas.itemconfig(self.mic_bg, fill="#3a1418" if muted else "#121626",
                               outline="#f87171" if muted else "#1e2540")
        self.canvas.itemconfig(self.mic_ic, text="🔇" if muted else "🎙")

    # ---- messages from voice thread
    def poll(self):
        while True:
            try:
                kind, val = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                self.state = val
            elif kind == "heard":
                self.canvas.itemconfig(self.heard_id, text=f"“{val[:70]}”")
            elif kind == "reply":
                if len(val) > 120:
                    val = val[:117] + "…"
                self.canvas.itemconfig(self.reply_id, text=val)
            elif kind == "pulse":
                self.pulse = 0.0
            elif kind == "quit":
                self.root.after(900, self.close)

    # ---- drawing
    def draw(self):
        c = self.canvas
        c.delete("dyn")
        th = THEMES.get(self.state, THEMES["sleeping"])
        for k in self.cur:                      # theme ki taraf smoothly badlo
            tgt = hex_to_rgb(th[k]) if k in ("main", "dark") else th[k]
            if k in ("main", "dark"):
                self.cur[k] = mix(self.cur[k], tgt, 0.12)
            else:
                self.cur[k] += (tgt - self.cur[k]) * 0.12

        main, dark = self.cur["main"], self.cur["dark"]
        speed, amp, glow = self.cur["speed"], self.cur["amp"], self.cur["glow"]
        t = self.t
        cx, cy = self.W / 2, 200
        R = 50 + math.sin(t * speed) * amp * 0.35

        # card border thoda chamke jab jaag rahi ho
        c.itemconfig(self.card, outline=rgb_to_hex(mix(BORDER_RGB, main, 0.55 * glow)))
        c.itemconfig(self.status_id, text=th["label"], fill=rgb_to_hex(mix(main, WHITE, 0.25)))

        # soft glow (radial gradient)
        steps = 16
        for k in range(steps, 0, -1):
            rr = R + k * 5
            a = (1 - k / steps) ** 2 * 0.55 * glow
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                          fill=rgb_to_hex(mix(CARD_RGB, main, a)), outline="", tags="dyn")

        # lehrati rings
        for i in range(3):
            rr = R + 14 + i * 13 + math.sin(t * speed * 0.8 + i * 1.3) * amp * 0.5
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill="", width=2, tags="dyn",
                          outline=rgb_to_hex(mix(CARD_RGB, main, 0.55 - i * 0.14)))

        # sochte waqt ghoomte arcs
        if self.state == "thinking":
            rr = R + 38
            for off in (0, 180):
                c.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=(t * 230 + off) % 360,
                             extent=70, style="arc", width=3, tags="dyn",
                             outline=rgb_to_hex(mix(main, WHITE, 0.3)))

        # 3D jaisa orb
        steps = 14
        hi = mix(main, WHITE, 0.6)
        for s in range(steps):
            f = s / (steps - 1)
            rr = R * (1 - f * 0.92)
            ox, oy = -f * R * 0.20, -f * R * 0.24
            c.create_oval(cx + ox - rr, cy + oy - rr, cx + ox + rr, cy + oy + rr,
                          fill=rgb_to_hex(mix(dark, hi, f)), outline="", tags="dyn")

        # jaagne par expanding ring
        if self.pulse is not None:
            p = self.pulse
            rr = R + 20 + p * 130
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill="", width=3, tags="dyn",
                          outline=rgb_to_hex(mix(CARD_RGB, main, (1 - p) * 0.95)))
            self.pulse = p + 0.04 if p < 1 else None

        # waveform bars
        n, bw, gap, base = 27, 5, 4, 346
        x0 = cx - (n * (bw + gap) - gap) / 2
        for i in range(n):
            env = 1 - abs((i - (n - 1) / 2) / ((n - 1) / 2)) ** 1.5
            wave = abs(math.sin(t * speed * 1.3 + i * 0.55) * math.sin(t * 2.1 + i * 0.37))
            h = 2 + self.cur["bars"] * env * (0.25 + 0.75 * wave)
            x = x0 + i * (bw + gap)
            c.create_rectangle(x, base - h, x + bw, base + h, outline="", tags="dyn",
                               fill=rgb_to_hex(mix(CARD_RGB, main, 0.40 + 0.60 * env)))

        # text items orb ke upar na aa jayein
        c.tag_raise(self.status_id)
        c.tag_raise(self.heard_id)
        c.tag_raise(self.reply_id)

    def tick(self):
        self.t += 0.033
        self.poll()
        self.draw()
        self.root.after(33, self.tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    pyautogui.FAILSAFE = True   # mouse ko corner mein le jao to automation ruk jayega
    App().run()
