"""
OpenWRT Integration Client
Fetches statistics and client info from OpenWRT router via LUCI API.

To enable on OpenWRT:
1. Install luci-mod-rpc: opkg install luci-mod-rpc
2. Enable RPC: uci set luci.main.rpc=1 && uci commit luci
3. Or use REST API if available (newer versions)

Alternative: Install statistics packages:
- opkg update
- opkg install luci-app-statistics collectd collectd-mod-network collectd-mod-interface
"""

import json
import threading
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Callable
import urllib.request
import urllib.parse


@dataclass
class OpenWRTClient:
    """Represents a client connected to the OpenWRT router."""
    mac: str
    ip: str = ""
    hostname: str = ""
    interface: str = ""
    ssid: str = ""  # SSID of the AP the client is connected to
    connected: bool = True
    signal_strength: int = 0  # dBm for wireless clients
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_rate: int = 0  # bps
    tx_rate: int = 0  # bps
    connected_time: int = 0  # seconds

    def to_dict(self) -> dict:
        return {
            'mac': self.mac,
            'ip': self.ip,
            'hostname': self.hostname or self.ip or self.mac,
            'interface': self.interface,
            'ssid': self.ssid,
            'connected': self.connected,
            'signal_strength': self.signal_strength,
            'rx_bytes': self.rx_bytes,
            'tx_bytes': self.tx_bytes,
            'rx_rate_mbps': round(self.rx_rate / 1_000_000, 2),
            'tx_rate_mbps': round(self.tx_rate / 1_000_000, 2),
            'connected_time': self.connected_time,
            'is_wireless': self.signal_strength != 0
        }


@dataclass
class WirelessNetwork:
    """Represents a wireless network on the router."""
    ssid: str
    ifname: str = ""
    mode: str = ""  # "ap" (access point) or "sta" (client/station)
    channel: int = 0
    frequency: int = 0  # MHz
    signal: int = 0  # dBm (for sta mode - signal from upstream AP)
    connected: bool = False  # For sta mode - whether connected to upstream
    bssid: str = ""  # For sta mode - BSSID of upstream AP

    def to_dict(self) -> dict:
        return {
            'ssid': self.ssid,
            'ifname': self.ifname,
            'mode': self.mode,
            'channel': self.channel,
            'frequency': self.frequency,
            'signal': self.signal,
            'connected': self.connected,
            'bssid': self.bssid,
            'is_ap': self.mode in ('ap', 'master'),
            'is_client': self.mode in ('sta', 'client')
        }


@dataclass
class OpenWRTStats:
    """Router statistics."""
    hostname: str = ""
    model: str = ""
    firmware: str = ""
    uptime: int = 0
    load_avg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    memory_total: int = 0
    memory_free: int = 0
    memory_buffered: int = 0
    connected_clients: int = 0
    wireless_clients: int = 0
    interfaces: dict = field(default_factory=dict)
    clients: list[OpenWRTClient] = field(default_factory=list)
    wireless_networks: list[WirelessNetwork] = field(default_factory=list)
    router_online: bool = False
    last_error: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            'hostname': self.hostname,
            'model': self.model,
            'firmware': self.firmware,
            'uptime_hours': round(self.uptime / 3600, 2),
            'load_avg': [round(x, 2) for x in self.load_avg],
            'memory_total_mb': round(self.memory_total / (1024 * 1024), 1),
            'memory_free_mb': round(self.memory_free / (1024 * 1024), 1),
            'memory_percent': round((self.memory_total - self.memory_free) / self.memory_total * 100, 1) if self.memory_total > 0 else 0,
            'connected_clients': self.connected_clients,
            'wireless_clients': self.wireless_clients,
            'interfaces': self.interfaces,
            'clients': [c.to_dict() for c in self.clients],
            'wireless_networks': [w.to_dict() for w in self.wireless_networks],
            'ap_networks': [w.to_dict() for w in self.wireless_networks if w.mode in ('ap', 'master')],
            'sta_networks': [w.to_dict() for w in self.wireless_networks if w.mode in ('sta', 'client')],
            'router_online': self.router_online,
            'last_error': self.last_error,
            'timestamp': self.timestamp
        }


