"""
Ping Monitor Module
Monitors specific hosts via ICMP ping and tracks their status.
"""

import subprocess
import threading
import time
import platform
from dataclasses import dataclass, field
from typing import Optional, Callable
from enum import Enum


class HostStatus(Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    REMOVED = "removed"


@dataclass
class MonitoredHost:
    hostname: str
    ip: str = ""
    username: str = ""  # SSH username for this host
    description: str = ""  # Display name (e.g., "ROBOT", "OPTITRACK SERVER")
    status: HostStatus = HostStatus.UNKNOWN
    latency_ms: float = 0.0
    last_seen: float = 0.0
    consecutive_failures: int = 0
    total_pings: int = 0
    successful_pings: int = 0
    latency_history: list[float] = field(default_factory=list)
    max_history: int = 60  # Keep last 60 measurements (2 min at 2s interval)

    @property
    def uptime_percent(self) -> float:
        if self.total_pings == 0:
            return 0.0
        return (self.successful_pings / self.total_pings) * 100

    @property
    def avg_latency(self) -> float:
        if not self.latency_history:
            return 0.0
        return sum(self.latency_history) / len(self.latency_history)

    @property
    def max_latency(self) -> float:
        if not self.latency_history:
            return 0.0
        return max(self.latency_history)

    @property
    def min_latency(self) -> float:
        if not self.latency_history:
            return 0.0
        return min(self.latency_history)

    def to_dict(self) -> dict:
        return {
            'hostname': self.hostname,
            'ip': self.ip,
            'username': self.username,
            'description': self.description,
            'status': self.status.value,
            'latency_ms': round(self.latency_ms, 2),
            'avg_latency': round(self.avg_latency, 2),
            'min_latency': round(self.min_latency, 2),
            'max_latency': round(self.max_latency, 2),
            'last_seen': self.last_seen,
            'consecutive_failures': self.consecutive_failures,
            'uptime_percent': round(self.uptime_percent, 1),
            'total_pings': self.total_pings,
            'successful_pings': self.successful_pings,
            'latency_history': self.latency_history[-60:]  # Send last 60 for uptime calculation
        }


class PingMonitor:
    """Monitors specific hosts via ping."""

    def __init__(self, ping_interval: float = 2.0, failure_threshold: int = 5, auto_remove: bool = False):
        self.ping_interval = ping_interval
        self.failure_threshold = failure_threshold
        self.auto_remove = auto_remove  # If False, hosts are never auto-removed
        self.hosts: dict[str, MonitoredHost] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []
        self._removal_callbacks: list[Callable] = []
        self._is_macos = platform.system() == 'Darwin'

    def on_update(self, callback: Callable):
        """Register callback for status updates."""
        self._callbacks.append(callback)

    def on_removal(self, callback: Callable):
        """Register callback for host removal."""
        self._removal_callbacks.append(callback)

    def _notify_callbacks(self, host: MonitoredHost):
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(host.to_dict())
            except Exception as e:
                print(f"Callback error: {e}")

    def _notify_removal(self, host: MonitoredHost):
        """Notify removal callbacks."""
        for callback in self._removal_callbacks:
            try:
                callback(host.to_dict())
            except Exception as e:
                print(f"Removal callback error: {e}")

    def add_host(self, hostname: str, ip: str = "", username: str = "", description: str = ""):
        """Add a host to monitor."""
        with self._lock:
            if hostname not in self.hosts:
                self.hosts[hostname] = MonitoredHost(hostname=hostname, ip=ip, username=username, description=description)
                print(f"Added host to monitor: {hostname}")

    def remove_host(self, hostname: str):
        """Remove a host from monitoring."""
        with self._lock:
            if hostname in self.hosts:
                del self.hosts[hostname]
                print(f"Removed host from monitor: {hostname}")

    def update_host_username(self, hostname: str, username: str):
        """Update the SSH username for a host."""
        with self._lock:
            if hostname in self.hosts:
                self.hosts[hostname].username = username
                print(f"Updated username for {hostname}: {username}")

    def update_host_description(self, hostname: str, description: str):
        """Update the description for a host."""
        with self._lock:
            if hostname in self.hosts:
                self.hosts[hostname].description = description
                print(f"Updated description for {hostname}: {description}")

    def get_hosts(self) -> list[dict]:
        """Get all monitored hosts."""
        with self._lock:
            return [h.to_dict() for h in self.hosts.values()
                    if h.status != HostStatus.REMOVED]

    def _ping_host(self, host: MonitoredHost) -> tuple[bool, float, str]:
        """Ping a single host and return (success, latency_ms, resolved_ip)."""
        target = host.ip if host.ip else host.hostname
        resolved_ip = host.ip

        # Try to resolve hostname to IP if not already set
        if not resolved_ip and host.hostname:
            try:
                import socket
                resolved_ip = socket.gethostbyname(host.hostname)
            except Exception:
                pass

        try:
            if self._is_macos:
                # macOS ping syntax
                cmd = ['ping', '-c', '1', '-W', '1000', target]
            else:
                # Linux ping syntax
                cmd = ['ping', '-c', '1', '-W', '1', target]

            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3
            )
            elapsed = (time.time() - start_time) * 1000

            if result.returncode == 0:
                # Try to parse actual latency from output
                import re
                # macOS: round-trip min/avg/max/stddev = 0.123/0.456/0.789/0.012 ms
                # Linux: rtt min/avg/max/mdev = 0.123/0.456/0.789/0.012 ms
                match = re.search(r'(\d+\.?\d*)/(\d+\.?\d*)/(\d+\.?\d*)', result.stdout)
                if match:
                    latency = float(match.group(1))  # min latency
                else:
                    latency = elapsed
                return True, latency, resolved_ip
            return False, 0.0, resolved_ip

        except subprocess.TimeoutExpired:
            return False, 0.0, resolved_ip
        except Exception as e:
            print(f"Ping error for {target}: {e}")
            return False, 0.0, resolved_ip

    def _ping_all(self):
        """Ping all monitored hosts."""
        hosts_to_remove = []

        with self._lock:
            hosts_copy = list(self.hosts.values())

        for host in hosts_copy:
            success, latency, resolved_ip = self._ping_host(host)

            with self._lock:
                previous_status = host.status

                # Update resolved IP if we got one and host didn't have one
                if resolved_ip and not host.ip:
                    host.ip = resolved_ip

                if success:
                    # Reset statistics on first connect (transition to online)
                    if previous_status in (HostStatus.OFFLINE, HostStatus.UNKNOWN):
                        host.total_pings = 0
                        host.successful_pings = 0
                        host.latency_history = []

                    host.total_pings += 1
                    host.status = HostStatus.ONLINE
                    host.latency_ms = latency
                    host.last_seen = time.time()
                    host.consecutive_failures = 0
                    host.successful_pings += 1
                    host.latency_history.append(latency)

                    # Trim history
                    if len(host.latency_history) > host.max_history:
                        host.latency_history = host.latency_history[-host.max_history:]
                else:
                    host.consecutive_failures += 1
                    host.latency_ms = 0.0

                    # Only mark offline after 3 consecutive failures
                    if host.consecutive_failures >= 3:
                        host.status = HostStatus.OFFLINE

                    # Only auto-remove if enabled
                    if self.auto_remove and host.consecutive_failures >= self.failure_threshold:
                        hosts_to_remove.append(host)
                        host.status = HostStatus.REMOVED

                self._notify_callbacks(host)

        # Notify and remove hosts that exceeded failure threshold (only if auto_remove is enabled)
        if self.auto_remove:
            for host in hosts_to_remove:
                self._notify_removal(host)
                with self._lock:
                    if host.hostname in self.hosts:
                        del self.hosts[host.hostname]

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                self._ping_all()
            except Exception as e:
                print(f"Monitor error: {e}")
            time.sleep(self.ping_interval)

    def start(self):
        """Start monitoring."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"Ping monitor started (interval: {self.ping_interval}s)")

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("Ping monitor stopped")
