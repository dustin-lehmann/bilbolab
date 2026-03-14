"""
Internet Connectivity Checker
Monitors internet connection status with multiple fallback checks.
"""

import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional, Callable


@dataclass
class InternetStatus:
    connected: bool = False
    latency_ms: float = 0.0
    method: str = ""  # Which check method succeeded
    last_check: float = 0.0
    consecutive_failures: int = 0
    dns_working: bool = False
    gateway_reachable: bool = False

    def to_dict(self) -> dict:
        return {
            'connected': self.connected,
            'latency_ms': round(self.latency_ms, 2),
            'method': self.method,
            'last_check': self.last_check,
            'dns_working': self.dns_working,
            'gateway_reachable': self.gateway_reachable
        }


class InternetChecker:
    """Monitors internet connectivity using multiple methods."""

    # Reliable endpoints for connectivity checks
    CHECK_HOSTS = [
        ("8.8.8.8", 53),        # Google DNS
        ("1.1.1.1", 53),        # Cloudflare DNS
        ("208.67.222.222", 53), # OpenDNS
    ]

    CHECK_URLS = [
        "http://www.google.com/generate_204",
        "http://connectivitycheck.gstatic.com/generate_204",
        "http://www.apple.com/library/test/success.html",
    ]

    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self.status = InternetStatus()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable] = []
        self._gateway_ip: Optional[str] = None

    def on_update(self, callback: Callable):
        """Register callback for status updates."""
        self._callbacks.append(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(self.status.to_dict())
            except Exception as e:
                print(f"Internet checker callback error: {e}")

    def _get_default_gateway(self) -> Optional[str]:
        """Get the default gateway IP."""
        try:
            import platform
            if platform.system() == 'Darwin':
                output = subprocess.check_output(
                    ['route', '-n', 'get', 'default'],
                    text=True, timeout=5
                )
                for line in output.split('\n'):
                    if 'gateway:' in line:
                        return line.split(':')[1].strip()
            else:  # Linux
                output = subprocess.check_output(
                    ['ip', 'route', 'show', 'default'],
                    text=True, timeout=5
                )
                parts = output.split()
                if 'via' in parts:
                    return parts[parts.index('via') + 1]
        except Exception:
            pass
        return None

    def _check_socket(self, host: str, port: int, timeout: float = 3.0) -> tuple[bool, float]:
        """Check connectivity via socket connection."""
        try:
            start = time.time()
            socket.setdefaulttimeout(timeout)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            s.close()
            latency = (time.time() - start) * 1000
            return True, latency
        except Exception:
            return False, 0.0

    def _check_dns(self) -> bool:
        """Check if DNS resolution works."""
        try:
            socket.gethostbyname("www.google.com")
            return True
        except Exception:
            return False

    def _check_http(self, url: str, timeout: float = 5.0) -> tuple[bool, float]:
        """Check connectivity via HTTP request."""
        try:
            start = time.time()
            req = urllib.request.Request(url, headers={'User-Agent': 'NetworkMonitor/1.0'})
            urllib.request.urlopen(req, timeout=timeout)
            latency = (time.time() - start) * 1000
            return True, latency
        except Exception:
            return False, 0.0

    def _check_gateway(self) -> bool:
        """Check if default gateway is reachable."""
        if not self._gateway_ip:
            self._gateway_ip = self._get_default_gateway()

        if self._gateway_ip:
            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', self._gateway_ip],
                    capture_output=True,
                    timeout=3
                )
                return result.returncode == 0
            except Exception:
                pass
        return False

    def check(self) -> InternetStatus:
        """Perform internet connectivity check."""
        self.status.last_check = time.time()
        self.status.dns_working = self._check_dns()
        self.status.gateway_reachable = self._check_gateway()

        # Try socket connections first (fastest)
        for host, port in self.CHECK_HOSTS:
            success, latency = self._check_socket(host, port)
            if success:
                self.status.connected = True
                self.status.latency_ms = latency
                self.status.method = f"socket:{host}:{port}"
                self.status.consecutive_failures = 0
                self._notify_callbacks()
                return self.status

        # Try HTTP checks as fallback
        for url in self.CHECK_URLS:
            success, latency = self._check_http(url)
            if success:
                self.status.connected = True
                self.status.latency_ms = latency
                self.status.method = f"http:{url}"
                self.status.consecutive_failures = 0
                self._notify_callbacks()
                return self.status

        # All checks failed
        self.status.connected = False
        self.status.latency_ms = 0.0
        self.status.method = "none"
        self.status.consecutive_failures += 1
        self._notify_callbacks()
        return self.status

    def _check_loop(self):
        """Background checking loop."""
        while self._running:
            try:
                self.check()
            except Exception as e:
                print(f"Internet check error: {e}")
            time.sleep(self.check_interval)

    def start(self):
        """Start background checking."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
        print(f"Internet checker started (interval: {self.check_interval}s)")

    def stop(self):
        """Stop background checking."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("Internet checker stopped")

    def get_status(self) -> dict:
        """Get current status."""
        return self.status.to_dict()
