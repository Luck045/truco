import asyncio
import json
import os
import time
import base64
import hashlib
import hmac
import secrets
import websockets

from database import (
    create_tables,
    ensure_schema_or_raise,
    create_user,
    get_user_by_username,
)

HOST = "localhost"  # Bloco 3 muda
PORT = int(os.environ.get("PORT", "8765"))

USERNAME_MIN = 3
USERNAME_MAX = 20

PASSWORD_MIN = 5
PASSWORD_MAX = 20  # se quiser, mude para 64

ROOM_MIN = 1
ROOM_MAX = 24

CHAT_MIN = 1
CHAT_MAX = 200
CHAT_COOLDOWN_SECONDS = 0.35

PBKDF2_ITERS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERS)
    return "pbkdf2_sha256$%d$%s$%s" % (
        PBKDF2_ITERS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        alg, iters_s, salt_b64, dk_b64 = stored.split("$", 3)
        if alg != "pbkdf2_sha256":
            return False
        iters = int(iters_s)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(dk_b64.encode("ascii"))
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def log(msg):
    print(f"[SERVER] {msg}")


def _clean(s: str) -> str:
    return (s or "").strip()


def validate_len(field: str, value: str, min_len: int, max_len: int) -> str | None:
    if not (min_len <= len(value) <= max_len):
        return f"{field} deve ter entre {min_len} e {max_len} caracteres"
    return None


async def safe_send(ws, data: dict):
    try:
        await ws.send(json.dumps(data))
        return True
    except:
        return False


# ----- DB init -----
create_tables()
try:
    ensure_schema_or_raise()
except RuntimeError as e:
    log(str(e))
    raise SystemExit(1)

# ----- estado -----
rooms = {}
clients = set()
conn_info = {}  # ws -> {"authed","username","role","room","last_chat"}

# ----- bootstrap dono (cria 1 admin no primeiro run) -----
OWNER_BOOTSTRAP_USER = os.environ.get("OWNER_BOOTSTRAP_USER", "").strip()
OWNER_BOOTSTRAP_PASS = os.environ.get("OWNER_BOOTSTRAP_PASS", "")

if OWNER_BOOTSTRAP_USER and OWNER_BOOTSTRAP_PASS:
    row = get_user_by_username(OWNER_BOOTSTRAP_USER)
    if not row:
        created = create_user(
            OWNER_BOOTSTRAP_USER,
            hash_password(OWNER_BOOTSTRAP_PASS),
            role="admin",
        )
        if created:
            log(f"Admin bootstrap criado: {OWNER_BOOTSTRAP_USER}")
        else:
            log("Falha ao criar admin bootstrap (username já existe?)")
    else:
        log("Admin bootstrap não criado (já existe).")


async def broadcast_room_list():
    payload = {"type": "room_list", "rooms": list(rooms.keys())}
    dead = []
    for ws in list(clients):
        ok = await safe_send(ws, payload)
        if not ok:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)
        conn_info.pop(ws, None)


async def broadcast(room_name: str, data: dict):
    room = rooms.get(room_name)
    if not room:
        return
    dead = []
    for ws in list(room["connections"]):
        ok = await safe_send(ws, data)
        if not ok:
            dead.append(ws)
    for ws in dead:
        room["connections"].discard(ws)
        clients.discard(ws)
        conn_info.pop(ws, None)


async def leave_room(ws):
    info = conn_info.get(ws)
    if not info:
        return
    room_name = info.get("room")
    username = info.get("username")
    if not room_name or room_name not in rooms or not username:
        info["room"] = None
        return

    rooms[room_name]["users"].discard(username)
    rooms[room_name]["connections"].discard(ws)
    info["room"] = None

    await broadcast(room_name, {"type": "system", "message": f"{username} saiu da sala"})

    if not rooms[room_name]["users"]:
        del rooms[room_name]

    await broadcast_room_list()


