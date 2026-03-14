"""
System Metrics Collector
Gathers CPU, memory, network, and disk metrics for the monitoring host.
"""

import os
import threading
import time
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class NetworkInterface:
    name: str
    ip: str = ""
    mac: str = ""
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    rx_errors: int = 0
    tx_errors: int = 0

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'ip': self.ip,
            'mac': self.mac,
            'rx_bytes': self.rx_bytes,
            'tx_bytes': self.tx_bytes,
            'rx_packets': self.rx_packets,
            'tx_packets': self.tx_packets,
            'rx_errors': self.rx_errors,
            'tx_errors': self.tx_errors,
            'rx_mbps': 0.0,  # Calculated externally
            'tx_mbps': 0.0
        }


@dataclass
class SystemMetrics:
    hostname: str = ""
    platform: str = ""
    cpu_percent: float = 0.0
    cpu_count: int = 0
    memory_total: int = 0
    memory_used: int = 0
    memory_percent: float = 0.0
    disk_total: int = 0
    disk_used: int = 0
    disk_percent: float = 0.0
    uptime_seconds: float = 0.0
    load_avg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    interfaces: list[NetworkInterface] = field(default_factory=list)
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            'hostname': self.hostname,
            'platform': self.platform,
            'cpu_percent': round(self.cpu_percent, 1),
            'cpu_count': self.cpu_count,
            'memory_total_gb': round(self.memory_total / (1024**3), 2),
            'memory_used_gb': round(self.memory_used / (1024**3), 2),
            'memory_percent': round(self.memory_percent, 1),
            'disk_total_gb': round(self.disk_total / (1024**3), 2),
            'disk_used_gb': round(self.disk_used / (1024**3), 2),
            'disk_percent': round(self.disk_percent, 1),
            'uptime_hours': round(self.uptime_seconds / 3600, 2),
            'load_avg': [round(x, 2) for x in self.load_avg],
            'interfaces': [iface.to_dict() for iface in self.interfaces],
            'timestamp': self.timestamp
        }


