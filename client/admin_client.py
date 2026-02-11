import tkinter as tk
from tkinter import messagebox
import threading
import asyncio
import websockets
import json

SERVER_URL = "ws://localhost:8765"


class AdminApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Truco Admin")
        self.root.geometry("520x520")

        self.ws = None
        self.loop = None
        self.role = None

        self.auth = tk.Frame(root)
        self.auth.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(self.auth, text="Usuário").grid(row=0, column=0, sticky="w")
        self.user = tk.Entry(self.auth)
        self.user.grid(row=0, column=1, sticky="ew", padx=5)

        tk.Label(self.auth, text="Senha").grid(row=1, column=0, sticky="w")
        self.pw = tk.Entry(self.auth, show="*")
        self.pw.grid(row=1, column=1, sticky="ew", padx=5)

        self.login_btn = tk.Button(self.auth, text="Login", state=tk.DISABLED, command=self.do_login)
        self.login_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=6)

        self.auth.columnconfigure(1, weight=1)

        # controls
        self.controls = tk.Frame(root)
        self.controls.pack(fill=tk.X, padx=10)

        self.list_btn = tk.Button(self.controls, text="Listar salas", state=tk.DISABLED, command=self.list_rooms)
        self.list_btn.pack(fill=tk.X, pady=4)

        # close room
        close_frame = tk.Frame(self.controls)
        close_frame.pack(fill=tk.X, pady=4)
        tk.Label(close_frame, text="Fechar sala:").pack(side=tk.LEFT)
        self.close_room_entry = tk.Entry(close_frame)
        self.close_room_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.close_btn = tk.Button(close_frame, text="Fechar", state=tk.DISABLED, command=self.close_room)
        self.close_btn.pack(side=tk.LEFT)

        # kick
        kick_frame = tk.Frame(self.controls)
        kick_frame.pack(fill=tk.X, pady=4)
        tk.Label(kick_frame, text="Kick (sala / user):").pack(side=tk.LEFT)
        self.kick_room = tk.Entry(kick_frame, width=14)
        self.kick_room.pack(side=tk.LEFT, padx=5)
        self.kick_user = tk.Entry(kick_frame, width=14)
        self.kick_user.pack(side=tk.LEFT, padx=5)
        self.kick_btn = tk.Button(kick_frame, text="Kick", state=tk.DISABLED, command=self.kick)
        self.kick_btn.pack(side=tk.LEFT)

        # output
        self.out = tk.Text(root, state="disabled", height=16)
        self.out.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        threading.Thread(target=self.start_ws, daemon=True).start()

    def start_ws(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.ws_loop())

    async def ws_loop(self):
        try:
            async with websockets.connect(SERVER_URL) as ws:
                self.ws = ws
                self.root.after(0, lambda: self.login_btn.config(state=tk.NORMAL))
                async for msg in ws:
                    data = json.loads(msg)
                    self.root.after(0, self.handle, data)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Erro", str(e)))

    def send_ws(self, data):
        if not self.ws or not self.loop:
            return
        asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(data)), self.loop)

    def write(self, line):
        self.out.config(state="normal")
        self.out.insert(tk.END, line + "\n")
        self.out.config(state="disabled")
        self.out.see(tk.END)

    def do_login(self):
        self.send_ws({"type": "login", "user": self.user.get().strip(), "pass": self.pw.get()})

    def list_rooms(self):
        self.send_ws({"type": "admin_list_rooms"})

    def close_room(self):
        self.send_ws({"type": "admin_close_room", "room": self.close_room_entry.get().strip()})

    def kick(self):
        self.send_ws({
            "type": "admin_kick",
            "room": self.kick_room.get().strip(),
            "user": self.kick_user.get().strip()
        })

    def handle(self, data):
        t = data.get("type")
        if t == "login_ok":
            self.role = data.get("role")
            self.write(f"Logado. role={self.role}")
            if self.role == "admin":
                self.list_btn.config(state=tk.NORMAL)
                self.close_btn.config(state=tk.NORMAL)
                self.kick_btn.config(state=tk.NORMAL)
            else:
                messagebox.showerror("Erro", "Este usuário não é admin.")
        elif t == "admin_rooms":
            self.write("Salas:")
            for r in data.get("rooms", []):
                self.write(f"- {r['room']} ({len(r['users'])}): {', '.join(r['users'])}")
        elif t == "admin_ok":
            self.write("OK: " + data.get("message", ""))
        elif t == "system":
            self.write("[SYSTEM] " + data.get("message", ""))
        elif t == "error":
            messagebox.showerror("Erro", data.get("message", "Erro"))


root = tk.Tk()
app = AdminApp(root)
root.mainloop()