def is_admin(ws) -> bool:
    info = conn_info.get(ws) or {}
    return info.get("role") == "admin"


async def handle_register(ws, data):
    username = _clean(data.get("user"))
    password = data.get("pass") or ""

    err = (
        validate_len("Usuário", username, USERNAME_MIN, USERNAME_MAX)
        or validate_len("Senha", password, PASSWORD_MIN, PASSWORD_MAX)
    )
    if err:
        await safe_send(ws, {"type": "error", "message": err})
        return

    ok = create_user(username, hash_password(password), role="user")
    if not ok:
        await safe_send(ws, {"type": "error", "message": "Não foi possível criar a conta"})
        return

    await safe_send(ws, {"type": "register_ok"})


async def handle_login(ws, data):
    username = _clean(data.get("user"))
    password = data.get("pass") or ""

    err = (
        validate_len("Usuário", username, USERNAME_MIN, USERNAME_MAX)
        or validate_len("Senha", password, PASSWORD_MIN, PASSWORD_MAX)
    )
    if err:
        await safe_send(ws, {"type": "error", "message": err})
        return

    row = get_user_by_username(username)
    if not row:
        await safe_send(ws, {"type": "error", "message": "Login inválido"})
        return

    user_id, username_db, password_hash, role = row
    if not verify_password(password, password_hash):
        await safe_send(ws, {"type": "error", "message": "Login inválido"})
        return

    conn_info[ws]["authed"] = True
    conn_info[ws]["username"] = username_db
    conn_info[ws]["role"] = role

    await safe_send(ws, {"type": "login_ok", "role": role})
    await broadcast_room_list()


# ----- comandos admin -----
async def admin_list_rooms(ws):
    if not is_admin(ws):
        await safe_send(ws, {"type": "error", "message": "Sem permissão"})
        return
    payload = []
    for name, room in rooms.items():
        payload.append({"room": name, "users": sorted(list(room["users"]))})
    await safe_send(ws, {"type": "admin_rooms", "rooms": payload})


async def admin_close_room(ws, room_name: str):
    if not is_admin(ws):
        await safe_send(ws, {"type": "error", "message": "Sem permissão"})
        return
    room = rooms.get(room_name)
    if not room:
        await safe_send(ws, {"type": "error", "message": "Sala não existe"})
        return

    await broadcast(room_name, {"type": "system", "message": "Sala fechada pelo admin"})
    for cws in list(room["connections"]):
        info = conn_info.get(cws)
        if info:
            info["room"] = None
    del rooms[room_name]
    await broadcast_room_list()
    await safe_send(ws, {"type": "admin_ok", "message": f"Sala '{room_name}' fechada"})


async def admin_kick_user(ws, room_name: str, username: str):
    if not is_admin(ws):
        await safe_send(ws, {"type": "error", "message": "Sem permissão"})
        return
    room = rooms.get(room_name)
    if not room:
        await safe_send(ws, {"type": "error", "message": "Sala não existe"})
        return

    target_ws = None
    for cws in list(room["connections"]):
        info = conn_info.get(cws) or {}
        if info.get("username") == username:
            target_ws = cws
            break

    if not target_ws:
        await safe_send(ws, {"type": "error", "message": "Usuário não encontrado nessa sala"})
        return

    room["users"].discard(username)
    room["connections"].discard(target_ws)
    if conn_info.get(target_ws):
        conn_info[target_ws]["room"] = None

    await safe_send(target_ws, {"type": "system", "message": "Você foi removido da sala pelo admin"})
    await broadcast(room_name, {"type": "system", "message": f"{username} foi removido pelo admin"})
    if not room["users"]:
        del rooms[room_name]
    await broadcast_room_list()
    await safe_send(ws, {"type": "admin_ok", "message": f"Kick em {username} da sala {room_name} realizado"})


