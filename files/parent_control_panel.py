"""
Parental Control Panel (Windows) - ondersteunt meerdere kinderen
==================================================================

Draait op jouw Windows 11 pc. Heeft een tabblad per kind:
  - Tabblad "Zoon (Windows)"   -> praat met child_client_windows.py op poort 5001
  - Tabblad "Dochter (MacBook)" -> praat met child_client_mac.py op poort 5002

Voor elk apparaat vul je hier het AUTH_TOKEN in dat je ook in het
bijbehorende child-script hebt gezet. Zonder match werkt niets.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import threading
import time
import io
import requests
from PIL import Image, ImageTk


class RemoteTerminalWindow:
    def __init__(self, parent, device):
        self.device = device  # DeviceTab instance
        self.current_cwd = "~"
        self.prompt_start_index = "1.0"
        self.cmd_history = []
        self.history_index = 0

        self.win = tk.Toplevel(parent)
        self.win.title(f"Terminal (Remote - {device.name})")
        self.win.geometry("820x500")
        self.win.configure(bg="#0c0c0c")

        scrollbar = tk.Scrollbar(self.win)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.console = tk.Text(
            self.win, bg="#0c0c0c", fg="#cccccc", insertbackground="#ffffff",
            insertwidth=2, font=("Consolas", 11), relief=tk.FLAT, padx=8, pady=8,
            wrap=tk.CHAR, undo=False, yscrollcommand=scrollbar.set
        )
        self.console.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.console.yview)

        self.console.bind("<Return>", self.on_enter)
        self.console.bind("<BackSpace>", self.on_backspace)
        self.console.bind("<Up>", self.on_up)
        self.console.bind("<Down>", self.on_down)
        self.console.bind("<Key>", self.on_any_key)

        self.write_text(f"Remote Parental Shell - {device.name}\n")
        self.write_text("Verbinding maken...\n\n")
        self.console.focus_set()
        self.send_command("", silent=True)

    def write_text(self, text):
        self.console.insert(tk.END, text)
        self.console.see(tk.END)

    def show_prompt(self):
        self.write_text(f"{self.current_cwd}>")
        self.prompt_start_index = self.console.index("end-1c")
        self.console.mark_set(tk.INSERT, tk.END)
        self.console.see(tk.END)

    def get_current_input(self):
        return self.console.get(self.prompt_start_index, "end-1c")

    def replace_current_input(self, new_text):
        self.console.delete(self.prompt_start_index, "end-1c")
        self.console.insert(self.prompt_start_index, new_text)
        self.console.mark_set(tk.INSERT, tk.END)

    def on_any_key(self, event):
        if event.char and event.char.isprintable():
            if self.console.compare(tk.INSERT, "<", self.prompt_start_index):
                self.console.mark_set(tk.INSERT, tk.END)
        return None

    def on_backspace(self, event):
        if self.console.compare(tk.INSERT, "<=", self.prompt_start_index):
            return "break"
        return None

    def on_up(self, event):
        if self.cmd_history and self.history_index > 0:
            self.history_index -= 1
            self.replace_current_input(self.cmd_history[self.history_index])
        return "break"

    def on_down(self, event):
        if self.cmd_history and self.history_index < len(self.cmd_history) - 1:
            self.history_index += 1
            self.replace_current_input(self.cmd_history[self.history_index])
        elif self.history_index == len(self.cmd_history) - 1:
            self.history_index = len(self.cmd_history)
            self.replace_current_input("")
        return "break"

    def on_enter(self, event):
        cmd = self.get_current_input().strip()
        self.write_text("\n")
        if cmd:
            self.cmd_history.append(cmd)
            self.history_index = len(self.cmd_history)
        if cmd.lower() in ("cls", "clear"):
            self.console.delete("1.0", tk.END)
            self.show_prompt()
            return "break"
        if cmd.lower() == "exit":
            self.win.destroy()
            return "break"
        if not cmd:
            self.show_prompt()
            return "break"
        self.send_command(cmd, silent=False)
        return "break"

    def send_command(self, cmd, silent=False):
        ip = self.device.ip
        if not ip:
            self.write_text("Fout: geen verbinding met dit apparaat.\n\n")
            self.show_prompt()
            return

        def worker():
            try:
                res = self.device.api_post("/terminal", json={"cmd": cmd}, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    self.win.after(0, self.handle_response, data.get("cwd", self.current_cwd), data.get("output", ""), silent)
                elif res.status_code == 401:
                    self.win.after(0, self.handle_response, self.current_cwd, "Fout: token klopt niet (401 Unauthorized).\n", silent)
                else:
                    self.win.after(0, self.handle_response, self.current_cwd, f"Serverfout: HTTP {res.status_code}\n", silent)
            except Exception as e:
                self.win.after(0, self.handle_response, self.current_cwd, f"Verbindingsfout: {e}\n", silent)

        threading.Thread(target=worker, daemon=True).start()

    def handle_response(self, new_cwd, out, silent):
        if not self.win.winfo_exists():
            return
        self.current_cwd = new_cwd
        if not silent and out:
            if not out.endswith("\n"):
                out += "\n"
            self.write_text(out + "\n")
        self.show_prompt()


class DeviceTab:
    """Een tabblad voor één kind-apparaat (Windows of macOS)."""

    def __init__(self, notebook, root, name, port):
        self.root = root
        self.name = name
        self.port = port
        self.ip = None
        self.last_seen = 0
        self.apps_loaded = False
        self.blocked_apps = []
        self.terminal_window = None

        self.frame = tk.Frame(notebook, bg="#1e1e2e")
        notebook.add(self.frame, text=name)

        # --- token invoer ---
        token_frame = tk.Frame(self.frame, bg="#2a2a3c", pady=8, padx=12)
        token_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Label(token_frame, text="Auth-token (moet exact overeenkomen met het token in het child-script):",
                 fg="#ccc", bg="#2a2a3c", font=("Segoe UI", 9)).pack(anchor=tk.W)
        self.token_entry = tk.Entry(token_frame, show="•", font=("Consolas", 10))
        self.token_entry.pack(fill=tk.X, pady=(4, 0))

        # --- bovenbalk ---
        top_frame = tk.Frame(self.frame, bg="#2a2a3c", pady=10, padx=15)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        self.status_label = tk.Label(
            top_frame, text=f"🔍 Zoeken naar {name} op netwerk...",
            fg="#f39c12", bg="#2a2a3c", font=("Segoe UI", 11, "bold")
        )
        self.status_label.pack(side=tk.LEFT)

        self.lock_btn = tk.Button(top_frame, text="🔒 Scherm Vergrendelen", bg="#e74c3c", fg="white",
                                   font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=12, pady=5,
                                   command=self.lock_child, state=tk.DISABLED)
        self.lock_btn.pack(side=tk.RIGHT)

        self.term_btn = tk.Button(top_frame, text=">_ Open Terminal", bg="#0c0c0c", fg="#2ecc71",
                                   font=("Consolas", 10, "bold"), relief=tk.FLAT, padx=12, pady=5,
                                   command=self.open_terminal_window, state=tk.DISABLED)
        self.term_btn.pack(side=tk.RIGHT, padx=(0, 10))

        # --- hoofdscherm ---
        main_frame = tk.Frame(self.frame, bg="#1e1e2e")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.screen_label = tk.Label(main_frame, text="Wachten op verbinding...", fg="#888",
                                      bg="#000000", width=90, height=28, font=("Segoe UI", 10))
        self.screen_label.pack(side=tk.LEFT, padx=(0, 10))

        right_panel = tk.Frame(main_frame, bg="#2a2a3c", padx=15, pady=15, width=280)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y)
        right_panel.pack_propagate(False)

        tk.Label(right_panel, text="🚫 Geblokkeerde Apps", fg="white", bg="#2a2a3c",
                 font=("Segoe UI", 12, "bold")).pack(anchor=tk.W, pady=(0, 10))

        add_frame = tk.Frame(right_panel, bg="#2a2a3c")
        add_frame.pack(fill=tk.X, pady=(0, 10))
        self.new_app_entry = tk.Entry(add_frame, font=("Segoe UI", 10))
        self.new_app_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.ban_btn = tk.Button(add_frame, text="Ban", bg="#e67e22", fg="white", font=("Segoe UI", 9, "bold"),
                                  relief=tk.FLAT, padx=10, command=self.ban_app, state=tk.DISABLED)
        self.ban_btn.pack(side=tk.RIGHT)

        self.apps_listbox = tk.Listbox(right_panel, bg="#1e1e2e", fg="white", font=("Segoe UI", 10),
                                        selectbackground="#3498db", relief=tk.FLAT, height=16)
        self.apps_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.unban_btn = tk.Button(right_panel, text="✅ Deblokkeren", bg="#2ecc71", fg="white",
                                    font=("Segoe UI", 10, "bold"), relief=tk.FLAT, pady=6,
                                    command=self.unban_app, state=tk.DISABLED)
        self.unban_btn.pack(fill=tk.X)

        threading.Thread(target=self.update_screen_loop, daemon=True).start()

    # --- netwerkhelpers ---
    def api_headers(self):
        return {"Authorization": f"Bearer {self.token_entry.get().strip()}"}

    def api_get(self, path, **kw):
        return requests.get(f"http://{self.ip}:{self.port}{path}", headers=self.api_headers(), **kw)

    def api_post(self, path, **kw):
        return requests.post(f"http://{self.ip}:{self.port}{path}", headers=self.api_headers(), **kw)

    def on_discovered(self, ip):
        self.ip = ip
        self.last_seen = time.time()
        self.root.after(0, self.set_online_ui)

    def set_online_ui(self):
        self.status_label.config(text=f"● Verbonden ({self.ip})", fg="#2ecc71")
        self.lock_btn.config(state=tk.NORMAL)
        self.ban_btn.config(state=tk.NORMAL)
        self.unban_btn.config(state=tk.NORMAL)
        self.term_btn.config(state=tk.NORMAL)
        if not self.apps_loaded:
            self.apps_loaded = True
            threading.Thread(target=self.fetch_current_apps, daemon=True).start()

    def set_offline_ui(self):
        self.status_label.config(text="● Verbinding verbroken — opnieuw zoeken...", fg="#e74c3c")
        self.lock_btn.config(state=tk.DISABLED)
        self.ban_btn.config(state=tk.DISABLED)
        self.unban_btn.config(state=tk.DISABLED)
        self.term_btn.config(state=tk.DISABLED)

    def fetch_current_apps(self):
        try:
            res = self.api_get("/get_apps", timeout=2)
            if res.status_code == 200:
                self.blocked_apps = res.json().get("apps", [])
                self.root.after(0, self.refresh_listbox)
        except Exception:
            self.apps_loaded = False

    def refresh_listbox(self):
        self.apps_listbox.delete(0, tk.END)
        for a in self.blocked_apps:
            self.apps_listbox.insert(tk.END, a)

    def sync_apps(self):
        if self.ip:
            threading.Thread(target=lambda: self.api_post("/set_apps", json={"apps": self.blocked_apps}), daemon=True).start()

    def ban_app(self):
        name = self.new_app_entry.get().strip()
        if not name:
            return
        if name.lower() not in [a.lower() for a in self.blocked_apps]:
            self.blocked_apps.append(name)
            self.refresh_listbox()
            self.sync_apps()
            self.new_app_entry.delete(0, tk.END)

    def unban_app(self):
        sel = self.apps_listbox.curselection()
        if not sel:
            messagebox.showwarning("Selectie", "Klik eerst een app aan in de lijst.")
            return
        name = self.apps_listbox.get(sel)
        self.blocked_apps.remove(name)
        self.refresh_listbox()
        self.sync_apps()

    def update_screen_loop(self):
        while True:
            if self.ip and (time.time() - self.last_seen < 6):
                try:
                    res = self.api_get("/screenshot", timeout=1.5)
                    if res.status_code == 200:
                        img = Image.open(io.BytesIO(res.content))
                        img.thumbnail((720, 480))
                        photo = ImageTk.PhotoImage(img)
                        self.root.after(0, self.render_frame, photo)
                    elif res.status_code == 401:
                        self.root.after(0, lambda: self.screen_label.config(
                            image="", text="Token klopt niet (401). Controleer het token hierboven."))
                except Exception as e:
                    self.root.after(0, lambda err=str(e): self.screen_label.config(
                        image="", text=f"Verbonden met {self.ip}, fout bij ophalen beeld:\n{err}"))
            elif self.ip:
                self.root.after(0, self.set_offline_ui)
            time.sleep(0.35)

    def render_frame(self, photo):
        self.screen_label.config(image=photo, text="", width=720, height=480)
        self.screen_label.image = photo

    def lock_child(self):
        if self.ip:
            threading.Thread(target=lambda: self.api_post("/lock"), daemon=True).start()
            messagebox.showinfo("Vergrendeld", f"Het scherm van {self.name} is vergrendeld.")

    def open_terminal_window(self):
        if self.terminal_window and self.terminal_window.win.winfo_exists():
            self.terminal_window.win.lift()
        else:
            self.terminal_window = RemoteTerminalWindow(self.root, self)


class ParentalControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Parental Control Panel")
        self.root.geometry("1120x700")
        self.root.configure(bg="#1e1e2e")

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Eén tab per kind. Poorten moeten overeenkomen met de child-scripts.
        self.devices = [
            DeviceTab(notebook, root, "Zoon (Windows)", port=5001),
            DeviceTab(notebook, root, "Dochter (MacBook)", port=5002),
        ]
        self.devices_by_name = {d.name: d for d in self.devices}

        threading.Thread(target=self.listen_for_children, daemon=True).start()

    def listen_for_children(self):
        """Luistert naar presence-broadcasts van child-scripts en koppelt het IP
        aan het juiste tabblad op basis van platform + poort."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", 5005))
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                parts = data.decode(errors="ignore").split("|")
                if len(parts) >= 4 and parts[0] == "PARENTAL_CHILD_ONLINE":
                    _, platform_, device_name, port_str = parts[:4]
                    ip, _ = addr
                    for device in self.devices:
                        if str(device.port) == port_str:
                            device.on_discovered(ip)
            except Exception:
                pass


if __name__ == "__main__":
    root = tk.Tk()
    app = ParentalControlApp(root)
    root.mainloop()
