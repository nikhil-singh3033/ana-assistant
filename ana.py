"""
ANA - Laptop Voice Assistant (Siri-style animated UI)
Run:  python ana.py
Wake word: "ana"  (ya UI ka mic button dabao)
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
# "ana" ko mic aksar alag sunta hai (anna, aana, ena...), isliye sab pehchante hain.
# Agar galti se bina bulaye chalne lage, to is list se extra naam hata do.
WAKE_WORDS = ["ana", "anna", "aana", "anaa", "ena", "anah", "ann"]
LANGUAGE = "en-IN"          # Hinglish ke liye best chalta hai
FOLLOWUP_SECONDS = 15       # wake ke baad itni der tak bina "ana" bole sunta rahega
OS = platform.system()      # Windows / Darwin / Linux

STATE_COLORS = {
    "idle": ("#3b82f6", "#1e3a8a"),
    "listening": ("#22d3ee", "#0e7490"),
    "thinking": ("#a855f7", "#6b21a8"),
    "speaking": ("#f472b6", "#9d174d"),
    "muted": ("#6b7280", "#374151"),
}

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
    """Agar text mein wake word hai to (True, baaki command) deta hai, warna (False, text)."""
    words = re.findall(r"[\w']+", text.lower())
    for i, w in enumerate(words):
        if w in WAKE_WORDS:
            return True, " ".join(words[i + 1:])
    return False, text


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

    def speak(self, text):
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
        self.q.put(("state", "idle"))

    def listen_once(self, mic, timeout=5, limit=8):
        try:
            audio = self.rec.listen(mic, timeout=timeout, phrase_time_limit=limit)
        except sr.WaitTimeoutError:
            return None
        self.q.put(("state", "thinking"))
        try:
            return self.rec.recognize_google(audio, language=LANGUAGE).lower()
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            self.q.put(("reply", "Internet check karo, speech service nahi chal rahi"))
            return None

    def loop(self):
        try:
            mic = sr.Microphone()
        except Exception as e:
            self.q.put(("reply", f"Mic nahi mila: {e}"))
            return
        with mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)
        self.speak(f"{ASSISTANT_NAME} ready hai")

        while self.running:
            if self.muted:
                self.q.put(("state", "muted"))
                time.sleep(0.3)
                continue

            self.q.put(("state", "listening" if time.time() < self.awake_until else "idle"))
            with mic as src:
                text = self.listen_once(src)
            if not text:
                continue

            self.q.put(("heard", text))
            awake = time.time() < self.awake_until
            woke, cmd = split_wake_word(text)

            if woke:
                if not cmd:
                    self.awake_until = time.time() + FOLLOWUP_SECONDS
                    self.speak("Haan boliye")
                    continue
            elif awake:
                cmd = text
            else:
                self.q.put(("state", "idle"))
                continue

            reply = handle(cmd, self)
            if reply == "EXIT":
                self.speak("Theek hai, bye!")
                self.q.put(("quit", None))
                return
            if reply:
                self.speak(reply)
                self.awake_until = time.time() + FOLLOWUP_SECONDS


# ---------------------------------------------------------------------- UI --
class App:
    W, H = 420, 600

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(ASSISTANT_NAME)
        self.root.geometry(f"{self.W}x{self.H}")
        self.root.configure(bg="#07070f")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(self.root, width=self.W, height=380,
                                bg="#07070f", highlightthickness=0)
        self.canvas.pack()

        self.heard_lbl = tk.Label(self.root, text="", fg="#9ca3af", bg="#07070f",
                                  font=("Segoe UI", 11, "italic"), wraplength=380)
        self.heard_lbl.pack(pady=(4, 2))
        self.reply_lbl = tk.Label(self.root, text="Starting...", fg="#f9fafb", bg="#07070f",
                                  font=("Segoe UI", 15), wraplength=380, justify="center")
        self.reply_lbl.pack(pady=6)

        self.mic_btn = tk.Button(self.root, text="🎙  Mute", command=self.toggle_mute,
                                 bg="#1f2937", fg="white", bd=0, padx=20, pady=8,
                                 font=("Segoe UI", 11), activebackground="#374151",
                                 activeforeground="white")
        self.mic_btn.pack(pady=14)

        self.state = "idle"
        self.t = 0.0
        self.q = queue.Queue()
        self.voice = Voice(self.q)
        threading.Thread(target=self.voice.loop, daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.tick()

    def toggle_mute(self):
        self.voice.muted = not self.voice.muted
        self.mic_btn.config(text="🔇  Unmute" if self.voice.muted else "🎙  Mute")

    def close(self):
        self.voice.running = False
        self.root.destroy()

    def poll(self):
        while True:
            try:
                kind, val = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "state":
                self.state = val
            elif kind == "heard":
                self.heard_lbl.config(text=f"“{val}”")
            elif kind == "reply":
                self.reply_lbl.config(text=val)
            elif kind == "quit":
                self.root.after(800, self.close)

    def draw_orb(self):
        c = self.canvas
        c.delete("orb")
        cx, cy = self.W / 2, 190
        main, glow = STATE_COLORS.get(self.state, STATE_COLORS["idle"])

        speed = {"idle": 1.2, "listening": 3, "thinking": 6,
                 "speaking": 4.5, "muted": 0.5}.get(self.state, 1.2)
        amp = {"idle": 4, "listening": 12, "thinking": 8,
               "speaking": 20, "muted": 1}.get(self.state, 4)

        for i in range(6, 0, -1):
            wobble = math.sin(self.t * speed + i * 0.9) * amp
            r = 40 + i * 14 + wobble
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          outline=glow if i % 2 else main,
                          width=2 if i > 2 else 3, tags="orb")

        core = 38 + math.sin(self.t * speed) * (amp * 0.5)
        c.create_oval(cx - core, cy - core, cx + core, cy + core,
                      fill=main, outline="", tags="orb")
        c.create_oval(cx - core * 0.5, cy - core * 0.6, cx + core * 0.1, cy - core * 0.1,
                      fill="#ffffff", outline="", stipple="gray25", tags="orb")

        c.create_text(cx, 350, text=ASSISTANT_NAME.upper(), fill=main,
                      font=("Segoe UI", 16, "bold"), tags="orb")

    def tick(self):
        self.t += 0.033
        self.poll()
        self.draw_orb()
        self.root.after(33, self.tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    pyautogui.FAILSAFE = True   # mouse ko corner mein le jao to automation ruk jayega
    App().run()
