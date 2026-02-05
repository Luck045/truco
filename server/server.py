import asyncio
import websockets
import json
from database import create_tables, get_or_create_user

create_tables()

rooms = {}     
clients = set() 


def log(msg):
    print(f"[SERVER] {msg}")


async def safe_send(ws, data: dict):
    try:
        await ws.send(json.dumps(data))
        return True
    except:
        return False


async def send_room_list(ws):
    await safe_send(ws, {
        "type": "room_list",
        "rooms": list(rooms.keys())
    })


async def broadcast_room_list():
    payload = {
        "type": "room_list",
        "rooms": list(rooms.keys())
    }
    dead = []
    for ws in list(clients):
        ok = await safe_send(ws, payload)
        if not ok:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


async def broadcast(room_name, data):
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


async def leave_room_internal(websocket, username, room_name, *, announce=True):
    room = rooms.get(room_name)
    if not room:
        return

    room["users"].discard(username)
    room["connections"].discard(websocket)

    if announce:
        await broadcast(room_name, {
            "type": "system",
            "message": f"{username} saiu da sala"
        })

    if not room["users"]:
        del rooms[room_name]

    await broadcast_room_list()


async def handler(websocket):
    clients.add(websocket)

    username = None
    current_room = None
    log("Novo cliente conectado")

    try:
        async for message in websocket:
            log(f"Mensagem recebida: {message}")
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                await safe_send(websocket, {"type": "error", "message": "JSON inválido"})
                continue

            msg_type = data.get("type")

            if msg_type == "login":
                username = (data.get("user") or "").strip()
                if not username:
                    await safe_send(websocket, {"type": "error", "message": "Usuário inválido"})
                    continue

                get_or_create_user(username)
                await safe_send(websocket, {"type": "login_ok"})
                await send_room_list(websocket)
                log(f"Usuário logado: {username}")

            elif msg_type == "create_room":
                if not username:
                    await safe_send(websocket, {"type": "error", "message": "Faça login primeiro"})
                    continue

                room_name = (data.get("room") or "").strip()
                if not room_name:
                    await safe_send(websocket, {"type": "error", "message": "Nome da sala inválido"})
                    continue

                if current_room and current_room != room_name:
                    await leave_room_internal(websocket, username, current_room, announce=False)
                    current_room = None

                rooms.setdefault(room_name, {"users": set(), "connections": set()})
                rooms[room_name]["users"].add(username)
                rooms[room_name]["connections"].add(websocket)
                current_room = room_name

                await safe_send(websocket, {"type": "room_joined", "room": room_name})
                await broadcast_room_list()
                log(f"{username} criou/entrou na sala {room_name}")

            elif msg_type == "join_room":
                if not username:
                    await safe_send(websocket, {"type": "error", "message": "Faça login primeiro"})
                    continue

                room_name = (data.get("room") or "").strip()
                if room_name not in rooms:
                    await safe_send(websocket, {"type": "error", "message": "Sala não existe"})
                    continue

                if current_room and current_room != room_name:
                    await leave_room_internal(websocket, username, current_room, announce=False)
                    current_room = None

                rooms[room_name]["users"].add(username)
                rooms[room_name]["connections"].add(websocket)
                current_room = room_name

                await safe_send(websocket, {"type": "room_joined", "room": room_name})
                await broadcast(room_name, {"type": "system", "message": f"{username} entrou na sala"})
                log(f"{username} entrou na sala {room_name}")

            elif msg_type == "chat":
                if not username:
                    await safe_send(websocket, {"type": "error", "message": "Faça login primeiro"})
                    continue

                room_name = data.get("room")
                text = (data.get("message") or "").strip()

                if not current_room:
                    await safe_send(websocket, {"type": "error", "message": "Você não está em uma sala"})
                    continue

                if room_name != current_room:
                    await safe_send(websocket, {"type": "error", "message": "Você não está nessa sala"})
                    continue

                if not text:
                    continue

                await broadcast(current_room, {
                    "type": "chat",
                    "user": username,
                    "message": text
                })

            elif msg_type == "leave_room":
                if not username:
                    continue

                room_name = data.get("room")
                if current_room and room_name == current_room:
                    await leave_room_internal(websocket, username, current_room, announce=True)
                    current_room = None

            else:
                await safe_send(websocket, {"type": "error", "message": "Tipo de mensagem desconhecido"})

    except websockets.exceptions.ConnectionClosed:
        log("Cliente desconectado")

    finally:
        clients.discard(websocket)

        if username and current_room:
            await leave_room_internal(websocket, username, current_room, announce=False)


async def main():
    log("Iniciando servidor...")
    async with websockets.serve(handler, "localhost", 8765):
        log("Servidor rodando em ws://localhost:8765")
        await asyncio.Future()


asyncio.run(main())