class SystemMetricsCollector:
    """Collects system performance metrics."""

    def __init__(self, collect_interval: float = 2.0):
        self.collect_interval = collect_interval
        self.metrics = SystemMetrics()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable] = []
        self._prev_net_stats: dict[str, tuple[int, int]] = {}
        self._prev_net_time: float = 0
        self._is_macos = platform.system() == 'Darwin'

        # Initialize static info
        self.metrics.hostname = platform.node()
        self.metrics.platform = f"{platform.system()} {platform.release()}"
        self.metrics.cpu_count = os.cpu_count() or 1

    def on_update(self, callback: Callable):
        """Register callback for metrics updates."""
        self._callbacks.append(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                callback(self.metrics.to_dict())
            except Exception as e:
                print(f"Metrics callback error: {e}")

    def _get_cpu_percent_macos(self) -> float:
        """Get CPU usage on macOS."""
        try:
            output = subprocess.check_output(
                ['top', '-l', '1', '-n', '0', '-stats', 'cpu'],
                text=True, timeout=5
            )
            for line in output.split('\n'):
                if 'CPU usage' in line:
                    # Parse: CPU usage: 5.0% user, 10.0% sys, 85.0% idle
                    parts = line.split(':')[1]
                    idle = float(parts.split(',')[2].split('%')[0].strip())
                    return 100.0 - idle
        except Exception:
            pass
        return 0.0

    def _get_cpu_percent_linux(self) -> float:
        """Get CPU usage on Linux."""
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
                parts = line.split()[1:]
                total = sum(int(x) for x in parts)
                idle = int(parts[3])
                # This is cumulative, so we'd need to track deltas
                # For simplicity, use top or /proc/loadavg
                pass
        except Exception:
            pass

        # Fallback to load average
        try:
            load = os.getloadavg()
            cpu_count = os.cpu_count() or 1
            return min(100.0, (load[0] / cpu_count) * 100)
        except Exception:
            return 0.0

    def _get_memory_info_macos(self) -> tuple[int, int]:
        """Get memory info on macOS using memory_pressure or vm_stat."""
        try:
            # Try using memory_pressure for more accurate info
            try:
                output = subprocess.check_output(['memory_pressure'], text=True, timeout=5)
                # Parse: "System-wide memory free percentage: 75%"
                for line in output.split('\n'):
                    if 'free percentage' in line.lower():
                        free_pct = int(line.split(':')[1].strip().rstrip('%'))
                        total = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True).strip())
                        used = int(total * (100 - free_pct) / 100)
                        return total, used
            except Exception:
                pass

            # Fallback to vm_stat
            output = subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True)
            total = int(output.strip())

            vm_output = subprocess.check_output(['vm_stat'], text=True)

            # Parse page size from first line
            page_size = 4096  # Default
            lines = vm_output.split('\n')
            if lines and 'page size of' in lines[0]:
                import re
                match = re.search(r'page size of (\d+) bytes', lines[0])
                if match:
                    page_size = int(match.group(1))

            # Parse memory stats
            stats = {}
            for line in lines[1:]:
                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip().lower()
                    val = val.strip().rstrip('.')
                    try:
                        stats[key] = int(val) * page_size
                    except ValueError:
                        pass

            # Calculate used memory (app memory = active + wired + compressed)
            wired = stats.get('pages wired down', 0)
            active = stats.get('pages active', 0)
            compressed = stats.get('pages occupied by compressor', 0)
            # Also include some cached that's actually in use
            speculative = stats.get('pages speculative', 0)

            # More accurate: used = total - (free + inactive + speculative + purgeable)
            free = stats.get('pages free', 0)
            inactive = stats.get('pages inactive', 0)
            purgeable = stats.get('pages purgeable', 0)

            # Available memory (what macOS shows as "available")
            available = free + inactive + purgeable + speculative
            used = total - available

            return total, max(0, used)
        except Exception as e:
            print(f"Memory info error: {e}")
            return 0, 0

    def _get_memory_info_linux(self) -> tuple[int, int]:
        """Get memory info on Linux."""
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    key = parts[0].rstrip(':')
                    value = int(parts[1]) * 1024  # Convert from KB
                    meminfo[key] = value

                total = meminfo.get('MemTotal', 0)
                free = meminfo.get('MemFree', 0)
                buffers = meminfo.get('Buffers', 0)
                cached = meminfo.get('Cached', 0)
                used = total - free - buffers - cached
                return total, used
        except Exception:
            return 0, 0

    def _get_disk_info(self) -> tuple[int, int]:
        """Get disk usage for root filesystem."""
        try:
            # On macOS, use f_bavail (available to non-root) for more accurate free space
            stat = os.statvfs('/')
            total = stat.f_blocks * stat.f_frsize
            # Use f_bavail instead of f_bfree for user-available space
            available = stat.f_bavail * stat.f_frsize
            used = total - available

            # On macOS with APFS, the reported values can be confusing due to snapshots
            # Use df command as fallback for more accurate reporting
            if self._is_macos:
                try:
                    output = subprocess.check_output(['df', '-k', '/'], text=True, timeout=5)
                    lines = output.strip().split('\n')
                    if len(lines) >= 2:
                        parts = lines[1].split()
                        if len(parts) >= 4:
                            # df -k reports in 1K blocks
                            total = int(parts[1]) * 1024
                            used = int(parts[2]) * 1024
                            return total, used
                except Exception:
                    pass

            return total, used
        except Exception as e:
            print(f"Disk info error: {e}")
            return 0, 0

    def _get_uptime(self) -> float:
        """Get system uptime in seconds."""
        try:
            if self._is_macos:
                output = subprocess.check_output(['sysctl', '-n', 'kern.boottime'], text=True)
                # Format: { sec = 1234567890, usec = 123456 } ...
                import re
                match = re.search(r'sec = (\d+)', output)
                if match:
                    boot_time = int(match.group(1))
                    return time.time() - boot_time
            else:
                with open('/proc/uptime', 'r') as f:
                    return float(f.readline().split()[0])
        except Exception:
            pass
        return 0.0

    def _get_network_interfaces(self) -> list[NetworkInterface]:
        """Get network interface statistics."""
        interfaces = []
        current_time = time.time()
        time_delta = current_time - self._prev_net_time if self._prev_net_time else 1.0

        def safe_int(val: str) -> int:
            """Safely convert to int, returning 0 for invalid values."""
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0

        try:
            if self._is_macos:
                # Use netstat on macOS
                output = subprocess.check_output(['netstat', '-ibn'], text=True, timeout=5)
                for line in output.split('\n')[1:]:
                    parts = line.split()
                    if len(parts) >= 10 and parts[2] != 'Link':
                        name = parts[0]
                        if name.startswith('en') or name.startswith('eth') or name.startswith('lo'):
                            # macOS netstat -ibn format varies, try to find the right columns
                            # Name Mtu Network Address Ipkts Ierrs Ibytes Opkts Oerrs Obytes
                            iface = NetworkInterface(
                                name=name,
                                mac=parts[3] if len(parts) > 3 and ':' in parts[3] else "",
                                rx_packets=safe_int(parts[4]) if len(parts) > 4 else 0,
                                rx_errors=safe_int(parts[5]) if len(parts) > 5 else 0,
                                rx_bytes=safe_int(parts[6]) if len(parts) > 6 else 0,
                                tx_packets=safe_int(parts[7]) if len(parts) > 7 else 0,
                                tx_errors=safe_int(parts[8]) if len(parts) > 8 else 0,
                                tx_bytes=safe_int(parts[9]) if len(parts) > 9 else 0
                            )
                            # Only add if we have valid byte counts
                            if iface.rx_bytes > 0 or iface.tx_bytes > 0:
                                interfaces.append(iface)
            else:
                # Read from /proc on Linux
                with open('/proc/net/dev', 'r') as f:
                    for line in f.readlines()[2:]:  # Skip headers
                        parts = line.split()
                        name = parts[0].rstrip(':')
                        if name.startswith('en') or name.startswith('eth') or name.startswith('wl'):
                            iface = NetworkInterface(
                                name=name,
                                rx_bytes=safe_int(parts[1]),
                                rx_packets=safe_int(parts[2]),
                                rx_errors=safe_int(parts[3]),
                                tx_bytes=safe_int(parts[9]),
                                tx_packets=safe_int(parts[10]),
                                tx_errors=safe_int(parts[11])
                            )
                            interfaces.append(iface)

            # Calculate throughput rates
            for iface in interfaces:
                key = iface.name
                if key in self._prev_net_stats:
                    prev_rx, prev_tx = self._prev_net_stats[key]
                    rx_rate = (iface.rx_bytes - prev_rx) / time_delta
                    tx_rate = (iface.tx_bytes - prev_tx) / time_delta
                    # Store as Mbps in the dict representation
                    iface.__dict__['rx_mbps'] = (rx_rate * 8) / (1024 * 1024)
                    iface.__dict__['tx_mbps'] = (tx_rate * 8) / (1024 * 1024)
                self._prev_net_stats[key] = (iface.rx_bytes, iface.tx_bytes)

            self._prev_net_time = current_time

        except Exception as e:
            print(f"Network interface error: {e}")

        return interfaces

    def collect(self) -> SystemMetrics:
        """Collect all system metrics."""
        self.metrics.timestamp = time.time()

        # CPU
        if self._is_macos:
            self.metrics.cpu_percent = self._get_cpu_percent_macos()
        else:
            self.metrics.cpu_percent = self._get_cpu_percent_linux()

        # Memory
        if self._is_macos:
            total, used = self._get_memory_info_macos()
        else:
            total, used = self._get_memory_info_linux()
        self.metrics.memory_total = total
        self.metrics.memory_used = used
        self.metrics.memory_percent = (used / total * 100) if total > 0 else 0

        # Disk
        total, used = self._get_disk_info()
        self.metrics.disk_total = total
        self.metrics.disk_used = used
        self.metrics.disk_percent = (used / total * 100) if total > 0 else 0

        # Uptime
        self.metrics.uptime_seconds = self._get_uptime()

        # Load average
        try:
            self.metrics.load_avg = os.getloadavg()
        except Exception:
            self.metrics.load_avg = (0.0, 0.0, 0.0)

        # Network interfaces
        self.metrics.interfaces = self._get_network_interfaces()

        self._notify_callbacks()
        return self.metrics

    def _collect_loop(self):
        """Background collection loop."""
        while self._running:
            try:
                self.collect()
            except Exception as e:
                print(f"Metrics collection error: {e}")
            time.sleep(self.collect_interval)

    def start(self):
        """Start background collection."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()
        print(f"System metrics collector started (interval: {self.collect_interval}s)")

    def stop(self):
        """Stop background collection."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("System metrics collector stopped")

    def get_metrics(self) -> dict:
        """Get current metrics."""
        return self.metrics.to_dict()
