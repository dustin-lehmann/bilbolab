# Hosting Content Server on Linux

This guide covers hosting the content server on a Linux PC and exposing it to the internet via Cloudflare Tunnel at `bilbolab.io`.

## Prerequisites

- Linux PC with Python 3.10+ and Node.js 18+
- Domain `bilbolab.io` with nameservers pointed to Cloudflare
- Cloudflare account with the domain added

## Architecture

```
Internet → bilbolab.io → Cloudflare Edge → Cloudflare Tunnel → localhost:9300
```

The tunnel creates an outbound-only connection from your server to Cloudflare, so no port forwarding or static IP is required.

---

## 1. Install Dependencies

### System packages (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm
```

### Cloudflared

```bash
# Download and install
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
rm cloudflared.deb

# Verify installation
cloudflared --version
```

---

## 2. Set Up the Content Server

### Clone/copy the project

```bash
# Copy the content_server directory to your Linux PC
# Example path: /home/user/content_server
```

### Install Python dependencies

```bash
cd /path/to/content_server
pip3 install flask
```

### Install frontend dependencies and build

```bash
cd frontend
npm install
npm run build
cd ..
```

### Test locally

```bash
# Start the server
python3 server.py

# In another terminal, verify it's running
curl http://localhost:9300
```

---

## 3. Set Up Cloudflare Tunnel

### Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This opens a browser to authorize your Cloudflare account. The credentials are saved to `~/.cloudflared/`.

### Create the tunnel (if not already created)

```bash
cloudflared tunnel create bilbolab
```

Note the tunnel ID (e.g., `6cecad8b-0417-40d3-9358-1960a00f49c4`).

### Migrating an Existing Tunnel vs Creating a New One

If the tunnel was already created on another machine (e.g., MacBook), you have two options:

**Option 1: Copy the credentials file (recommended)**

This is simpler since DNS routes are already configured.

```bash
# On the source machine (e.g., MacBook), find the credentials file
ls ~/.cloudflared/*.json

# Copy to the Linux PC
scp ~/.cloudflared/6cecad8b-0417-40d3-9358-1960a00f49c4.json user@linux-pc:~/.cloudflared/
```

The credentials file is just a JSON file with an authentication secret—it's not tied to a specific machine. Use the same tunnel ID in your config.yml.

**Option 2: Create a new tunnel on the Linux PC**

If you can't copy the credentials, create a fresh tunnel:

```bash
# Authenticate (opens browser)
cloudflared tunnel login

# Create new tunnel
cloudflared tunnel create bilbolab-linux
```

Note the new tunnel ID. Then update DNS to point to the new tunnel:

1. Go to Cloudflare dashboard → bilbolab.io → DNS
2. Delete the existing CNAME records for `@` and `www`
3. Add new routes:
   ```bash
   cloudflared tunnel route dns <new-tunnel-id> bilbolab.io
   cloudflared tunnel route dns <new-tunnel-id> www.bilbolab.io
   ```

Update your config.yml with the new tunnel ID and credentials path.

### Create tunnel configuration

```bash
mkdir -p ~/.cloudflared
nano ~/.cloudflared/config.yml
```

Add the following content:

```yaml
tunnel: 6cecad8b-0417-40d3-9358-1960a00f49c4
credentials-file: /home/YOUR_USERNAME/.cloudflared/6cecad8b-0417-40d3-9358-1960a00f49c4.json

ingress:
  - hostname: bilbolab.io
    service: http://localhost:9300
  - hostname: www.bilbolab.io
    service: http://localhost:9300
  - service: http_status:404
```

Replace `YOUR_USERNAME` with your actual Linux username.

### Add DNS routes (if not already configured)

```bash
cloudflared tunnel route dns bilbolab bilbolab.io
cloudflared tunnel route dns bilbolab www.bilbolab.io
```

### Test the tunnel

```bash
cloudflared tunnel run bilbolab
```

You should see "Registered tunnel connection" messages.

---

## 4. Run as Systemd Services

### Content Server Service

Create the service file:

```bash
sudo nano /etc/systemd/system/content-server.service
```

Add:

```ini
[Unit]
Description=BilboLab Content Server
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/content_server
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Cloudflare Tunnel Service

```bash
sudo cloudflared service install
```

This creates a systemd service automatically using your `~/.cloudflared/config.yml`.

### Enable and start services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services to start on boot
sudo systemctl enable content-server
sudo systemctl enable cloudflared

# Start services
sudo systemctl start content-server
sudo systemctl start cloudflared

# Check status
sudo systemctl status content-server
sudo systemctl status cloudflared
```

---

## 5. Managing the Services

### View logs

```bash
# Content server logs
sudo journalctl -u content-server -f

# Cloudflared logs
sudo journalctl -u cloudflared -f
```

### Restart services

```bash
sudo systemctl restart content-server
sudo systemctl restart cloudflared
```

### Stop services

```bash
sudo systemctl stop content-server
sudo systemctl stop cloudflared
```

---

## 6. Updating Content

When you update videos, experiments, or other content:

1. Copy new files to the appropriate directories (`videos/`, `thumbnails/`, etc.)
2. Update `experiments.json` if adding new experiments
3. No service restart needed for content changes

When you update the frontend code:

```bash
cd /path/to/content_server/frontend
npm run build
# No restart needed if serving static build
```

When you update the Python server:

```bash
sudo systemctl restart content-server
```

---

## 7. Troubleshooting

### Check if services are running

```bash
sudo systemctl status content-server
sudo systemctl status cloudflared
```

### Check if port 9300 is listening

```bash
ss -tlnp | grep 9300
```

### Test local connectivity

```bash
curl http://localhost:9300
```

### Check DNS resolution

```bash
dig bilbolab.io A +short
# Should return a Cloudflare IP (104.x.x.x or similar)

dig bilbolab.io NS +short
# Should return *.ns.cloudflare.com
```

### Check tunnel status in Cloudflare dashboard

1. Go to https://dash.cloudflare.com
2. Select bilbolab.io
3. Go to **Traffic** → **Cloudflare Tunnel**
4. Verify tunnel shows as "Healthy"

### Common issues

| Issue | Solution |
|-------|----------|
| "Connection refused" | Content server not running on port 9300 |
| Strato placeholder page | DNS not propagated; nameservers still at Strato |
| 502 Bad Gateway | Tunnel running but content server not responding |
| Tunnel not connecting | Check credentials file path in config.yml |

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `cloudflared tunnel run bilbolab` | Start tunnel manually |
| `sudo systemctl start cloudflared` | Start tunnel service |
| `sudo systemctl start content-server` | Start content server |
| `sudo journalctl -u cloudflared -f` | View tunnel logs |
| `sudo journalctl -u content-server -f` | View server logs |

---

## Configuration Files

| File | Purpose |
|------|---------|
| `~/.cloudflared/config.yml` | Tunnel configuration |
| `~/.cloudflared/<tunnel-id>.json` | Tunnel credentials |
| `/etc/systemd/system/content-server.service` | Content server systemd unit |
| `experiments.json` | Experiment definitions |
| `settings.json` | Application settings |