class OpenWRTIntegration:
    """
    Integrates with OpenWRT router to get network statistics.

    Supports multiple methods:
    1. LUCI RPC API (requires luci-mod-rpc)
    2. ubus over HTTP (requires uhttpd-mod-ubus)
    3. SSH commands (fallback)
    """

    def __init__(
        self,
        router_ip: str = "192.168.1.1",
        username: str = "root",
        password: str = "",
        poll_interval: float = 10.0
    ):
        self.router_ip = router_ip
        self.username = username
        self.password = password
        self.poll_interval = poll_interval
        self.stats = OpenWRTStats()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable] = []
        self._auth_token: Optional[str] = None
        self._available = False
        self._method: str = ""
        self._fetch_count = 0
        self._last_error: str = ""
        self._error_count = 0
        self._consecutive_failures = 0

    def on_update(self, callback: Callable):
        """Register callback for stats updates."""
        self._callbacks.append(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(self.stats.to_dict())
            except Exception as e:
                print(f"OpenWRT callback error: {e}")

    def _http_request(self, url: str, data: dict = None, method: str = "GET") -> Optional[dict]:
        """Make HTTP request to router."""
        try:
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'NetworkMonitor/1.0'
            }

            if data:
                data_bytes = json.dumps(data).encode('utf-8')
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
            else:
                req = urllib.request.Request(url, headers=headers, method=method)

            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            self._last_error = str(e)
            # Only log occasionally to avoid spam
            if not hasattr(self, '_error_count'):
                self._error_count = 0
            self._error_count += 1
            if self._error_count <= 3 or self._error_count % 10 == 0:
                print(f"OpenWRT HTTP error: {e}")
            return None

    def _luci_rpc_auth(self) -> Optional[str]:
        """Authenticate with LUCI RPC and get auth token."""
        url = f"http://{self.router_ip}/cgi-bin/luci/rpc/auth"
        data = {
            "id": 1,
            "method": "login",
            "params": [self.username, self.password]
        }
        result = self._http_request(url, data, "POST")
        if result and result.get("result"):
            return result["result"]
        return None

    def _luci_rpc_call(self, module: str, method: str, params: list = None) -> Optional[dict]:
        """Call LUCI RPC method."""
        if not self._auth_token:
            self._auth_token = self._luci_rpc_auth()
            if not self._auth_token:
                return None

        url = f"http://{self.router_ip}/cgi-bin/luci/rpc/{module}?auth={self._auth_token}"
        data = {
            "id": 1,
            "method": method,
            "params": params or []
        }
        return self._http_request(url, data, "POST")

    def _ubus_login(self) -> Optional[str]:
        """Authenticate with ubus and get session token."""
        url = f"http://{self.router_ip}/ubus"
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [
                "00000000000000000000000000000000",
                "session",
                "login",
                {
                    "username": self.username,
                    "password": self.password
                }
            ]
        }
        result = self._http_request(url, data, "POST")

        if result and "result" in result:
            res = result["result"]
            if isinstance(res, list) and len(res) > 1 and isinstance(res[1], dict):
                session = res[1].get("ubus_rpc_session")
                if session:
                    print(f"OpenWRT: ubus login successful")
                    return session

        print(f"OpenWRT: ubus login failed (response: {result})")
        return None

    def _ubus_call(self, path: str, method: str, params: dict = None) -> Optional[dict]:
        """Call ubus over HTTP."""
        # Ensure we have a session token
        if not self._auth_token:
            self._auth_token = self._ubus_login()
            if not self._auth_token:
                return None

        url = f"http://{self.router_ip}/ubus"
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [
                self._auth_token,
                path,
                method,
                params or {}
            ]
        }
        result = self._http_request(url, data, "POST")

        if not result:
            return None

        # Debug: print raw response on first few calls
        if not hasattr(self, '_debug_count'):
            self._debug_count = 0
        if self._debug_count < 3:
            print(f"OpenWRT: ubus {path}.{method} response: {result}")
            self._debug_count += 1

        if "result" in result:
            res = result["result"]
            # ubus returns [status_code, data] where status 0 = success
            if isinstance(res, list):
                # Check for access denied (status 6)
                if len(res) > 0 and res[0] == 6:
                    print(f"OpenWRT: Access denied for {path}.{method}, re-authenticating...")
                    self._auth_token = None
                    return None
                if len(res) > 1 and isinstance(res[1], dict):
                    return res[1]
                elif len(res) > 0 and res[0] == 0:
                    # Success but no data dict
                    return {}
            elif isinstance(res, dict):
                return res

        # Check for error (only log non-access-denied errors after debug period)
        if "error" in result:
            err = result['error']
            # Suppress repeated access denied messages
            if err.get('code') != -32002 or self._debug_count <= 3:
                print(f"OpenWRT: ubus error: {err}")

        return None

    def _detect_method(self) -> bool:
        """Detect which API method is available."""
        print(f"OpenWRT: Attempting to connect to {self.router_ip}...")

        # Clear old auth token to force fresh login (important after router reboot)
        self._auth_token = None

        # Try ubus first (requires uhttpd-mod-ubus on router)
        try:
            print(f"OpenWRT: Trying ubus API at http://{self.router_ip}/ubus ...")
            result = self._ubus_call("system", "info")
            # Result can be {} (empty dict) for success with no data, or dict with data
            if result is not None:
                self._method = "ubus"
                self._available = True
                print(f"OpenWRT: SUCCESS - Using ubus API at {self.router_ip}")
                if isinstance(result, dict) and result:
                    uptime = result.get('uptime', 0)
                    if uptime:
                        print(f"OpenWRT: Router uptime: {uptime // 3600}h {(uptime % 3600) // 60}m")
                    mem = result.get('memory', {})
                    if mem:
                        total_mb = mem.get('total', 0) // (1024*1024)
                        free_mb = mem.get('free', 0) // (1024*1024)
                        print(f"OpenWRT: Memory: {free_mb}MB free / {total_mb}MB total")
                return True
            else:
                print(f"OpenWRT: ubus call failed (auth issue or endpoint not available)")
        except Exception as e:
            print(f"OpenWRT: ubus failed: {e}")

        # Try LUCI RPC
        try:
            print(f"OpenWRT: Trying LUCI RPC API...")
            self._auth_token = self._luci_rpc_auth()
            if self._auth_token:
                self._method = "luci"
                self._available = True
                print(f"OpenWRT: SUCCESS - Using LUCI RPC at {self.router_ip}")
                return True
            else:
                print(f"OpenWRT: LUCI auth failed (no token)")
        except Exception as e:
            print(f"OpenWRT: LUCI RPC failed: {e}")

        print(f"OpenWRT: FAILED - No API available at {self.router_ip}")
        print(f"OpenWRT: Install 'uhttpd-mod-ubus' or 'luci-mod-rpc' on your router")
        return False

    def _fetch_ubus_stats(self) -> OpenWRTStats:
        """Fetch statistics using ubus."""
        stats = OpenWRTStats(timestamp=time.time(), router_online=True)
        interface_to_ssid = {}  # Map interface name to SSID

        # System info
        sys_info = self._ubus_call("system", "info")
        if sys_info and isinstance(sys_info, dict):
            stats.uptime = sys_info.get("uptime", 0)
            load = sys_info.get("load", [0, 0, 0])
            if isinstance(load, list) and len(load) >= 3:
                # Load is in 1/65536 units, convert to decimal
                stats.load_avg = tuple(x / 65536.0 for x in load[:3])
            mem = sys_info.get("memory", {})
            if isinstance(mem, dict):
                stats.memory_total = mem.get("total", 0)
                stats.memory_free = mem.get("free", 0)
                stats.memory_buffered = mem.get("buffered", 0)

        # Board info
        board = self._ubus_call("system", "board")
        if board and isinstance(board, dict):
            stats.hostname = board.get("hostname", "")
            stats.model = board.get("model", "")
            release = board.get("release", {})
            if isinstance(release, dict):
                stats.firmware = f"{release.get('distribution', '')} {release.get('version', '')}".strip()

        # Network interfaces
        net_status = self._ubus_call("network.interface", "dump")
        if net_status and isinstance(net_status, dict) and "interface" in net_status:
            for iface in net_status.get("interface", []):
                if not isinstance(iface, dict):
                    continue
                name = iface.get("interface", "")
                ipv4_addrs = iface.get("ipv4-address", [])
                stats.interfaces[name] = {
                    "up": iface.get("up", False),
                    "protocol": iface.get("proto", ""),
                    "device": iface.get("l3_device", ""),
                    "ipv4": [addr.get("address") for addr in ipv4_addrs if isinstance(addr, dict)]
                }

        # DHCP leases (connected clients)
        leases = self._ubus_call("dhcp", "ipv4leases")
        if self._fetch_count < 3:
            print(f"OpenWRT: dhcp.ipv4leases response: {leases}")
        if leases and isinstance(leases, dict) and "dhcp_leases" in leases:
            dhcp_leases = leases.get("dhcp_leases", {})
            if self._fetch_count < 3:
                print(f"OpenWRT: DHCP leases structure: {type(dhcp_leases)}, keys={dhcp_leases.keys() if isinstance(dhcp_leases, dict) else 'N/A'}")
            if isinstance(dhcp_leases, dict):
                for lease_name, lease_group in dhcp_leases.items():
                    if self._fetch_count < 3:
                        print(f"OpenWRT: DHCP lease group '{lease_name}': {lease_group}")
                    if isinstance(lease_group, list):
                        for lease in lease_group:
                            if isinstance(lease, dict):
                                client = OpenWRTClient(
                                    mac=lease.get("mac", ""),
                                    ip=lease.get("ipaddr", ""),
                                    hostname=lease.get("hostname", "")
                                )
                                if self._fetch_count < 3:
                                    print(f"OpenWRT: Added DHCP client: mac={client.mac}, ip={client.ip}, hostname={client.hostname}")
                                stats.clients.append(client)
        elif self._fetch_count < 3:
            print(f"OpenWRT: No DHCP leases found in response")

        # Wireless clients and networks
        wifi_status = self._ubus_call("network.wireless", "status")

        # Debug: log wireless status structure (without sensitive data)
        if self._fetch_count < 3 and wifi_status:
            radios = list(wifi_status.keys()) if isinstance(wifi_status, dict) else []
            print(f"OpenWRT: network.wireless.status has {len(radios)} radios: {radios}")

        if wifi_status and isinstance(wifi_status, dict):
            for radio, data in wifi_status.items():
                if not isinstance(data, dict):
                    continue

                # Get radio channel/frequency info
                radio_channel = data.get("channel", 0)
                radio_frequency = data.get("frequency", 0)

                # Debug: log interfaces
                if self._fetch_count < 3:
                    print(f"OpenWRT: Radio {radio} has {len(data.get('interfaces', []))} interfaces")

                for iface in data.get("interfaces", []):
                    if not isinstance(iface, dict):
                        continue

                    # Extract wireless network info (SSIDs)
                    config = iface.get("config", {})
                    ifname = iface.get("ifname", "")

                    # Debug: log interface details (without sensitive data)
                    if self._fetch_count < 3:
                        ssid_debug = config.get("ssid", "unknown") if isinstance(config, dict) else "unknown"
                        mode_debug = config.get("mode", "unknown") if isinstance(config, dict) else "unknown"
                        stations = iface.get("stations", [])
                        print(f"OpenWRT: Interface {ifname}: ssid={ssid_debug}, mode={mode_debug}, stations={len(stations)}")

                    if isinstance(config, dict):
                        ssid = config.get("ssid", "")
                        mode = config.get("mode", "ap")
                        if ssid:
                            # Map interface to SSID for client lookup
                            if ifname:
                                interface_to_ssid[ifname] = ssid

                            wifi_net = WirelessNetwork(
                                ssid=ssid,
                                ifname=ifname,
                                mode=mode,
                                channel=radio_channel,
                                frequency=radio_frequency
                            )

                            # For STA mode, get connection info
                            if mode in ("sta", "client"):
                                iwinfo = iface.get("iwinfo", {})
                                if isinstance(iwinfo, dict):
                                    wifi_net.signal = iwinfo.get("signal", 0)
                                    wifi_net.bssid = iwinfo.get("bssid", "")
                                    wifi_net.connected = iwinfo.get("bssid") is not None

                            stats.wireless_networks.append(wifi_net)

                    # Process associated clients (for AP mode)
                    # Try both 'assoclist' (older) and 'stations' (newer) fields
                    assoclist = iface.get("assoclist", {}) or {}
                    stations = iface.get("stations", []) or []

                    client_ssid = interface_to_ssid.get(ifname, "")

                    # Process assoclist format (dict of mac -> data)
                    if isinstance(assoclist, dict):
                        for mac, client_data in assoclist.items():
                            if not isinstance(client_data, dict):
                                continue
                            existing = next((c for c in stats.clients if c.mac.lower() == mac.lower()), None)
                            if existing:
                                existing.signal_strength = client_data.get("signal", 0)
                                existing.interface = ifname or radio
                                existing.ssid = client_ssid
                            else:
                                stats.clients.append(OpenWRTClient(
                                    mac=mac,
                                    signal_strength=client_data.get("signal", 0),
                                    interface=ifname or radio,
                                    ssid=client_ssid
                                ))
                            stats.wireless_clients += 1

                    # Process stations format (list)
                    if isinstance(stations, list):
                        for station in stations:
                            if not isinstance(station, dict):
                                continue
                            mac = station.get("mac", "")
                            if not mac:
                                continue
                            existing = next((c for c in stats.clients if c.mac.lower() == mac.lower()), None)
                            if existing:
                                existing.signal_strength = station.get("signal", 0)
                                existing.interface = ifname or radio
                                existing.ssid = client_ssid
                            else:
                                stats.clients.append(OpenWRTClient(
                                    mac=mac,
                                    signal_strength=station.get("signal", 0),
                                    interface=ifname or radio,
                                    ssid=client_ssid
                                ))
                            stats.wireless_clients += 1

        # Try to get clients from hostapd for each AP interface
        for wifi_net in stats.wireless_networks:
            if wifi_net.mode in ('ap', 'master') and wifi_net.ifname:
                hostapd_clients = self._ubus_call(f"hostapd.{wifi_net.ifname}", "get_clients")
                if self._fetch_count < 3:
                    print(f"OpenWRT: hostapd.{wifi_net.ifname} response: {hostapd_clients}")
                if hostapd_clients and isinstance(hostapd_clients, dict):
                    clients_dict = hostapd_clients.get("clients", {})
                    if isinstance(clients_dict, dict):
                        if self._fetch_count < 3:
                            print(f"OpenWRT: hostapd.{wifi_net.ifname} has {len(clients_dict)} clients for SSID '{wifi_net.ssid}'")
                        for mac, client_data in clients_dict.items():
                            if not isinstance(client_data, dict):
                                continue
                            if self._fetch_count < 3:
                                print(f"OpenWRT: hostapd client MAC={mac}, data={client_data}")
                            existing = next((c for c in stats.clients if c.mac.lower() == mac.lower()), None)
                            if existing:
                                existing.signal_strength = client_data.get("signal", 0)
                                existing.interface = wifi_net.ifname
                                existing.ssid = wifi_net.ssid
                                if self._fetch_count < 3:
                                    print(f"OpenWRT: Updated existing client {mac} with ssid={wifi_net.ssid}")
                            else:
                                stats.clients.append(OpenWRTClient(
                                    mac=mac,
                                    signal_strength=client_data.get("signal", 0),
                                    interface=wifi_net.ifname,
                                    ssid=wifi_net.ssid
                                ))
                                if self._fetch_count < 3:
                                    print(f"OpenWRT: Added new hostapd client {mac} with ssid={wifi_net.ssid}")
                            stats.wireless_clients += 1

        stats.connected_clients = len(stats.clients)

        # Debug: log final client list
        if self._fetch_count < 5:
            print(f"OpenWRT: Final client list ({len(stats.clients)} clients):")
            for c in stats.clients:
                print(f"  - MAC={c.mac}, IP={c.ip}, hostname={c.hostname}, ssid={c.ssid}, signal={c.signal_strength}, is_wireless={c.signal_strength != 0}")

        return stats

    def _fetch_luci_stats(self) -> OpenWRTStats:
        """Fetch statistics using LUCI RPC."""
        stats = OpenWRTStats(timestamp=time.time())

        # System info via sys module
        result = self._luci_rpc_call("sys", "sysinfo")
        if result and result.get("result"):
            info = result["result"]
            stats.uptime = info.get("uptime", 0)
            stats.load_avg = tuple(info.get("load", [0, 0, 0]))
            stats.memory_total = info.get("memory", {}).get("total", 0)
            stats.memory_free = info.get("memory", {}).get("free", 0)

        # Network info
        result = self._luci_rpc_call("uci", "get_all", ["network"])
        if result and result.get("result"):
            for name, config in result["result"].items():
                if config.get(".type") == "interface":
                    stats.interfaces[name] = {
                        "proto": config.get("proto", ""),
                        "device": config.get("device", "")
                    }

        return stats

    def fetch_stats(self) -> Optional[OpenWRTStats]:
        """Fetch all statistics from router."""
        if not self._available:
            if not self._detect_method():
                # Router offline - create empty stats with offline status
                self.stats = OpenWRTStats(
                    timestamp=time.time(),
                    router_online=False,
                    last_error=self._last_error
                )
                self._consecutive_failures += 1
                self._notify_callbacks()
                return self.stats

        try:
            if self._method == "ubus":
                self.stats = self._fetch_ubus_stats()
            elif self._method == "luci":
                self.stats = self._fetch_luci_stats()

            # Check if we actually got data (router might be partially responsive)
            if self.stats.uptime > 0:
                self.stats.router_online = True
                self._consecutive_failures = 0
                self._error_count = 0
            else:
                self.stats.router_online = False
                self._consecutive_failures += 1
                # After 3 consecutive failures, force re-authentication
                if self._consecutive_failures >= 3:
                    print(f"OpenWRT: {self._consecutive_failures} consecutive failures, will re-authenticate")
                    self._available = False
                    self._auth_token = None

            # Log successful fetch (first time and every 30 fetches ~5 min)
            self._fetch_count += 1
            if self._fetch_count == 1 or self._fetch_count % 30 == 0:
                print(f"OpenWRT: Fetched stats - {self.stats.connected_clients} clients, "
                      f"uptime: {self.stats.uptime // 3600}h, "
                      f"mem: {self.stats.memory_free // (1024*1024)}MB free")

            self._notify_callbacks()
            return self.stats
        except Exception as e:
            print(f"OpenWRT fetch error: {e}")
            self._available = False
            self._consecutive_failures += 1

            # Return offline status
            self.stats = OpenWRTStats(
                timestamp=time.time(),
                router_online=False,
                last_error=str(e)
            )
            self._notify_callbacks()
            return self.stats

    def _poll_loop(self):
        """Background polling loop."""
        while self._running:
            try:
                self.fetch_stats()
            except Exception as e:
                print(f"OpenWRT poll error: {e}")
            time.sleep(self.poll_interval)

    def start(self):
        """Start background polling."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print(f"OpenWRT integration started (router: {self.router_ip}, interval: {self.poll_interval}s)")

    def stop(self):
        """Stop background polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("OpenWRT integration stopped")

    def get_stats(self) -> dict:
        """Get current stats."""
        return self.stats.to_dict()

    def is_available(self) -> bool:
        """Check if OpenWRT integration is available."""
        return self._available
