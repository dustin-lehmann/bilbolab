"""
Network Scanner Module
Discovers devices on the local network using ARP scanning and hostname resolution.
"""

import subprocess
import socket
import threading
import time
import re
import platform
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime


@dataclass
class NetworkDevice:
    ip: str
    mac: str = ""
    hostname: str = ""
    vendor: str = ""
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            'ip': self.ip,
            'mac': self.mac,
            'hostname': self.hostname or self.ip,
            'vendor': self.vendor,
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'online_duration': time.time() - self.first_seen
        }


class NetworkScanner:
    """Scans the local network for connected devices."""

    def __init__(self, interface: str = None, scan_interval: float = 10.0):
        self.interface = interface
        self.scan_interval = scan_interval
        self.devices: dict[str, NetworkDevice] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []
        self._local_ip = self._get_local_ip()
        self._network_prefix = self._get_network_prefix()

    def _get_local_ip(self) -> str:
        """Get the local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _get_network_prefix(self) -> str:
        """Get the network prefix (e.g., 192.168.1)."""
        parts = self._local_ip.split('.')
        if len(parts) == 4:
            return '.'.join(parts[:3])
        return "192.168.1"

    def on_update(self, callback: Callable):
        """Register a callback for device updates."""
        self._callbacks.append(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks."""
        devices = self.get_devices()
        for callback in self._callbacks:
            try:
                callback(devices)
            except Exception as e:
                print(f"Callback error: {e}")

    def _is_valid_device_ip(self, ip: str) -> bool:
        """Check if IP is a valid device address (not multicast, broadcast, etc.)."""
        try:
            parts = [int(p) for p in ip.split('.')]
            if len(parts) != 4:
                return False

            first_octet = parts[0]

            # Filter out multicast addresses (224.0.0.0 - 239.255.255.255)
            if 224 <= first_octet <= 239:
                return False

            # Filter out broadcast address
            if parts == [255, 255, 255, 255]:
                return False

            # Filter out link-local (169.254.x.x) - usually means DHCP failure
            if first_octet == 169 and parts[1] == 254:
                return False

            # Filter out loopback (127.x.x.x)
            if first_octet == 127:
                return False

            # Filter out 0.0.0.0
            if parts == [0, 0, 0, 0]:
                return False

            return True
        except (ValueError, IndexError):
            return False

    def _resolve_hostname(self, ip: str) -> str:
        """Resolve IP to hostname."""
        try:
            hostname = socket.gethostbyaddr(ip)[0]
            return hostname
        except (socket.herror, socket.gaierror):
            return ""

    def _scan_arp_macos(self) -> list[tuple[str, str]]:
        """Scan using arp on macOS."""
        results = []
        try:
            # Use arp -a to get ARP table
            output = subprocess.check_output(['arp', '-a'], text=True, timeout=10)
            # Pattern: hostname (ip) at mac on interface
            pattern = r'\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)'
            for match in re.finditer(pattern, output):
                ip, mac = match.groups()
                if mac != '(incomplete)' and mac != 'ff:ff:ff:ff:ff:ff':
                    results.append((ip, mac))
        except Exception as e:
            print(f"ARP scan error: {e}")
        return results

    def _scan_arp_linux(self) -> list[tuple[str, str]]:
        """Scan using arp-scan on Linux (preferred) or arp fallback."""
        results = []

        # Try arp-scan first (more reliable, requires root)
        try:
            cmd = ['arp-scan', '--localnet', '-q']
            if self.interface:
                cmd.extend(['-I', self.interface])
            output = subprocess.check_output(cmd, text=True, timeout=30, stderr=subprocess.DEVNULL)
            for line in output.strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 2:
                    ip, mac = parts[0], parts[1]
                    if re.match(r'\d+\.\d+\.\d+\.\d+', ip):
                        results.append((ip, mac))
            if results:
                return results
        except Exception:
            pass

        # Fallback to reading /proc/net/arp
        try:
            with open('/proc/net/arp', 'r') as f:
                for line in f.readlines()[1:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 4:
                        ip, mac = parts[0], parts[3]
                        if mac != '00:00:00:00:00:00':
                            results.append((ip, mac))
        except Exception:
            pass

        # Also try ping sweep to populate ARP table
        self._ping_sweep()

        return results

    def _ping_sweep(self):
        """Ping sweep to populate ARP table."""
        def ping_host(ip):
            try:
                subprocess.run(
                    ['ping', '-c', '1', '-W', '1', ip],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2
                )
            except Exception:
                pass

        threads = []
        for i in range(1, 255):
            ip = f"{self._network_prefix}.{i}"
            t = threading.Thread(target=ping_host, args=(ip,), daemon=True)
            threads.append(t)
            t.start()

        # Wait for all pings (with timeout)
        for t in threads:
            t.join(timeout=0.1)

    def scan(self) -> dict[str, NetworkDevice]:
        """Perform a network scan."""
        system = platform.system()

        if system == 'Darwin':
            # On macOS, do a ping sweep first to populate ARP cache
            self._ping_sweep()
            time.sleep(0.5)
            results = self._scan_arp_macos()
        elif system == 'Linux':
            results = self._scan_arp_linux()
        else:
            results = []

        current_time = time.time()
        seen_ips = set()

        with self._lock:
            for ip, mac in results:
                # Skip invalid addresses (multicast, broadcast, etc.)
                if not self._is_valid_device_ip(ip):
                    continue

                seen_ips.add(ip)
                if ip in self.devices:
                    self.devices[ip].last_seen = current_time
                    self.devices[ip].mac = mac
                    # Retry hostname resolution if not yet resolved
                    if not self.devices[ip].hostname or self.devices[ip].hostname == ip:
                        hostname = self._resolve_hostname(ip)
                        if hostname:
                            self.devices[ip].hostname = hostname
                else:
                    hostname = self._resolve_hostname(ip)
                    self.devices[ip] = NetworkDevice(
                        ip=ip,
                        mac=mac,
                        hostname=hostname,
                        first_seen=current_time,
                        last_seen=current_time
                    )

            # Remove stale devices (not seen for more than 5 minutes)
            # and any invalid addresses (multicast, broadcast, etc.)
            stale_threshold = current_time - 300
            ips_to_remove = [ip for ip, dev in self.devices.items()
                             if dev.last_seen < stale_threshold or not self._is_valid_device_ip(ip)]
            for ip in ips_to_remove:
                del self.devices[ip]

        self._notify_callbacks()
        return self.devices.copy()

    def get_devices(self) -> list[dict]:
        """Get list of discovered devices."""
        with self._lock:
            return [dev.to_dict() for dev in self.devices.values()]

    def _scan_loop(self):
        """Background scanning loop."""
        while self._running:
            try:
                self.scan()
            except Exception as e:
                print(f"Scan error: {e}")
            time.sleep(self.scan_interval)

    def start(self):
        """Start background scanning."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()
        print(f"Network scanner started (interval: {self.scan_interval}s)")

    def stop(self):
        """Stop background scanning."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("Network scanner stopped")
