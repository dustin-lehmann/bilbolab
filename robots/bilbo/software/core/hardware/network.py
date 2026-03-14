import getpass
import re
import socket
import os
import subprocess
import sys
import platform
import psutil


def getAllPrivateIPs():
    """
    Retrieves private IP addresses grouped by common subnet origins:
    - '192.*' (Local Wi-Fi/LAN),
    - '169.*' (USB or self-assigned),
    - '172.*' (Often WSL or Docker),
    - '10.*' (Common in enterprise/virtual setups).

    :return: A dictionary with keys: 'local_ips', 'usb_ips', 'wsl_ips', 'enterprise_ips',
             each containing a list of corresponding IP addresses.
    """
    ip_groups = {
        "local_ips": [],
        "usb_ips": [],
        "wsl_ips": [],
        "enterprise_ips": []
    }

    try:
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if ip.startswith("192."):
                        ip_groups["local_ips"].append(ip)
                    elif ip.startswith("169."):
                        ip_groups["usb_ips"].append(ip)
                    elif ip.startswith("172."):
                        ip_groups["wsl_ips"].append(ip)
                    elif ip.startswith("10."):
                        ip_groups["enterprise_ips"].append(ip)
    except Exception as e:
        print(f"Error retrieving IPs: {e}")

    return ip_groups


def getHostIP(priorities=None, interactive=False):
    """
    Selects a single host IP according to an optional priority list.

    :param priorities: List of priority categories, e.g. ['local','usb','wsl','enterprise'], or None.
    :param interactive: If True, and more than one candidate is found in the selected pool,
                        prompt the user to choose; otherwise pick the first match.
    :return: A single IP string or None.
    """
    # Validate priorities
    valid = {'local', 'usb', 'wsl', 'enterprise'}
    if priorities is not None:
        if not all(p in valid for p in priorities):
            raise ValueError(f"Invalid priority; expected subset of {valid}, got {priorities}")

    ip_data = getAllPrivateIPs()

    # Map shorthand to ip_data keys
    group_map = {
        'local': 'local_ips',
        'usb': 'usb_ips',
        'wsl': 'wsl_ips',
        'enterprise': 'enterprise_ips'
    }

    # Build the pool of candidate IPs
    if priorities:
        # Respect the order of priorities
        for p in priorities:
            candidates = ip_data.get(group_map[p], [])
            if candidates:
                chosen_group = candidates
                break
        else:
            # None of the priority groups had any IPs
            return None
    else:
        # No priorities → all IPs
        chosen_group = (
                ip_data.get('local_ips', []) +
                ip_data.get('usb_ips', []) +
                ip_data.get('wsl_ips', []) +
                ip_data.get('enterprise_ips', [])
        )
        if not chosen_group:
            return None

    # If only one, return it immediately
    if len(chosen_group) == 1 or not interactive:
        return chosen_group[0]

    # Otherwise, ask the user to choose among chosen_group
    print("Multiple matching IPs found:")
    for i, ip in enumerate(chosen_group, 1):
        print(f"  {i}) {ip}")

    while True:
        try:
            sel = int(input(f"Select an IP [1–{len(chosen_group)}]: "))
            if 1 <= sel <= len(chosen_group):
                return chosen_group[sel - 1]
        except ValueError:
            pass
        print("Invalid selection; please enter a number.")

def splitServerAddress(address: str):
    server_address = None
    server_port = None
    try:
        server_address = re.search(r'[0-9.]*(?=:)', address)[0]
    except:
        ...
    try:
        server_port = int(re.search(r'(?<=:)[0-9]*', address)[0])
    except:
        ...

    return server_address, server_port


def getAllIPAdresses():
    """

    :param debug:
    :return:
    """

    local_ip = None
    usb_ip = None

    if os.name == 'nt':

        hostname = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(hostname)[2]
        local_ips = [ip for ip in ip_addresses if ip.startswith("192.168.0")]
        if len(local_ips) == 0:
            return None

        local_ip = [ip for ip in ip_addresses if ip.startswith("192.168.0")][:1][0]
        usb_ip = ''
        server_address = socket.gethostbyname_ex(socket.gethostname())

    elif os.name == 'posix':
        hostname = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(hostname)[2]
        local_ips = [ip for ip in ip_addresses if ip.startswith("192.168.")]
        if len(local_ips) == 0:
            return None
        local_ip = [ip for ip in ip_addresses if ip.startswith("192.168.")][:1][0]
        usb_ip = ''
        server_address = socket.gethostbyname_ex(socket.gethostname())

    output = {'hostname': hostname, 'local': local_ip, 'usb': usb_ip, 'all': server_address[2]}

    for i, add in enumerate(server_address[2]):
        if add is not local_ip and add is not usb_ip:
            ...
    return output


