import asyncio
import socket
import threading
import websockets

ESP32_UDP_PORT = 8888      # ESP32 sends UDP packets here
WS_PORT = 8765             # browser connects here via WebSocket

clients = set()
loop = None   # asyncio event loop, set in main()


# ── WebSocket handlers ────────────────────────────────────────────────────────

async def ws_handler(websocket):
    clients.add(websocket)
    print(f"Browser connected: {websocket.remote_address}")
    try:
        await websocket.wait_closed()
    finally:
        clients.discard(websocket)
        print(f"Browser disconnected: {websocket.remote_address}")


async def broadcast(data: bytes):
    """Send audio chunk to every connected browser WebSocket."""
    if not clients:
        return
    dead = []
    for ws in list(clients):
        try:
            await ws.send(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


# ── UDP listener (runs in a background thread) ────────────────────────────────

def udp_listener():
    """Receive UDP packets from ESP32 and forward them to WebSocket clients."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", ESP32_UDP_PORT))
    print(f"UDP server listening on :{ESP32_UDP_PORT} for ESP32")

    last_addr = None
    while True:
        try:
            data, addr = sock.recvfrom(4096)   # 512 int16 = 1024 bytes
            if addr != last_addr:
                last_addr = addr
                print(f"ESP32 packets arriving from {addr}")

            # ensure even byte count for int16
            if len(data) % 2 != 0:
                data += b"\x00"

            # schedule broadcast on the asyncio event loop from this thread
            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(broadcast(data), loop)

        except Exception as e:
            print(f"UDP error: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    global loop
    loop = asyncio.get_running_loop()

    # Start UDP listener in a daemon thread
    t = threading.Thread(target=udp_listener, daemon=True)
    t.start()

    ws_server = await websockets.serve(ws_handler, "0.0.0.0", WS_PORT)
    print(f"WebSocket server at ws://localhost:{WS_PORT}/ for browser")
    print("Waiting for ESP32 UDP audio and browser connections...\n")

    await ws_server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())

