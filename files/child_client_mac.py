#!/usr/bin/env python3
"""
Parental Control - macOS Child Client
======================================

Draait op de MacBook van je dochter. Vereist dat ze (of jij) dit zichtbaar
installeert en opstart; dit verbergt zichzelf NIET en vraagt geen stille
admin-rechten aan, in tegenstelling tot een "RAT".

Beveiliging t.o.v. het oorspronkelijke Windows-script:
  - Elk verzoek moet een geldig "Authorization: Bearer <TOKEN>" bevatten.
    Zonder het juiste token werkt geen enkel endpoint.
  - UDP-broadcast bevat alleen "ik ben online + apparaatnaam", NOOIT het token.
  - Er draait een zichtbaar menubalk-icoontje (via `rumps`) zodat altijd
    duidelijk is dat het programma actief is. Er is geen "onzichtbare .pyw"-modus.

Installatie (eenmalig, in Terminal op de Mac):
    python3 -m pip install flask mss psutil pillow rumps

Instellen:
  1. Verzin een lang, willekeurig token (bijv. via `python3 -c "import secrets;print(secrets.token_hex(16))"`)
  2. Vul dat token hieronder in bij AUTH_TOKEN.
  3. Vul precies hetzelfde token in bij het parent control panel voor dit apparaat.
  4. Start dit script. Een slotje-icoontje verschijnt in de menubalk.

Automatisch opstarten (optioneel, via LaunchAgent) staat onderaan toegelicht.
"""

import io
import os
import secrets
import socket
import subprocess
import threading
import time
from functools import wraps

from flask import Flask, request, jsonify, Response
import mss
import psutil
from PIL import Image

# ------------------------------------------------------------------
# CONFIGURATIE - PAS DIT AAN
# ------------------------------------------------------------------
AUTH_TOKEN = "VERANDER_DIT_IN_EEN_LANG_WILLEKEURIG_TOKEN"
DEVICE_NAME = "MacBook Dochter"
PORT = 5002  # ander poortnummer dan de Windows-client (5001), zodat ze naast elkaar kunnen draaien op het netwerk
# ------------------------------------------------------------------

if AUTH_TOKEN.startswith("VERANDER_DIT"):
    print("!! LET OP: je hebt het standaard AUTH_TOKEN nog niet aangepast.")
    print("!! Genereer er zelf een met: python3 -c \"import secrets;print(secrets.token_hex(16))\"")

app = Flask(__name__)
current_dir = os.path.expanduser("~")
config = {"blocked_apps": []}


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not secrets.compare_digest(token, AUTH_TOKEN):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper


def broadcast_presence():
    """Zendt alleen aanwezigheid + naam uit, GEEN token. Parent moet zelf het
    juiste token kennen om daadwerkelijk iets te kunnen doen."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    msg = f"PARENTAL_CHILD_ONLINE|mac|{DEVICE_NAME}|{PORT}".encode()
    while True:
        try:
            sock.sendto(msg, ("255.255.255.255", 5005))
        except Exception:
            pass
        time.sleep(2)


def enforce_rules():
    while True:
        blocked = [a.lower() for a in config["blocked_apps"]]
        if blocked:
            for proc in psutil.process_iter(["name"]):
                try:
                    pname = (proc.info.get("name") or "").lower()
                    if any(b in pname for b in blocked):
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        time.sleep(1)


@app.route("/screenshot")
@require_auth
def screenshot():
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        sct_img = sct.grab(mon)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        img.thumbnail((960, 540))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=55)
        return Response(buf.getvalue(), mimetype="image/jpeg")


@app.route("/lock", methods=["POST"])
@require_auth
def lock():
    # Ctrl+Cmd+Q is de systeemsnelkoppeling om het scherm te vergrendelen op macOS
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to keystroke "q" using {control down, command down}'
    ])
    return jsonify({"status": "locked"})


@app.route("/get_apps", methods=["GET"])
@require_auth
def get_apps():
    return jsonify({"apps": config["blocked_apps"]})


@app.route("/set_apps", methods=["POST"])
@require_auth
def set_apps():
    data = request.json or {}
    config["blocked_apps"] = data.get("apps", [])
    return jsonify({"status": "updated"})


@app.route("/terminal", methods=["POST"])
@require_auth
def run_terminal():
    global current_dir
    cmd = (request.json or {}).get("cmd", "").strip()
    if not cmd:
        return jsonify({"output": "", "cwd": current_dir})

    if cmd == "cd":
        return jsonify({"output": current_dir + "\n", "cwd": current_dir})
    if cmd.startswith("cd "):
        target = cmd[3:].strip().strip('"')
        new_path = os.path.abspath(os.path.join(current_dir, os.path.expanduser(target)))
        if os.path.isdir(new_path):
            current_dir = new_path
            return jsonify({"output": "", "cwd": current_dir})
        return jsonify({"output": f"cd: geen zo'n map: {target}\n", "cwd": current_dir})

    try:
        res = subprocess.run(
            cmd, shell=True, cwd=current_dir,
            capture_output=True, text=True, timeout=15
        )
        output = res.stdout + res.stderr
    except subprocess.TimeoutExpired:
        output = "Fout: commando duurde te lang (time-out na 15s).\n"
    except Exception as e:
        output = f"Fout bij uitvoeren: {e}\n"
    return jsonify({"output": output, "cwd": current_dir})


def run_server():
    threading.Thread(target=broadcast_presence, daemon=True).start()
    threading.Thread(target=enforce_rules, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)


# --------------------------------------------------------------
# Zichtbare menubalk-indicator (geen verborgen achtergrondproces)
# --------------------------------------------------------------
try:
    import rumps

    class StatusBarApp(rumps.App):
        def __init__(self):
            super().__init__("🔒 Toezicht actief", quit_button="Stoppen")
            self.menu = ["Apparaatnaam: " + DEVICE_NAME, "Poort: " + str(PORT)]

    if __name__ == "__main__":
        threading.Thread(target=run_server, daemon=True).start()
        StatusBarApp().run()

except ImportError:
    # rumps niet geinstalleerd: werkt nog steeds, maar dan zonder menubalk-icoontje.
    # Installeer met: python3 -m pip install rumps
    if __name__ == "__main__":
        print(f"[Parental Control] actief op poort {PORT} als '{DEVICE_NAME}' "
              f"(tip: installeer 'rumps' voor een zichtbaar menubalk-icoontje)")
        run_server()
