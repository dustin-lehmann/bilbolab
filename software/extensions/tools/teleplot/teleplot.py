import os
import signal
import socket
import subprocess
import argparse
import shutil
import time
import sys

# UDP port Teleplot listens on for incoming datapoints
UDP_DATA_PORT = 47269
# HTTP port for the Teleplot web interface
HTTP_PORT = 9000

# Where the JS server lives, relative to this file
_TELEPLOT_DIR = os.path.join(os.path.dirname(__file__), "src", "server")
_PID_FILE = os.path.join(_TELEPLOT_DIR, "teleplot.pid")


def _install_teleplot():
    """Reinstall node modules from scratch."""
    node_mod = os.path.join(_TELEPLOT_DIR, "node_modules")
    if os.path.isdir(node_mod):
        shutil.rmtree(node_mod)
    os.chdir(_TELEPLOT_DIR)
    subprocess.run(["npm", "install"], check=True)


def _detect_host_ip():
    """
    Detect a network IP in the 192.168.x.x or 169.254.x.x range.
    Returns the first matching IPv4 address, or None if none found.
    """
    # 1) Try resolving the hostname
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("192.168."):
                return ip
        for info in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("169.254."):
                return ip
    except socket.gaierror:
        pass

    # 2) Fallback: use the default-route trick
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # doesn't actually send packets
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip.startswith("192.168.") or ip.startswith("169.254."):
            return ip
    except Exception:
        pass

    return None


def startTelePlotServer(background=False, host="localhost"):
    """
    Start the Teleplot server.

    If background=True, detaches and writes its PID to teleplot.pid.
    Otherwise, runs in the foreground (blocking).

    `host` controls what address is shown to the user (and set in the ENV for Node).
    """
    if not os.path.isdir(os.path.join(_TELEPLOT_DIR, "node_modules")):
        _install_teleplot()

    os.chdir(_TELEPLOT_DIR)
    cmd = ["node", "main.js"]
    server_url = f"http://{host}:{HTTP_PORT}"

    # Propagate HOST to the Node.js process in case the server code uses it
    env = os.environ.copy()
    env["HOST"] = host

    if background:
        if os.name == "nt":
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                env=env
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
                env=env
            )

        with open(_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        print(f"Teleplot server started in background (PID {proc.pid}).")
        print(f"Open your browser at {server_url}")
    else:
        print(f"Starting Teleplot server in foreground.")
        print(f"Open your browser at {server_url}")
        subprocess.run(cmd, check=True, env=env)


def kill_by_pid(pid: int):
    """Cross-platform kill of the Teleplot process (and its group)."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass


def closeTeleplotServers():
    """Read the PID file and terminate the background Teleplot server."""
    if not os.path.exists(_PID_FILE):
        print("No teleplot server is currently running.")
        return

    try:
        with open(_PID_FILE) as f:
            pid = int(f.read().strip())
    except Exception:
        print("PID file is malformed; deleting it.")
        os.remove(_PID_FILE)
        return

    kill_by_pid(pid)
    os.remove(_PID_FILE)
    print(f"Killed Teleplot server process (PID {pid}).")


def _send_udp(message: str):
    """Low‐level: send a raw telemetry string over UDP."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(message.encode(), ("localhost", UDP_DATA_PORT))


def send_value(
    identifier: str,
    value,
    *,
    automatic_plot: bool = True,
    use_client_timestamp: bool = False,
    unit: str = None
):
    """
    Send a single numeric or text value.
    """
    parts = [identifier]
    if use_client_timestamp:
        parts.append(str(int(time.time() * 1000)))
    parts.append(str(value))

    msg = ":".join(parts)

    # unit before flags
    if unit:
        msg += f"§{unit}"

    flags = []
    if not automatic_plot:
        flags.append("np")

    if flags:
        msg += "|" + ",".join(flags)

    _send_udp(msg)


def send_values(
    identifier: str,
    values,
    *,
    automatic_plot: bool = True,
    unit: str = None
):
    """
    Send multiple values for one telemetry in one packet.
    """
    entries = []
    for v in values:
        if isinstance(v, tuple) and len(v) == 2:
            ts, val = v
            entries.append(f"{ts}:{val}")
        else:
            entries.append(str(v))

    msg = f"{identifier}:" + ";".join(entries)

    if unit:
        msg += f"§{unit}"

    flags = []
    if not automatic_plot:
        flags.append("np")
    if flags:
        msg += "|" + ",".join(flags)

    _send_udp(msg)


def send_xy(
    identifier: str,
    x,
    y,
    *,
    automatic_plot: bool = True,
    use_client_timestamp: bool = False
):
    """
    Send one (x,y) point.
    """
    parts = [identifier, str(x), str(y)]
    if use_client_timestamp:
        parts.append(str(int(time.time() * 1000)))

    msg = ":".join(parts) + "|xy"

    if not automatic_plot:
        msg += ",np"

    _send_udp(msg)


def send_xy_series(
    identifier: str,
    points,
    *,
    automatic_plot: bool = True
):
    """
    Send multiple (x,y) points in one packet.
    """
    entries = []
    for p in points:
        if len(p) == 3:
            x, y, ts = p
            entries.append(f"{x}:{y}:{ts}")
        else:
            x, y = p
            entries.append(f"{x}:{y}")

    msg = f"{identifier}:" + ";".join(entries) + "|xy"

    if not automatic_plot:
        msg += ",np"

    _send_udp(msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Control the Teleplot server."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--background",
        action="store_true",
        help="Start server in background."
    )
    group.add_argument(
        "--close",
        action="store_true",
        help="Close any background Teleplot server."
    )
    parser.add_argument(
        "--mode",
        choices=["local", "network"],
        default="local",
        help="If 'network', attempt to detect a 192.168.x.x or 169.254.x.x IP and show that address instead of localhost."
    )
    args = parser.parse_args()

    if args.close:
        closeTeleplotServers()
    else:
        # Determine host for the UI
        if args.mode == "network":
            ip = _detect_host_ip()
            if ip is None:
                print("Error: no suitable network IP found (192.168.x.x or 169.254.x.x).")
                sys.exit(1)
        else:
            ip = "localhost"
        startTelePlotServer(background=args.background, host=ip)