def getLocalIP():
    """

        :param debug:
        :return:
        """

    local_ip = None
    usb_ip = None

    if os.name == 'nt':

        hostname = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(hostname)[2]
        local_ips = [ip for ip in ip_addresses if ip.startswith("192.168.0")]
        if len(local_ips) == 0:
            return None

        local_ip = [ip for ip in ip_addresses if ip.startswith("192.168.0")][:1][0]
        usb_ip = ''
        server_address = socket.gethostbyname_ex(socket.gethostname())

    elif os.name == 'posix':
        hostname = socket.gethostname()
        ip_addresses = socket.gethostbyname_ex(hostname)[2]
        local_ips = [ip for ip in ip_addresses if ip.startswith("192.168.")]
        if len(local_ips) == 0:
            return None
        local_ip = [ip for ip in ip_addresses if ip.startswith("192.168.")][:1][0]
        usb_ip = ''
        server_address = socket.gethostbyname_ex(socket.gethostname())

    return local_ip


def is_ipv4(address):
    """Check if the provided address is a valid IPv4 address."""
    try:
        socket.inet_aton(address)
        return True
    except socket.error:
        return False


def ipv4_to_bytes(ipv4_str):
    """Encode an IPv4 string into 4 bytes."""
    if not is_ipv4(ipv4_str):
        raise ValueError("Invalid IPv4 address.")
    # Use socket library to pack the IPv4 string into 4 bytes
    return socket.inet_aton(ipv4_str)


def bytes_to_ipv4(byte_data):
    """Decode 4 bytes back into an IPv4 string."""
    if len(byte_data) != 4:
        raise ValueError("Invalid byte length for IPv4 address.")
    # Use socket library to unpack the bytes back into a string
    return socket.inet_ntoa(byte_data)


def resolve_hostname(hostname, check_availability=False):
    """Resolve a hostname to an IP address and check its network availability.

    Args:
        hostname (str): The hostname to resolve.
        check_availability (bool): Whether to check if the host is reachable on the network.

    Returns:
        str: The IP address of the hostname, or an error message if unreachable.
    """
    try:
        # Step 1: Resolve the hostname to an IP address
        ip_address = socket.gethostbyname(hostname)

        # Step 2: Optionally check if the host is available on the network
        if check_availability:
            if is_host_reachable(ip_address):
                return f"{hostname} is available at IP: {ip_address}"
            else:
                return f"{hostname} resolved to {ip_address}, but is not reachable on the network."

        return ip_address

    except socket.gaierror:
        return None


def is_host_reachable(ip_address):
    """Ping the IP address to check if it is reachable on the network."""
    # Use different commands depending on the operating system
    param = "-n" if platform.system().lower() == "windows" else "-c"
    command = ["ping", param, "1", ip_address]

    try:
        # Send the ping command and check for a successful response
        response = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return response.returncode == 0
    except Exception as e:
        print(f"An error occurred while pinging: {e}")
        return False


def get_hostname(ip_address):
    # hostname, _, _ = socket.gethostbyaddr(ip_address)
    # return hostname
    # """Resolve an IP address to a hostname.
    #
    # Args:
    #     ip_address (str): The IP address to resolve.
    #
    # Returns:
    #     str: The hostname associated with the IP address, or an error message if not found.
    # """
    try:
        # Perform a reverse DNS lookup
        hostname, _, _ = socket.gethostbyaddr(ip_address)
        return hostname
    except socket.herror:
        return None
    except socket.gaierror:
        return None
    except Exception as e:
        return None


def getIPAdress(address):
    # Check if the address is a valid IPv4 String:
    if is_ipv4(address):
        return address
    else:
        return resolve_hostname(address)


def getLocalIP_RPi():
    network_information = getNetworkInformation()

    if network_information['local_ip'] is not None:
        return network_information['local_ip']
    elif network_information['usb_ip'] is not None:
        return network_information['usb_ip']

    # Fallback: use psutil-based lookup (works on Mac/Linux)
    return getHostIP(priorities=['local', 'enterprise'])


def get_current_user():
    """
    Returns the name of the currently logged-in user.
    """
    return getpass.getuser()


def get_own_hostname():
    hostname = socket.gethostname()
    return hostname


def get_wifi_ssid():
    try:
        # Get the SSID of the current Wi-Fi network
        ssid = subprocess.check_output(['/sbin/iwgetid', '-r']).decode().rstrip()
        if ssid == '':
            ssid = None
    except Exception:
        ssid = None

    return ssid


