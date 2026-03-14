#!/usr/bin/env python3
"""
Network Monitor Application
Main entry point for the network monitoring dashboard.

Usage:
    python network_monitor_app.py [--config config.yaml]

Access:
    http://localhost:8500
    http://network.local:8500 (with mDNS enabled)
"""

import os
import sys
import argparse
import signal
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import yaml

from core.utils.mdns.mdns_advertiser import MDNSAdvertiser
from extensions.apps.network_monitor.backend.server import NetworkMonitorServer


class NetworkMonitorApp:
    """Main application class."""

    def __init__(self, config_path: str = None):
        # Store absolute config path for persistence
        if config_path is None:
            self.config_path = str(Path(__file__).parent / "config.yaml")
        else:
            self.config_path = str(Path(config_path).absolute())

        self.config = self._load_config(self.config_path)
        self.server: NetworkMonitorServer = None
        self.mdns_advertiser: MDNSAdvertiser = None
        self._running = False

    def _load_config(self, config_path: str = None) -> dict:
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"

        config = {}
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                print(f"Loaded config from: {config_path}")
        except FileNotFoundError:
            print(f"Config file not found: {config_path}, using defaults")
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")

        return config

    def _build_server_config(self) -> dict:
        """Build server configuration dict."""
        intervals = self.config.get("intervals", {})
        ping_config = self.config.get("ping_monitor", {})
        openwrt_config = self.config.get("openwrt", {})

        return {
            "scan_interval": intervals.get("network_scan", 15.0),
            "ping_interval": intervals.get("ping", 2.0),
            "internet_check_interval": intervals.get("internet_check", 5.0),
            "metrics_interval": intervals.get("system_metrics", 2.0),
            "openwrt_interval": intervals.get("openwrt_poll", 10.0),
            "failure_threshold": ping_config.get("failure_threshold", 5),
            "monitored_hosts": self.config.get("monitored_hosts", []),
            "openwrt_enabled": openwrt_config.get("enabled", False),
            "openwrt_ip": openwrt_config.get("ip", "192.168.1.1"),
            "openwrt_username": openwrt_config.get("username", "root"),
            "openwrt_password": openwrt_config.get("password", ""),
        }

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(sig, frame):
            print("\nShutdown signal received...")
            # Use os._exit for clean exit with eventlet
            # (eventlet's monkey-patched threading doesn't work well in signal handlers)
            import os
            os._exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def init(self):
        """Initialize the application."""
        print("\n" + "=" * 60)
        print("  Network Monitor - Initializing")
        print("=" * 60)

        server_config = self.config.get("server", {})
        host = server_config.get("host", "0.0.0.0")
        port = server_config.get("port", 8500)

        # Determine static folder
        static_folder = Path(__file__).parent / "frontend" / "dist"
        if not static_folder.exists():
            print(f"Warning: Frontend not built at {static_folder}")
            print("Run 'npm run build' in the frontend directory")
            static_folder = None

        self.server = NetworkMonitorServer(
            host=host,
            port=port,
            static_folder=str(static_folder) if static_folder else None,
            config=self._build_server_config(),
            config_path=self.config_path
        )

        # Setup mDNS if enabled
        mdns_config = self.config.get("mdns", {})
        if mdns_config.get("enabled", True):
            hostname = mdns_config.get("hostname", "network")
            advertised_port = 80 if mdns_config.get("use_port_80", False) else port
            self.mdns_advertiser = MDNSAdvertiser(
                hostname=hostname,
                port=advertised_port
            )
            print(f"mDNS will advertise: http://{hostname}.local:{advertised_port}")

        self._setup_signal_handlers()
        print("Initialization complete\n")

    def start(self):
        """Start the application."""
        self._running = True

        # Start mDNS
        if self.mdns_advertiser:
            self.mdns_advertiser.start()

        # Start server (this blocks)
        print("\nStarting server...")
        self.server.start()

    def stop(self):
        """Stop the application."""
        if not self._running:
            return

        self._running = False
        print("\nStopping services...")

        if self.server:
            self.server.stop()

        if self.mdns_advertiser:
            self.mdns_advertiser.stop()

        print("Application stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Network Monitor Application")
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to configuration file"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="Override server port"
    )
    parser.add_argument(
        "--no-mdns",
        action="store_true",
        help="Disable mDNS advertisement"
    )

    args = parser.parse_args()

    app = NetworkMonitorApp(config_path=args.config)

    # Apply command line overrides
    if args.port:
        app.config.setdefault("server", {})["port"] = args.port
    if args.no_mdns:
        app.config.setdefault("mdns", {})["enabled"] = False

    app.init()
    app.start()


if __name__ == "__main__":
    main()
