import tkinter as tk
from tkinter import simpledialog, messagebox
import threading
import asyncio
import websockets
import json

SERVER_URL = "ws://localhost:8765"


class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Truco Online")
        self.root.geometry("400x500")

        self.username = simpledialog.askstring("Login", "Digite seu nome:")
        if not self.username:
            root.destroy()
            return

        self.room = None
        self.pending_room = None
        self.ws = None
        self.loop = None

        self.lobby_frame = tk.Frame(root)
        self.lobby_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            self.lobby_frame,
            text="Salas disponíveis",
            font=("Arial", 14, "bold")
        ).pack(pady=10)

        self.rooms_listbox = tk.Listbox(self.lobby_frame, height=10)
        self.rooms_listbox.pack(fill=tk.X, padx=20)

        self.create_btn = tk.Button(
            self.lobby_frame,
            text="Criar Sala",
            state=tk.DISABLED,
            command=self.create_room
        )
        self.create_btn.pack(fill=tk.X, padx=40, pady=5)

        self.join_btn = tk.Button(
            self.lobby_frame,
            text="Entrar na Sala",
            state=tk.DISABLED,
            command=self.join_room
        )
        self.join_btn.pack(fill=tk.X, padx=40)

        self.chat_frame = tk.Frame(root)

        tk.Label(
            self.chat_frame,
            text="Chat",
            font=("Arial", 14, "bold")
        ).pack(pady=5)

        self.chat_box = tk.Text(self.chat_frame, state="disabled", height=15)
        self.chat_box.pack(fill=tk.BOTH, padx=10, expand=True)

        self.msg_entry = tk.Entry(self.chat_frame)
        self.msg_entry.pack(fill=tk.X, padx=10, pady=5)
        self.msg_entry.bind("<Return>", self.send_message)

        tk.Button(
            self.chat_frame,
            text="Sair da Sala",
            command=self.leave_room
        ).pack(fill=tk.X, padx=40, pady=5)

        threading.Thread(target=self.start_ws, daemon=True).start()


    def start_ws(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.ws_loop())

    async def ws_loop(self):
        try:
            async with websockets.connect(SERVER_URL) as ws:
                self.ws = ws

                await ws.send(json.dumps({
                    "type": "login",
                    "user": self.username
                }))

                self.root.after(0, self.enable_buttons)

                async for msg in ws:
                    data = json.loads(msg)
                    self.root.after(0, self.handle_message, data)

        except Exception as e:
            self.root.after(
                0,
                self.show_error,
                f"Não foi possível conectar ao servidor.\n{e}"
            )

    def show_error(self, msg):
        messagebox.showerror("Erro", msg)

    def enable_buttons(self):
        self.create_btn.config(state=tk.NORMAL)
        self.join_btn.config(state=tk.NORMAL)

    def append_chat(self, text):
        self.chat_box.config(state="normal")
        self.chat_box.insert(tk.END, text + "\n")
        self.chat_box.config(state="disabled")
        self.chat_box.see(tk.END)

    def go_to_chat(self):
        self.lobby_frame.pack_forget()
        self.chat_frame.pack(fill=tk.BOTH, expand=True)

    def go_to_lobby(self):
        self.chat_frame.pack_forget()
        self.lobby_frame.pack(fill=tk.BOTH, expand=True)

    def handle_message(self, data):
        msg_type = data.get("type")

        if msg_type == "room_list":
            self.rooms_listbox.delete(0, tk.END)
            for room in data.get("rooms", []):
                self.rooms_listbox.insert(tk.END, room)

        elif msg_type == "room_joined":
            self.room = data.get("room")
            self.pending_room = None
            self.chat_box.config(state="normal")
            self.chat_box.delete("1.0", tk.END)
            self.chat_box.config(state="disabled")
            self.go_to_chat()
            self.append_chat(f"Você entrou na sala: {self.room}")

        elif msg_type == "error":
            self.pending_room = None
            self.show_error(data.get("message", "Erro desconhecido"))

        elif msg_type in ("chat", "system"):
            if "user" in data:
                self.append_chat(f'{data["user"]}: {data["message"]}')
            else:
                self.append_chat(f'{data["message"]}')

    def send_ws(self, data):
        if not self.ws or not self.loop:
            return

        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps(data)),
            self.loop
        )

    def create_room(self):
        room = simpledialog.askstring("Criar Sala", "Nome da sala:")
        if room:
            self.pending_room = room
            self.send_ws({"type": "create_room", "room": room})

    def join_room(self):
        selection = self.rooms_listbox.curselection()
        if not selection:
            return

        room = self.rooms_listbox.get(selection[0])
        self.pending_room = room
        self.send_ws({"type": "join_room", "room": room})

    def leave_room(self):
        if self.room:
            self.send_ws({"type": "leave_room", "room": self.room})
        self.room = None
        self.pending_room = None
        self.go_to_lobby()

    def send_message(self, event=None):
        msg = self.msg_entry.get()
        self.msg_entry.delete(0, tk.END)

        if msg and self.room:
            self.send_ws({
                "type": "chat",
                "room": self.room,
                "message": msg
            })


root = tk.Tk()
app = ClientApp(root)
root.mainloop()
