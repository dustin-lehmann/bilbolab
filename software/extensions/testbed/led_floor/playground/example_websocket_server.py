import json
import random
import socket
import threading
import time

from core.utils.network import getHostIP
from core.utils.websockets import WebsocketServer

NUM_TILES = 4
UDP_DISCOVERY_PORT = 4210
WS_PORT = 8080


def generate_led_data():
    tiles = {}
    for tile_id in range(NUM_TILES):
        tiles[f"tile_{tile_id}"] = {
            "r": random.randint(0, 255),
            "g": random.randint(0, 255),
            "b": random.randint(0, 255),
        }
    return {"tiles": tiles}


def udp_broadcast_loop(host_ip, ws_port, interval=1.0):
    """Broadcast server info via UDP so ESP32 boards can discover us."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    message = json.dumps({"host": host_ip, "port": ws_port}).encode()
    print(f"[UDP] Broadcasting discovery on port {UDP_DISCOVERY_PORT}: {message.decode()}")
    while True:
        sock.sendto(message, ("<broadcast>", UDP_DISCOVERY_PORT))
        time.sleep(interval)


def example_websocket_server():
    host_ip = getHostIP()
    server = WebsocketServer(host=host_ip, port=WS_PORT, heartbeats=False)

    def new_client_callback(client):
        print(f"New client connected: {client.address}")

    def message_callback(client, message):
        print(f"Message received from {client.address}: {message}")

    server.start()

    server.callbacks.new_client.register(new_client_callback)
    server.callbacks.message.register(message_callback)

    # Start UDP discovery broadcast
    threading.Thread(target=udp_broadcast_loop, args=(host_ip, WS_PORT), daemon=True).start()

    while True:
        data = generate_led_data()

        for client in server.clients:
            print(f"Sending data to client...")
            client.send(data)

        time.sleep(1)


if __name__ == '__main__':
    example_websocket_server()