def check_internet(timeout=0.25):
    """
    Checks if the device has internet connectivity by pinging 8.8.8.8.

    :param timeout: Timeout in seconds for the ping command.
    :return: True if the device can ping 8.8.8.8, False otherwise.
    """
    try:
        # Use subprocess to ping 8.8.8.8 with a single packet and specified timeout
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), "8.8.8.8"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0  # Return True if ping was successful (returncode 0)
    except Exception as e:
        print(f"Error while checking internet connectivity: {e}")
        return False


def getNetworkInformation():
    try:
        # Get the username from the /home directory
        usernames = os.listdir('/home/')
        username = usernames[0] if usernames else None
    except Exception:
        username = None

    try:
        # Get the hostname of the device
        hostname = socket.gethostname()
    except Exception:
        hostname = None

    try:
        # Get the SSID of the current Wi-Fi network
        ssid = subprocess.check_output(['/sbin/iwgetid', '-r']).decode().rstrip()
        if ssid == '':
            ssid = None
    except Exception:
        ssid = None

    try:
        # Get the list of IP addresses (hostname -I is Linux-only)
        ip_string = subprocess.check_output(['hostname', '-I'], stderr=subprocess.DEVNULL).decode()
        ips = re.findall(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', ip_string)

        # Separate IPs into local and USB IPs
        local_ips = [ip for ip in ips if ip.startswith('192.')]
        usb_ips = [ip for ip in ips if ip.startswith('169.')]

        # Use the first local IP or set to None if not found
        local_ip = local_ips[0] if local_ips else None

        usb_ips = usb_ips[0] if usb_ips else None

    except Exception:
        local_ip = None
        usb_ips = None

    return {
        "username": username,
        "hostname": hostname,
        "ssid": ssid,
        "local_ip": local_ip,
        "usb_ip": usb_ips
    }


# === GET SIGNAL STRENGTH ===============================================================================================
def getSignalStrength(interface: str):
    """
    Return Wi-Fi signal strength for the given interface.

    Tries multiple backends depending on OS:
      - Linux: `iw dev <iface> link` (preferred), then `iwconfig <iface>`
      - macOS: `airport -I`
      - Windows: `netsh wlan show interfaces`

    Args:
        interface (str): Wireless interface name, e.g. 'wlan0' on Linux or 'Wi-Fi' on Windows.
                         On macOS the system utility doesn't take an interface argument, so it's ignored.

    Returns:
        dict: {
            'dbm': Optional[int], # RSSI in dBm (negative number, e.g. -45). None if unavailable.
            'percent': Optional[int], # Signal as 0..100. None if unavailable.
            'source': str # Which method produced the reading.
        }
        If no reading could be obtained, returns {'dbm': None, 'percent': None, 'source': 'unavailable'}.
    """
    import subprocess, re, shutil, os, platform
    system = platform.system().lower()

    def _run(cmd):
        try:
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode(errors="ignore")
        except Exception:
            return ""

    # --- Linux (iw / iwconfig / nmcli as last resort for percent) ---
    if system == "linux":
        # Prefer `iw` if present (modern).
        iw_path = shutil.which("iw") or ("/sbin/iw" if os.path.exists("/sbin/iw") else None)
        if iw_path:
            out = _run([iw_path, "dev", interface, "link"])
            # Example line: "signal: -45 dBm"
            m = re.search(r"signal:\s*(-?\d+)\s*dBm", out)
            if m:
                dbm = int(m.group(1))
                # Map dBm to a rough percentage (typical heuristic: -30dBm≈100, -90dBm≈0)
                pct = max(0, min(100, int((dbm + 90) * (100 / 60))))  # linear between -90 and -30
                return {'dbm': dbm, 'percent': pct, 'source': 'iw'}

        # Fallback: `iwconfig`
        iwc_path = shutil.which("iwconfig") or ("/sbin/iwconfig" if os.path.exists("/sbin/iwconfig") else None)
        if iwc_path:
            out = _run([iwc_path, interface])
            # Look for "Signal level=-45 dBm" or "Signal level=-45/100"
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

        # Last resort on Linux: `nmcli` (gives percent for visible networks)
        nmcli = shutil.which("nmcli")
        if nmcli:
            # This shows the currently connected network marked with '*'
            out = _run([nmcli, "-t", "-f", "IN-USE,DEVICE,SIGNAL", "dev", "wifi"])
            # Lines like: "*:wlan0:80"
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
