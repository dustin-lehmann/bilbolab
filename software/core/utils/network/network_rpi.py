"""
RPi-specific network utilities (Linux-only commands like iwgetid, hostname -I).
"""
import getpass
import os
import re
import socket
import subprocess

from core.utils.network.network import getHostIP


def getLocalIP_RPi():
    """Get the local IP on a Raspberry Pi, preferring Wi-Fi, then USB, then psutil fallback."""
    network_information = getNetworkInformation()

    if network_information['local_ip'] is not None:
        return network_information['local_ip']
    elif network_information['usb_ip'] is not None:
        return network_information['usb_ip']

    # Fallback: use psutil-based lookup (works on Mac/Linux)
    return getHostIP(priorities=['local', 'enterprise'])


def getNetworkInformation():
    """Gather network info using Linux-specific commands (hostname -I, iwgetid)."""
    try:
        usernames = os.listdir('/home/')
        username = usernames[0] if usernames else None
    except Exception:
        username = None

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = None

    try:
        ssid = subprocess.check_output(['/sbin/iwgetid', '-r']).decode().rstrip()
        if ssid == '':
            ssid = None
    except Exception:
        ssid = None

    try:
        ip_string = subprocess.check_output(['hostname', '-I'], stderr=subprocess.DEVNULL).decode()
        ips = re.findall(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', ip_string)

        local_ips = [ip for ip in ips if ip.startswith('192.')]
        usb_ips = [ip for ip in ips if ip.startswith('169.')]

        local_ip = local_ips[0] if local_ips else None
        usb_ip = usb_ips[0] if usb_ips else None
    except Exception:
        local_ip = None
        usb_ip = None

    return {
        "username": username,
        "hostname": hostname,
        "ssid": ssid,
        "local_ip": local_ip,
        "usb_ip": usb_ip
    }


def get_wifi_ssid():
    """Get the current Wi-Fi SSID (Linux only, uses iwgetid)."""
    try:
        ssid = subprocess.check_output(['/sbin/iwgetid', '-r']).decode().rstrip()
        if ssid == '':
            ssid = None
    except Exception:
        ssid = None
    return ssid


def get_current_user():
    return getpass.getuser()


def get_own_hostname():
    return socket.gethostname()


def getSignalStrength(interface: str):
    """
    Return Wi-Fi signal strength for the given interface.

    Returns:
        dict with 'dbm', 'percent', 'source' keys.
    """
    import shutil
    import platform
    system = platform.system().lower()

    def _run(cmd):
        try:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode(errors="ignore")
        except Exception:
            return ""

    if system == "linux":
        iw_path = shutil.which("iw") or ("/sbin/iw" if os.path.exists("/sbin/iw") else None)
        if iw_path:
            out = _run([iw_path, "dev", interface, "link"])
            m = re.search(r"signal:\s*(-?\d+)\s*dBm", out)
            if m:
                dbm = int(m.group(1))
                pct = max(0, min(100, int((dbm + 90) * (100 / 60))))
                return {'dbm': dbm, 'percent': pct, 'source': 'iw'}

        iwc_path = shutil.which("iwconfig") or ("/sbin/iwconfig" if os.path.exists("/sbin/iwconfig") else None)
        if iwc_path:
            out = _run([iwc_path, interface])
            m_dbm = re.search(r"Signal level[=\s:]*(-?\d+)\s*dBm", out, re.IGNORECASE)
            m_frac = re.search(r"Link Quality[=\s:]*([0-9]+)/([0-9]+)", out, re.IGNORECASE)
            dbm = int(m_dbm.group(1)) if m_dbm else None
            pct = None
            if m_frac:
                num, den = int(m_frac.group(1)), int(m_frac.group(2))
                if den > 0:
                    pct = max(0, min(100, int(round(100 * num / den))))
            if dbm is not None and pct is None:
                pct = max(0, min(100, int((dbm + 90) * (100 / 60))))
            if dbm is not None or pct is not None:
                return {'dbm': dbm, 'percent': pct, 'source': 'iwconfig'}

        nmcli = shutil.which("nmcli")
        if nmcli:
            out = _run([nmcli, "-t", "-f", "IN-USE,DEVICE,SIGNAL", "dev", "wifi"])
            for line in out.splitlines():
                parts = line.strip().split(":")
                if len(parts) >= 3:
                    inuse, dev, signal = parts[0], parts[1], parts[2]
                    if dev == interface and inuse == "*":
                        try:
                            pct = int(signal)
                            return {'dbm': None, 'percent': max(0, min(100, pct)), 'source': 'nmcli'}
                        except ValueError:
                            pass

    return {'dbm': None, 'percent': None, 'source': 'unavailable'}
