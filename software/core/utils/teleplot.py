import os
import socket

open_socket = None
host = os.environ.get('TELEPLOT_HOST', 'localhost')
port = int(os.environ.get('TELEPLOT_PORT', '47269'))


def sendValue(name, value):
    global open_socket
    if open_socket is None:
        open_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    open_socket.sendto(f"{name}:{value}".encode(), (host, port))
