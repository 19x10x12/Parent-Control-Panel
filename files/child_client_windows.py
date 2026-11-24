"""
Parental Control - Windows Child Client (bijgewerkt)
======================================================

Zelfde als je oorspronkelijke child_client_pyw.py, maar nu met verplichte
authenticatie op elk endpoint. Zonder het juiste token (ingesteld in het
parent control panel) werkt er niets, ook niet voor andere apparaten op
hetzelfde wifi-netwerk.
"""

import time
import io
import os
import sys
import ctypes
import secrets
import subprocess
import socket
import threading
from functools import wraps
from flask import Flask, request, jsonify, Response
import mss
import psutil
from PIL import Image

# ------------------------------------------------------------------
# CONFIGURATIE - PAS DIT AAN
# ------------------------------------------------------------------
AUTH_TOKEN = "VERANDER_DIT_IN_EEN_LANG_WILLEKEURIG_TOKEN"
DEVICE_NAME = "Laptop Zoon"
PORT = 5001
# ------------------------------------------------------------------


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def setup_firewall():
    cmd = (
        'netsh advfirewall firewall add rule name="ParentalControlAuto" '
        f'dir=in action=allow protocol=TCP localport={PORT}'
    )
    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if not is_admin():
    # Dit toont een zichtbare Windows UAC-prompt; niets gebeurt hier onzichtbaar.
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{os.path.abspath(__file__)}"', None, 0)
    sys.exit()
else:
    setup_firewall()

app = Flask(__name__)
current_dir = os.path.expanduser("~")
config = {"blocked_apps": ["RobloxPlayerBeta.exe", "steam.exe"]}


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
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    msg = f"PARENTAL_CHILD_ONLINE|windows|{DEVICE_NAME}|{PORT}".encode()
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
                    pname = proc.info.get("name")
                    if pname and pname.lower() in blocked:
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
    os.system("rundll32.exe user32.dll,LockWorkStation")
    return jsonify({"status": "locked"})


@app.route("/set_apps", methods=["POST"])
@require_auth
def set_apps():
    data = request.json or {}
    config["blocked_apps"] = data.get("apps", [])
    return jsonify({"status": "updated"})


@app.route("/get_apps", methods=["GET"])
@require_auth
def get_apps():
    return jsonify({"apps": config["blocked_apps"]})


@app.route("/terminal", methods=["POST"])
@require_auth
def run_terminal():
    global current_dir
    cmd = (request.json or {}).get("cmd", "").strip()

    if not cmd:
        return jsonify({"output": "", "cwd": current_dir})

    if cmd.lower() == "ls":
        cmd = "dir"
    elif cmd.lower().startswith("ls "):
        cmd = "dir " + cmd[3:]

    if len(cmd) == 2 and cmd[1] == ":" and cmd[0].isalpha():
        target = cmd.upper() + "\\"
        if os.path.exists(target):
            current_dir = target
            return jsonify({"output": "", "cwd": current_dir})
        return jsonify({"output": f"Het systeem kan het opgegeven station ({cmd}) niet vinden.\n", "cwd": current_dir})

    if cmd.lower() == "cd":
        return jsonify({"output": current_dir + "\n", "cwd": current_dir})
    elif cmd.lower().startswith("cd ") or cmd.lower().startswith("cd\\") or cmd.lower().startswith("cd/"):
        target = cmd[2:].strip()
        if target.startswith("/d "):
            target = target[3:].strip()
        target = target.strip('"')
        new_path = os.path.abspath(os.path.join(current_dir, target))
        if os.path.isdir(new_path):
            current_dir = new_path
            return jsonify({"output": "", "cwd": current_dir})
        return jsonify({"output": f"Het systeem kan het opgegeven pad niet vinden: {target}\n", "cwd": current_dir})

    try:
        res = subprocess.run(
            cmd, shell=True, cwd=current_dir, capture_output=True,
            text=True, encoding="cp850", errors="replace", timeout=15
        )
        output = res.stdout + res.stderr
    except subprocess.TimeoutExpired:
        output = "Fout: Commando duurde te lang (time-out na 15 seconden).\n"
    except Exception as e:
        output = f"Fout bij uitvoeren: {str(e)}\n"

    return jsonify({"output": output, "cwd": current_dir})


if __name__ == "__main__":
    if AUTH_TOKEN.startswith("VERANDER_DIT"):
        print("!! LET OP: pas AUTH_TOKEN aan voor je dit gebruikt.")
    threading.Thread(target=broadcast_presence, daemon=True).start()
    threading.Thread(target=enforce_rules, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)
