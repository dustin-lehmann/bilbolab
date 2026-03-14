# Network Monitor

A real-time network monitoring dashboard for experiment networks. Displays internet connectivity, discovered devices, monitored hosts with ping status, and OpenWRT router integration.

## Features

- Real-time internet connectivity monitoring
- Network device discovery (ARP scanning)
- Host ping monitoring with latency tracking and signal strength visualization
- OpenWRT router integration (WiFi SSIDs, connected clients)
- Right-click context menus for SSH access and host management
- Persistent configuration (YAML)
- mDNS advertisement (accessible via `network.local`)

## Quick Start

### 1. Install Python Dependencies

```bash
cd software/extensions/apps/network_monitor
pip install flask flask-socketio flask-cors eventlet pyyaml zeroconf
```

### 2. Build Frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3. Configure

Edit `config.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 8500

mdns:
  enabled: true
  hostname: "network"  # Accessible at http://network.local:8500

monitored_hosts:
  - name: myhost.local
    ip: 192.168.1.100
    username: admin  # Optional: for SSH access

openwrt:
  enabled: true
  ip: "192.168.1.1"
  username: "root"
  password: "your-password"
```

### 4. Run

```bash
python network_monitor_app.py
```

Or use the quick start script:
```bash
./run.sh
```

Access at: http://localhost:8500 or http://network.local:8500

---

## OpenWRT Router Setup

To enable full OpenWRT integration, you need to configure ubus HTTP access on your router.

### 1. Install Required Packages

SSH into your router:
```bash
ssh root@192.168.1.1
opkg update
opkg install uhttpd-mod-ubus
```

### 2. Configure ubus ACL Permissions

Create an ACL file to allow access to network information:

```bash
cat > /usr/share/rpcd/acl.d/network-monitor.json << 'EOF'
{
  "network-monitor": {
    "description": "Network monitor access",
    "read": {
      "ubus": {
        "system": ["info", "board"],
        "network.interface": ["dump", "status"],
        "network.wireless": ["status"],
        "network.device": ["status"],
        "dhcp": ["ipv4leases"],
        "hostapd.*": ["get_clients"],
        "iwinfo": ["info", "scan", "assoclist"]
      }
    }
  }
}
EOF
```

### 3. Restart Services

```bash
/etc/init.d/rpcd restart
/etc/init.d/uhttpd restart
```

### 4. Verify

Test ubus access:
```bash
curl -X POST http://192.168.1.1/ubus -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"call","params":["00000000000000000000000000000000","session","login",{"username":"root","password":"your-password"}]}'
```

---

## Usage

### Adding Monitored Hosts

1. **From the UI**: Enter hostname/IP and optional username in the form, click "Add"
2. **Right-click a network device**: Select "Add to Monitored Hosts"
3. **Edit config.yaml**: Add entries to `monitored_hosts` list

### SSH Access

Right-click an online monitored host:
- **Open SSH Terminal**: Opens `ssh://user@host` URL (requires terminal app to handle ssh:// URLs)
- **Copy SSH Command**: Copies `ssh user@host` to clipboard

#### Configure iTerm2 for ssh:// URLs (macOS)

1. Open iTerm2 → Settings → General → Selection
2. Find URL Schemes section
3. Set iTerm2 as handler for `ssh://`

### Changing Username

Right-click a monitored host → "Change Username"

---

## Configuration Reference

### config.yaml

```yaml
server:
  host: "0.0.0.0"      # Listen address
  port: 8500           # HTTP/WebSocket port

mdns:
  enabled: true        # Enable mDNS advertisement
  hostname: "network"  # .local hostname (network.local)

intervals:
  scan: 15.0           # Network scan interval (seconds)
  ping: 2.0            # Ping interval for monitored hosts
  internet: 5.0        # Internet check interval
  metrics: 2.0         # System metrics collection interval
  openwrt: 10.0        # OpenWRT polling interval

monitored_hosts:       # Hosts to monitor
  - name: host1.local
    ip: 192.168.1.10   # Optional: use IP instead of DNS
    username: admin    # Optional: for SSH

openwrt:
  enabled: false       # Enable OpenWRT integration
  ip: "192.168.1.1"
  username: "root"
  password: ""
```

---

## Troubleshooting

### OpenWRT "Access denied" errors

The ubus ACL doesn't have required permissions. See "OpenWRT Router Setup" above.

### Frontend not loading

Build the frontend:
```bash
cd frontend && npm install && npm run build
```

### mDNS not working

- Ensure `zeroconf` is installed: `pip install zeroconf`
- Check firewall allows mDNS (UDP port 5353)
- On Linux, you may need `avahi-daemon` running

### SSH URL not opening terminal

- macOS: Configure Terminal.app or iTerm2 to handle `ssh://` URLs
- Use "Copy SSH Command" as alternative

---

## Development

### Frontend Development

```bash
cd frontend
npm run dev  # Starts dev server at http://localhost:9201
```

The dev server proxies API requests to the backend at port 8500.

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Overall system status |
| `GET /api/devices` | Discovered network devices |
| `GET /api/monitored` | Monitored hosts with ping status |
| `GET /api/internet` | Internet connectivity status |
| `GET /api/metrics` | System metrics (CPU, RAM, etc.) |
| `GET /api/openwrt` | OpenWRT router stats |
| `POST /api/monitor/add` | Add host to monitoring |
| `POST /api/monitor/remove` | Remove host from monitoring |

### WebSocket Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `init` | Server→Client | Initial state on connect |
| `internet_update` | Server→Client | Internet status change |
| `devices_update` | Server→Client | Network devices updated |
| `ping_update` | Server→Client | Host ping result |
| `metrics_update` | Server→Client | System metrics |
| `openwrt_update` | Server→Client | Router stats |
| `add_monitor` | Client→Server | Add host to monitoring |
| `remove_monitor` | Client→Server | Remove host |
| `update_monitor` | Client→Server | Update host (e.g., username) |
