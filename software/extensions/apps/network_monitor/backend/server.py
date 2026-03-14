"""
Network Monitor Server
Flask-SocketIO backend serving the network monitoring dashboard.
"""

import os
import sys
import json
import time
import threading
from pathlib import Path

# Monkey-patch for eventlet (must be before other imports)
try:
    import eventlet
    eventlet.monkey_patch()
    ASYNC_MODE = 'eventlet'
except ImportError:
    ASYNC_MODE = 'threading'

from flask import Flask, send_from_directory, jsonify, request, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from extensions.apps.network_monitor.backend.network_scanner import NetworkScanner
from extensions.apps.network_monitor.backend.ping_monitor import PingMonitor
from extensions.apps.network_monitor.backend.internet_checker import InternetChecker
from extensions.apps.network_monitor.backend.system_metrics import SystemMetricsCollector
from extensions.apps.network_monitor.backend.openwrt_client import OpenWRTIntegration


class NetworkMonitorServer:
    """Main server class for the network monitor."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8500,
        static_folder: str = None,
        config: dict = None,
        config_path: str = None
    ):
        self.host = host
        self.port = port
        self.config = config or {}
        self.config_path = config_path

        # Determine static folder
        if static_folder:
            self.static_folder = static_folder
        else:
            # Default to frontend dist folder
            self.static_folder = str(Path(__file__).parent.parent / "frontend" / "dist")

        # Flask app
        self.app = Flask(
            __name__,
            static_folder=self.static_folder,
            static_url_path=""
        )
        CORS(self.app)

        # SocketIO
        self.socketio = SocketIO(
            self.app,
            cors_allowed_origins="*",
            async_mode=ASYNC_MODE,
            ping_timeout=60,
            ping_interval=25,
            logger=False,
            engineio_logger=False
        )
        print(f"SocketIO async mode: {ASYNC_MODE}")

        # Components
        self.scanner = NetworkScanner(
            scan_interval=self.config.get("scan_interval", 15.0)
        )
        self.ping_monitor = PingMonitor(
            ping_interval=self.config.get("ping_interval", 2.0),
            failure_threshold=self.config.get("failure_threshold", 5),
            auto_remove=False  # Never auto-remove, keep hosts visible
        )
        self.internet_checker = InternetChecker(
            check_interval=self.config.get("internet_check_interval", 5.0)
        )
        self.metrics_collector = SystemMetricsCollector(
            collect_interval=self.config.get("metrics_interval", 2.0)
        )

        # OpenWRT integration (optional)
        self.openwrt: OpenWRTIntegration = None
        if self.config.get("openwrt_enabled", False):
            self.openwrt = OpenWRTIntegration(
                router_ip=self.config.get("openwrt_ip", "192.168.1.1"),
                username=self.config.get("openwrt_username", "root"),
                password=self.config.get("openwrt_password", ""),
                poll_interval=self.config.get("openwrt_interval", 10.0)
            )

        # Monitored hosts from config (guard against None)
        self.monitored_hostnames = self.config.get("monitored_hosts") or []

        # Setup routes and handlers
        self._setup_routes()
        self._setup_socketio()
        self._setup_callbacks()

    def _setup_routes(self):
        """Setup Flask routes."""

        @self.app.route("/")
        def index():
            # Check if frontend is built
            import os
            index_path = os.path.join(self.static_folder, "index.html") if self.static_folder else None
            if not index_path or not os.path.exists(index_path):
                return self._dev_page()
            return send_from_directory(self.static_folder, "index.html")

        def _dev_page_inner():
            return self._dev_page()

        self._dev_page_route = _dev_page_inner

        @self.app.route("/api/status")
        def api_status():
            return jsonify({
                "status": "running",
                "internet": self.internet_checker.get_status(),
                "devices_count": len(self.scanner.get_devices()),
                "monitored_hosts_count": len(self.ping_monitor.get_hosts()),
                "openwrt_available": self.openwrt.is_available() if self.openwrt else False
            })

        @self.app.route("/api/devices")
        def api_devices():
            return jsonify(self.scanner.get_devices())

        @self.app.route("/api/monitored")
        def api_monitored():
            return jsonify(self.ping_monitor.get_hosts())

        @self.app.route("/api/internet")
        def api_internet():
            return jsonify(self.internet_checker.get_status())

        @self.app.route("/api/metrics")
        def api_metrics():
            return jsonify(self.metrics_collector.get_metrics())

        @self.app.route("/api/openwrt")
        def api_openwrt():
            if self.openwrt:
                return jsonify(self.openwrt.get_stats())
            return jsonify({"error": "OpenWRT integration not enabled"})

        @self.app.route("/api/monitor/add", methods=["POST"])
        def api_monitor_add():
            data = request.get_json()
            hostname = data.get("hostname")
            ip = data.get("ip", "")
            if hostname:
                self.ping_monitor.add_host(hostname, ip)
                return jsonify({"success": True})
            return jsonify({"error": "Hostname required"}), 400

        @self.app.route("/api/monitor/remove", methods=["POST"])
        def api_monitor_remove():
            data = request.get_json()
            hostname = data.get("hostname")
            if hostname:
                self.ping_monitor.remove_host(hostname)
                return jsonify({"success": True})
            return jsonify({"error": "Hostname required"}), 400

        # Catch-all for SPA routing
        @self.app.errorhandler(404)
        def not_found(e):
            import os
            index_path = os.path.join(self.static_folder, "index.html") if self.static_folder else None
            if not index_path or not os.path.exists(index_path):
                return self._dev_page()
            return send_from_directory(self.static_folder, "index.html")

    def _dev_page(self):
        """Return a development page when frontend is not built."""
        from flask import Response
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Network Monitor - Dev Mode</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'JetBrains Mono', 'Courier New', monospace;
            background: #0a0a0f;
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container { max-width: 800px; text-align: center; }
        h1 {
            color: #00f0ff;
            font-size: 28px;
            margin-bottom: 20px;
            text-shadow: 0 0 20px rgba(0, 240, 255, 0.3);
        }
        .status { margin: 30px 0; }
        .status-item {
            background: #16161f;
            border: 1px solid #2a2a3a;
            border-radius: 8px;
            padding: 15px 20px;
            margin: 10px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .status-label { color: #888; }
        .status-value { color: #00ff88; font-weight: bold; }
        .status-value.warn { color: #ffcc00; }
        .instructions {
            background: #1a1a24;
            border-left: 3px solid #00f0ff;
            padding: 20px;
            margin: 20px 0;
            text-align: left;
        }
        code {
            background: #0a0a0f;
            padding: 2px 8px;
            border-radius: 4px;
            color: #ff00aa;
        }
        pre {
            background: #0a0a0f;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            margin: 10px 0;
            text-align: left;
        }
        a { color: #00f0ff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Network Monitor</h1>
        <p style="color: #ffcc00;">Frontend not built - running in API-only mode</p>

        <div class="status">
            <div class="status-item">
                <span class="status-label">Backend Server</span>
                <span class="status-value">Running</span>
            </div>
            <div class="status-item">
                <span class="status-label">Frontend</span>
                <span class="status-value warn">Not Built</span>
            </div>
            <div class="status-item">
                <span class="status-label">API Endpoints</span>
                <span class="status-value">Available</span>
            </div>
        </div>

        <div class="instructions">
            <h3 style="color: #00f0ff; margin-bottom: 10px;">To build the frontend:</h3>
            <pre>cd software/extensions/network_monitor/frontend
npm install
npm run build</pre>
            <p style="margin-top: 15px;">Or run in development mode:</p>
            <pre>npm run dev</pre>
            <p style="margin-top: 10px;">Then access at <a href="http://localhost:9201">http://localhost:9201</a></p>
        </div>

        <div class="instructions">
            <h3 style="color: #00f0ff; margin-bottom: 10px;">API Endpoints:</h3>
            <p><code>GET /api/status</code> - Overall status</p>
            <p><code>GET /api/devices</code> - Network devices</p>
            <p><code>GET /api/internet</code> - Internet status</p>
            <p><code>GET /api/metrics</code> - System metrics</p>
            <p><code>GET /api/monitored</code> - Monitored hosts</p>
        </div>
    </div>
</body>
</html>"""
        return Response(html, mimetype='text/html')

    def _setup_socketio(self):
        """Setup SocketIO event handlers."""

        @self.socketio.on("connect")
        def handle_connect():
            print(f"Client connected: {request.sid}")
            # Send initial state
            emit("init", {
                "internet": self.internet_checker.get_status(),
                "devices": self.scanner.get_devices(),
                "monitored": self.ping_monitor.get_hosts(),
                "metrics": self.metrics_collector.get_metrics(),
                "openwrt": self.openwrt.get_stats() if self.openwrt else None,
                "config": {
                    "monitored_hostnames": self.monitored_hostnames,
                    "openwrt_enabled": self.openwrt is not None
                }
            })

        @self.socketio.on("disconnect")
        def handle_disconnect():
            print(f"Client disconnected: {request.sid}")

        @self.socketio.on("add_monitor")
        def handle_add_monitor(data):
            hostname = data.get("hostname")
            ip = data.get("ip", "")
            username = data.get("username", "")
            description = data.get("description", "")
            persist = data.get("persist", False)
            if hostname:
                self.ping_monitor.add_host(hostname, ip, username, description)
                if persist:
                    self._persist_add_host(hostname, ip, username, description)
                emit("monitor_added", {"hostname": hostname})

        @self.socketio.on("remove_monitor")
        def handle_remove_monitor(data):
            hostname = data.get("hostname")
            persist = data.get("persist", False)
            if hostname:
                self.ping_monitor.remove_host(hostname)
                if persist:
                    self._persist_remove_host(hostname)
                emit("monitor_removed", {"hostname": hostname})

        @self.socketio.on("update_monitor")
        def handle_update_monitor(data):
            hostname = data.get("hostname")
            persist = data.get("persist", False)
            if hostname:
                if "username" in data:
                    self.ping_monitor.update_host_username(hostname, data["username"])
                if "description" in data:
                    self.ping_monitor.update_host_description(hostname, data["description"])
                if persist:
                    self._persist_update_host(hostname, data.get("username"), data.get("description"))
                emit("monitor_updated", {"hostname": hostname, "username": data.get("username", ""), "description": data.get("description", "")})

        @self.socketio.on("request_scan")
        def handle_request_scan():
            """Trigger immediate network scan."""
            threading.Thread(target=self.scanner.scan, daemon=True).start()

    def _setup_callbacks(self):
        """Setup callbacks from monitoring components."""

        def emit_devices(devices):
            self.socketio.emit("devices_update", devices)

        def emit_ping_status(host_data):
            self.socketio.emit("ping_update", host_data)

        def emit_host_removed(host_data):
            self.socketio.emit("host_removed", host_data)

        def emit_internet_status(status):
            self.socketio.emit("internet_update", status)

        def emit_metrics(metrics):
            self.socketio.emit("metrics_update", metrics)

        def emit_openwrt(stats):
            self.socketio.emit("openwrt_update", stats)

        self.scanner.on_update(emit_devices)
        self.ping_monitor.on_update(emit_ping_status)
        self.ping_monitor.on_removal(emit_host_removed)
        self.internet_checker.on_update(emit_internet_status)
        self.metrics_collector.on_update(emit_metrics)

        if self.openwrt:
            self.openwrt.on_update(emit_openwrt)

    def start(self):
        """Start all monitoring services."""
        print(f"\n{'='*60}")
        print("  Network Monitor Server")
        print(f"{'='*60}")
        print(f"  Host: {self.host}:{self.port}")
        print(f"  Static folder: {self.static_folder}")
        print(f"  Monitored hosts: {self.monitored_hostnames}")
        if self.openwrt:
            print(f"  OpenWRT: {self.config.get('openwrt_ip', 'N/A')}")
        print(f"{'='*60}\n")

        # Add initial monitored hosts
        for hostname in self.monitored_hostnames:
            if isinstance(hostname, dict):
                self.ping_monitor.add_host(
                    hostname.get("name", ""),
                    hostname.get("ip", ""),
                    hostname.get("username", ""),
                    hostname.get("description", "")
                )
            else:
                self.ping_monitor.add_host(hostname)

        # Start all background services
        self.scanner.start()
        self.ping_monitor.start()
        self.internet_checker.start()
        self.metrics_collector.start()

        if self.openwrt:
            self.openwrt.start()

        # Run Flask-SocketIO
        self.socketio.run(
            self.app,
            host=self.host,
            port=self.port,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        )

    def stop(self):
        """Stop all services."""
        self.scanner.stop()
        self.ping_monitor.stop()
        self.internet_checker.stop()
        self.metrics_collector.stop()
        if self.openwrt:
            self.openwrt.stop()


    def _persist_add_host(self, hostname: str, ip: str = "", username: str = "", description: str = ""):
        """Add host to config file."""
        if not self.config_path:
            return

        try:
            import yaml
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f) or {}

            if 'monitored_hosts' not in config or config['monitored_hosts'] is None:
                config['monitored_hosts'] = []

            # Check if already exists
            existing = [h for h in config['monitored_hosts']
                       if (isinstance(h, dict) and h.get('name') == hostname) or h == hostname]
            if not existing:
                if ip or username or description:
                    host_entry = {'name': hostname}
                    if ip:
                        host_entry['ip'] = ip
                    if username:
                        host_entry['username'] = username
                    if description:
                        host_entry['description'] = description
                    config['monitored_hosts'].append(host_entry)
                else:
                    config['monitored_hosts'].append(hostname)

                with open(self.config_path, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                print(f"Persisted host to config: {hostname}")
        except Exception as e:
            print(f"Error persisting host: {e}")

    def _persist_remove_host(self, hostname: str):
        """Remove host from config file."""
        if not self.config_path:
            return

        try:
            import yaml
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f) or {}

            if 'monitored_hosts' not in config or config['monitored_hosts'] is None:
                return

            # Remove matching entries
            config['monitored_hosts'] = [
                h for h in config['monitored_hosts']
                if not ((isinstance(h, dict) and h.get('name') == hostname) or h == hostname)
            ]

            with open(self.config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            print(f"Removed host from config: {hostname}")
        except Exception as e:
            print(f"Error removing host from config: {e}")

    def _persist_update_host(self, hostname: str, username: str = None, description: str = None):
        """Update host username/description in config file."""
        if not self.config_path:
            return

        try:
            import yaml
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f) or {}

            if 'monitored_hosts' not in config or config['monitored_hosts'] is None:
                return

            # Find and update the host entry
            for i, h in enumerate(config['monitored_hosts']):
                if isinstance(h, dict) and h.get('name') == hostname:
                    if username is not None:
                        config['monitored_hosts'][i]['username'] = username
                    if description is not None:
                        config['monitored_hosts'][i]['description'] = description
                    break
                elif h == hostname:
                    # Convert string entry to dict
                    new_entry = {'name': hostname}
                    if username is not None:
                        new_entry['username'] = username
                    if description is not None:
                        new_entry['description'] = description
                    config['monitored_hosts'][i] = new_entry
                    break

            with open(self.config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            print(f"Updated config for {hostname}")
        except Exception as e:
            print(f"Error updating host in config: {e}")


def create_server(config: dict = None, config_path: str = None) -> NetworkMonitorServer:
    """Factory function to create server instance."""
    return NetworkMonitorServer(config=config, config_path=config_path)
