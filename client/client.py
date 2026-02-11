import tkinter as tk
from tkinter import messagebox, simpledialog
import threading
import asyncio
import websockets
import json

SERVER_URL = "ws://localhost:8765"


class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Truco Online")
        self.root.geometry("420x560")

        self.ws = None
        self.loop = None

        self.username = None
        self.role = None
        self.room = None

        # ===== AUTH FRAME =====
        self.auth_frame = tk.Frame(root)
        self.auth_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(self.auth_frame, text="Truco Online", font=("Arial", 16, "bold")).pack(pady=10)

        tk.Label(self.auth_frame, text="Usuário").pack(anchor="w")
        self.user_entry = tk.Entry(self.auth_frame)
        self.user_entry.pack(fill=tk.X, pady=4)

        tk.Label(self.auth_frame, text="Senha").pack(anchor="w")
        self.pass_entry = tk.Entry(self.auth_frame, show="*")
        self.pass_entry.pack(fill=tk.X, pady=4)

        self.login_btn = tk.Button(self.auth_frame, text="Login", state=tk.DISABLED, command=self.do_login)
        self.login_btn.pack(fill=tk.X, pady=6)

        self.register_btn = tk.Button(self.auth_frame, text="Criar conta", state=tk.DISABLED, command=self.do_register)
        self.register_btn.pack(fill=tk.X)

        tk.Button(self.auth_frame, text="Preencher (atalho)", command=self.fill_demo).pack(fill=tk.X, pady=12)

        # ===== LOBBY =====
        self.lobby_frame = tk.Frame(root)

        tk.Label(self.lobby_frame, text="Salas disponíveis", font=("Arial", 14, "bold")).pack(pady=10)

        self.rooms_listbox = tk.Listbox(self.lobby_frame, height=10)
        self.rooms_listbox.pack(fill=tk.X, padx=20)

        self.create_btn = tk.Button(self.lobby_frame, text="Criar Sala", state=tk.DISABLED, command=self.create_room)
        self.create_btn.pack(fill=tk.X, padx=40, pady=5)

        self.join_btn = tk.Button(self.lobby_frame, text="Entrar na Sala", state=tk.DISABLED, command=self.join_room)
        self.join_btn.pack(fill=tk.X, padx=40)

        tk.Button(self.lobby_frame, text="Sair (logout)", command=self.logout).pack(fill=tk.X, padx=40, pady=10)

        # ===== CHAT =====
        self.chat_frame = tk.Frame(root)

        tk.Label(self.chat_frame, text="Chat", font=("Arial", 14, "bold")).pack(pady=5)

        self.chat_box = tk.Text(self.chat_frame, state="disabled", height=15)
        self.chat_box.pack(fill=tk.BOTH, padx=10, expand=True)

        self.msg_entry = tk.Entry(self.chat_frame)
        self.msg_entry.pack(fill=tk.X, padx=10, pady=5)
        self.msg_entry.bind("<Return>", self.send_message)

        tk.Button(self.chat_frame, text="Sair da Sala", command=self.leave_room).pack(fill=tk.X, padx=40, pady=5)

        # ===== WS THREAD =====
        threading.Thread(target=self.start_ws, daemon=True).start()

    # ================= WS =================

    def start_ws(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.ws_loop())

    async def ws_loop(self):
        try:
            async with websockets.connect(SERVER_URL) as ws:
                self.ws = ws
                self.root.after(0, self.enable_auth_buttons)

                async for msg in ws:
                    data = json.loads(msg)
                    self.root.after(0, self.handle_message, data)

        except Exception as e:
            self.root.after(0, lambda: self.show_error(f"Não foi possível conectar ao servidor.\n{e}"))

    def send_ws(self, data):
        if not self.ws or not self.loop:
            return
        asyncio.run_coroutine_threadsafe(self.ws.send(json.dumps(data)), self.loop)

    # ================= UI helpers =================

    def show_error(self, msg):
        messagebox.showerror("Erro", msg)

    def show_info(self, msg):
        messagebox.showinfo("Info", msg)

    def enable_auth_buttons(self):
        self.login_btn.config(state=tk.NORMAL)
        self.register_btn.config(state=tk.NORMAL)

    def append_chat(self, text):
        self.chat_box.config(state="normal")
        self.chat_box.insert(tk.END, text + "\n")
        self.chat_box.config(state="disabled")
        self.chat_box.see(tk.END)

    def go_to_auth(self):
        self.lobby_frame.pack_forget()
        self.chat_frame.pack_forget()
        self.auth_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.pass_entry.delete(0, tk.END)
        self.pass_entry.focus_set()

    def go_to_lobby(self):
        self.chat_frame.pack_forget()
        self.auth_frame.pack_forget()
        self.lobby_frame.pack(fill=tk.BOTH, expand=True)

    def go_to_chat(self):
        self.lobby_frame.pack_forget()
        self.auth_frame.pack_forget()
        self.chat_frame.pack(fill=tk.BOTH, expand=True)

    # ================= Actions =================

    def fill_demo(self):
        self.user_entry.delete(0, tk.END)
        self.pass_entry.delete(0, tk.END)
        self.user_entry.insert(0, "teste")
        self.pass_entry.insert(0, "12345")

    def do_register(self):
        u = self.user_entry.get().strip()
        p = self.pass_entry.get()
        self.send_ws({"type": "register", "user": u, "pass": p})

    def do_login(self):
        u = self.user_entry.get().strip()
        p = self.pass_entry.get()
        self.send_ws({"type": "login", "user": u, "pass": p})

    def logout(self):
        self.role = None
        self.username = None
        self.room = None
        self.create_btn.config(state=tk.DISABLED)
        self.join_btn.config(state=tk.DISABLED)
        self.go_to_auth()

    def create_room(self):
        room = simpledialog.askstring("Criar Sala", "Nome da sala:")
        if room:
            self.send_ws({"type": "create_room", "room": room})

    def join_room(self):
        selection = self.rooms_listbox.curselection()
        if not selection:
            return
        room = self.rooms_listbox.get(selection[0])
        self.send_ws({"type": "join_room", "room": room})

    def leave_room(self):
        if self.room:
            self.send_ws({"type": "leave_room", "room": self.room})
        self.room = None
        self.go_to_lobby()

    def send_message(self, event=None):
        msg = self.msg_entry.get()
        self.msg_entry.delete(0, tk.END)
        if msg and self.room:
            self.send_ws({"type": "chat", "room": self.room, "message": msg})

    # ================= Handlers =================

    def handle_message(self, data):
        t = data.get("type")

        if t == "register_ok":
            self.show_info("Conta criada. Agora faça login.")
            self.pass_entry.delete(0, tk.END)
            self.pass_entry.focus_set()

        elif t == "login_ok":
            self.role = data.get("role")
            self.username = self.user_entry.get().strip()
            self.pass_entry.delete(0, tk.END)

            self.create_btn.config(state=tk.NORMAL)
            self.join_btn.config(state=tk.NORMAL)

            self.go_to_lobby()

        elif t == "room_list":
            self.rooms_listbox.delete(0, tk.END)
            for room in data.get("rooms", []):
                self.rooms_listbox.insert(tk.END, room)

        elif t == "room_joined":
            self.room = data.get("room")
            self.chat_box.config(state="normal")
            self.chat_box.delete("1.0", tk.END)
            self.chat_box.config(state="disabled")
            self.go_to_chat()
            self.append_chat(f"Você entrou na sala: {self.room}")

        elif t in ("chat", "system"):
            if "user" in data:
                self.append_chat(f'{data["user"]}: {data["message"]}')
            else:
                self.append_chat(data.get("message", ""))

        elif t == "error":
            self.show_error(data.get("message", "Erro desconhecido"))
            if not self.role:
                self.go_to_auth()


root = tk.Tk()
app = ClientApp(root)
root.mainloop()