async def handler(ws):
    clients.add(ws)
    conn_info[ws] = {"authed": False, "username": None, "role": None, "room": None, "last_chat": 0.0}
    log("Cliente conectado")

    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await safe_send(ws, {"type": "error", "message": "JSON inválido"})
                continue

            t = data.get("type")

            if t == "register":
                await handle_register(ws, data)
                continue

            if t == "login":
                await handle_login(ws, data)
                continue

            if not conn_info[ws]["authed"]:
                await safe_send(ws, {"type": "error", "message": "Faça login primeiro"})
                continue

            username = conn_info[ws]["username"]

            # ---- admin endpoints ----
            if t == "admin_list_rooms":
                await admin_list_rooms(ws)
                continue
            if t == "admin_close_room":
                await admin_close_room(ws, _clean(data.get("room")))
                continue
            if t == "admin_kick":
                await admin_kick_user(ws, _clean(data.get("room")), _clean(data.get("user")))
                continue

            # ---- normal rooms/chat ----
            if t == "create_room":
                room_name = _clean(data.get("room"))
                err = validate_len("Sala", room_name, ROOM_MIN, ROOM_MAX)
                if err:
                    await safe_send(ws, {"type": "error", "message": err})
                    continue
                if conn_info[ws]["room"] and conn_info[ws]["room"] != room_name:
                    await leave_room(ws)

                rooms.setdefault(room_name, {"users": set(), "connections": set()})
                rooms[room_name]["users"].add(username)
                rooms[room_name]["connections"].add(ws)
                conn_info[ws]["room"] = room_name

                await safe_send(ws, {"type": "room_joined", "room": room_name})
                await broadcast_room_list()
                continue

            if t == "join_room":
                room_name = _clean(data.get("room"))
                if room_name not in rooms:
                    await safe_send(ws, {"type": "error", "message": "Sala não existe"})
                    continue
                if conn_info[ws]["room"] and conn_info[ws]["room"] != room_name:
                    await leave_room(ws)

                rooms[room_name]["users"].add(username)
                rooms[room_name]["connections"].add(ws)
                conn_info[ws]["room"] = room_name

                await safe_send(ws, {"type": "room_joined", "room": room_name})
                await broadcast(room_name, {"type": "system", "message": f"{username} entrou na sala"})
                continue

            if t == "leave_room":
                await leave_room(ws)
                continue

            if t == "chat":
                room_name = _clean(data.get("room"))
                msg = _clean(data.get("message"))

                if not conn_info[ws]["room"]:
                    await safe_send(ws, {"type": "error", "message": "Você não está em uma sala"})
                    continue
                if room_name != conn_info[ws]["room"]:
                    await safe_send(ws, {"type": "error", "message": "Você não está nessa sala"})
                    continue

                err = validate_len("Mensagem", msg, CHAT_MIN, CHAT_MAX)
                if err:
                    await safe_send(ws, {"type": "error", "message": err})
                    continue

                now = time.time()
                if now - conn_info[ws]["last_chat"] < CHAT_COOLDOWN_SECONDS:
                    await safe_send(ws, {"type": "error", "message": "Envie mensagens mais devagar"})
                    continue
                conn_info[ws]["last_chat"] = now

                await broadcast(room_name, {"type": "chat", "user": username, "message": msg})
                continue

            await safe_send(ws, {"type": "error", "message": "Tipo de mensagem desconhecido"})

    except websockets.exceptions.ConnectionClosed:
        log("Cliente desconectado")
    finally:
        try:
            await leave_room(ws)
        except:
            pass
        clients.discard(ws)
        conn_info.pop(ws, None)
        try:
            await broadcast_room_list()
        except:
            pass


async def main():
    log(f"Iniciando servidor em ws://{HOST}:{PORT}")
    try:
        async with websockets.serve(handler, HOST, PORT):
            log("Servidor rodando.")
            await asyncio.Future()
    except OSError as e:
        log(f"Não foi possível iniciar (porta ocupada?): {e}")


asyncio.run(main())
