<template>
  <div class="app" @click="hideContextMenu">
    <!-- Connection overlay -->
    <div v-if="!connected" class="connection-overlay">
      <div class="connection-spinner"></div>
      <div class="connection-text">Connecting to server...</div>
    </div>

    <!-- Context Menu -->
    <div
      v-if="contextMenu.show"
      class="context-menu"
      :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
      @click.stop
    >
      <div
        v-for="item in contextMenu.items"
        :key="item.label"
        class="context-menu-item"
        @click="item.action"
      >
        {{ item.label }}
      </div>
    </div>

    <!-- Notifications -->
    <transition-group name="notification">
      <div
        v-for="notification in notifications"
        :key="notification.id"
        class="notification"
        :class="notification.type"
      >
        <span class="notification-icon">{{ notification.type === 'success' ? '✓' : '⚠' }}</span>
        <div class="notification-content">
          <div class="notification-title">{{ notification.title }}</div>
          <div class="notification-message">{{ notification.message }}</div>
        </div>
        <button class="notification-close" @click="dismissNotification(notification.id)">×</button>
      </div>
    </transition-group>

    <!-- Header -->
    <header class="header">
      <div class="header-left">
        <img src="/bilbolab_logo.png" alt="BilboLab" class="header-logo" />
        <div class="header-title">Network Monitor</div>
      </div>
      <div class="header-status">
        <!-- Router status -->
        <div v-if="openwrt" class="status-indicator">
          <span class="status-dot" :class="openwrt.router_online ? 'online' : 'offline'"></span>
          <span>Router {{ openwrt.router_online ? 'Online' : 'Offline' }}</span>
        </div>
        <!-- WiFi Networks from OpenWRT -->
        <div v-if="openwrt && openwrt.router_online && openwrt.ap_networks && openwrt.ap_networks.length" class="wifi-info">
          <span class="wifi-label">AP:</span>
          <span v-for="net in openwrt.ap_networks" :key="net.ssid" class="wifi-ssid">{{ net.ssid }}</span>
        </div>
        <div v-if="openwrt && openwrt.router_online && openwrt.sta_networks && openwrt.sta_networks.length" class="wifi-info">
          <span class="wifi-label">STA:</span>
          <span v-for="net in openwrt.sta_networks" :key="net.ssid" class="wifi-ssid" :class="{ connected: net.connected }">
            {{ net.ssid }} <span v-if="net.signal" class="wifi-signal">({{ net.signal }}dBm)</span>
          </span>
        </div>
        <div class="status-indicator">
          <span class="status-dot" :class="internet.connected ? 'online' : 'offline'"></span>
          <span>{{ internet.connected ? 'Internet Online' : 'Internet Offline' }}</span>
        </div>
        <div class="status-indicator">
          <span class="status-dot" :class="connected ? 'online' : 'offline'"></span>
          <span>{{ connected ? 'Connected' : 'Disconnected' }}</span>
        </div>
      </div>
    </header>

    <!-- Main content - single screen layout -->
    <main class="main-grid">
      <!-- Status cards row -->
      <div class="status-grid">
        <div class="status-card internet">
          <div class="status-card-label">Internet</div>
          <div class="status-card-value">{{ internet.connected ? 'ONLINE' : 'OFFLINE' }}</div>
          <div class="status-card-sub">
            {{ internet.connected ? `${formatLatency(internet.latency_ms)}ms latency` : 'No connection' }}
          </div>
        </div>

        <div class="status-card devices">
          <div class="status-card-label">Network Devices</div>
          <div class="status-card-value">{{ devices.length }}</div>
          <div class="status-card-sub">discovered on network</div>
        </div>

        <div class="status-card monitored">
          <div class="status-card-label">Monitored Hosts</div>
          <div class="status-card-value">{{ monitoredOnlineCount }}/{{ allMonitored.length }}</div>
          <div class="status-card-sub">hosts responding</div>
        </div>

        <div class="status-card system">
          <div class="status-card-label">System Load</div>
          <div class="status-card-value">{{ metrics.cpu_percent }}%</div>
          <div class="status-card-sub">CPU · {{ metrics.memory_percent }}% RAM</div>
        </div>
      </div>

      <!-- Panels row -->
      <div class="panels-row">
      <!-- Monitored Hosts Panel -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title">Monitored Hosts</span>
          <div class="panel-controls">
            <label class="toggle-label">
              <input type="checkbox" v-model="showOfflineHosts" @change="saveShowOffline" class="toggle-checkbox" />
              <span class="toggle-text">Show offline</span>
            </label>
            <span class="panel-badge">{{ filteredMonitored.length }} hosts</span>
          </div>
        </div>
        <div class="panel-content">
          <!-- Add host form -->
          <div class="add-host-form">
            <input
              v-model="newHostname"
              class="add-host-input"
              type="text"
              placeholder="hostname or IP..."
              @keyup.enter="addMonitoredHost"
            />
            <input
              v-model="newUsername"
              class="add-host-input add-host-input-small"
              type="text"
              placeholder="user"
              @keyup.enter="addMonitoredHost"
            />
            <button class="add-host-btn" @click="addMonitoredHost">Add</button>
          </div>

          <div v-if="filteredMonitored.length === 0" class="empty-state">
            <div class="empty-state-icon">📡</div>
            <div class="empty-state-text">
              {{ allMonitored.length === 0 ? 'No hosts being monitored.' : 'No online hosts.' }}<br>
              {{ allMonitored.length === 0 ? 'Add a hostname above to start.' : 'Enable "Show offline" to see all.' }}
            </div>
          </div>

          <div v-else class="device-list">
            <div
              v-for="host in filteredMonitored"
              :key="host.hostname"
              class="monitored-item clickable"
              :class="host.status"
              @contextmenu.prevent="showMonitoredContextMenu($event, host)"
            >
              <div class="monitored-status"></div>
              <div class="monitored-info">
                <div class="monitored-hostname">
                  <template v-if="host.description">
                    <span class="host-description">{{ host.description }}</span>
                    <span class="host-hostname-secondary">({{ host.username ? host.username + '@' : '' }}{{ host.hostname }})</span>
                  </template>
                  <template v-else>
                    <span v-if="host.username" class="monitored-user">{{ host.username }}@</span>{{ host.hostname }}
                  </template>
                  <span v-if="getHostConnection(host)" class="host-ssid" :class="{ ethernet: getHostConnection(host) === 'Ethernet' }">
                    {{ getHostConnection(host) }}
                  </span>
                </div>
                <div class="monitored-stats">
                  <span v-if="getHostIP(host)" class="host-ip">{{ getHostIP(host) }}</span>
                  <span>{{ getRecentUptime(host) }}% uptime</span>
                  <span v-if="host.consecutive_failures > 0 && host.consecutive_failures <= 5" class="failure-count">
                    {{ host.consecutive_failures }} failures
                  </span>
                </div>
              </div>
              <div class="monitored-metrics">
                <!-- WiFi signal if available (online only) -->
                <div v-if="host.status === 'online' && getHostSignal(host)" class="metric-display" :title="`WiFi Signal: ${getHostSignal(host)} dBm`">
                  <div class="metric-value" :style="{ color: getSignalColor(getHostSignal(host)) }">
                    {{ getHostSignal(host) }}
                  </div>
                  <div class="metric-unit">dBm</div>
                </div>
                <!-- Latency sparkline (last 2 min rolling, color-coded, online only) -->
                <svg v-if="host.status === 'online'"
                     class="sparkline"
                     viewBox="0 0 120 20"
                     preserveAspectRatio="none">
                  <line v-for="(segment, i) in getSparklineSegments(host.latency_history?.slice(-60) || [], 20, 120)"
                        :key="i"
                        :x1="segment.x1"
                        :y1="segment.y1"
                        :x2="segment.x2"
                        :y2="segment.y2"
                        :stroke="segment.color"
                        stroke-width="1.5"
                        stroke-linecap="round"
                  />
                </svg>
                <!-- Latency display -->
                <div class="metric-display">
                  <div class="metric-value" :style="{ color: host.status === 'online' ? getLatencyColor(host.latency_ms) : 'var(--text-muted)' }">
                    {{ host.status === 'online' ? formatLatency(host.latency_ms) : '—' }}
                  </div>
                  <div class="metric-unit">ms</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Network Devices Panel -->
      <div class="panel">
        <div class="panel-header">
          <span class="panel-title">Network Devices</span>
          <span class="panel-badge">{{ devices.length }} found</span>
        </div>
        <div class="panel-content">
          <div v-if="devices.length === 0" class="empty-state">
            <div class="empty-state-icon">🔍</div>
            <div class="empty-state-text">Scanning network...</div>
          </div>

          <div v-else class="device-list">
            <div
              v-for="device in sortedDevices"
              :key="device.ip"
              class="device-item clickable"
              @contextmenu.prevent="showDeviceContextMenu($event, device)"
            >
              <div>
                <div class="device-hostname">{{ device.hostname }}</div>
                <div class="device-ip">{{ device.ip }}</div>
                <div class="device-meta">
                  <span v-if="device.mac" class="device-mac">{{ device.mac }}</span>
                  <span v-if="device.mac && macToSsid[device.mac.toLowerCase()]" class="device-ssid">
                    {{ macToSsid[device.mac.toLowerCase()] }}
                  </span>
                  <span v-else-if="device.mac && openwrt && openwrt.router_online" class="device-ssid ethernet">
                    Ethernet
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- System & Events Panel (combined) -->
      <div class="panel panel-split">
        <div class="panel-section">
          <div class="panel-header">
            <span class="panel-title">Host System</span>
            <span class="panel-badge">{{ metrics.hostname }}</span>
          </div>
          <div class="panel-content compact">
            <div class="metrics-row">
              <div class="metric-mini">
                <span class="metric-mini-label">CPU</span>
                <span class="metric-mini-value">{{ metrics.cpu_percent }}%</span>
              </div>
              <div class="metric-mini">
                <span class="metric-mini-label">RAM</span>
                <span class="metric-mini-value">{{ metrics.memory_percent }}%</span>
              </div>
              <div class="metric-mini">
                <span class="metric-mini-label">Disk</span>
                <span class="metric-mini-value">{{ metrics.disk_percent }}%</span>
              </div>
              <div class="metric-mini">
                <span class="metric-mini-label">Uptime</span>
                <span class="metric-mini-value">{{ formatUptime(metrics.uptime_hours) }}</span>
              </div>
            </div>
            <div class="load-row">
              <span class="load-label">Load:</span>
              <span class="load-1m">{{ metrics.load_avg?.[0] || 0 }}</span>
              <span class="load-5m">{{ metrics.load_avg?.[1] || 0 }}</span>
              <span class="load-15m">{{ metrics.load_avg?.[2] || 0 }}</span>
            </div>
          </div>
        </div>

        <div class="panel-section panel-section-grow">
          <div class="panel-header">
            <span class="panel-title">Event Log</span>
            <span class="panel-badge">{{ events.length }}</span>
          </div>
          <div class="panel-content">
            <div v-if="events.length === 0" class="empty-state small">
              <div class="empty-state-text">No events yet</div>
            </div>

            <div v-else class="log-list">
              <div
                v-for="event in events.slice(-30).reverse()"
                :key="event.id"
                class="log-item"
                :class="event.type"
              >
                <span class="log-time">{{ formatTime(event.timestamp) }}</span>
                <span class="log-message">{{ event.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      </div>
    </main>

    <!-- Footer -->
    <footer class="footer">
      <div class="footer-left">
        <div class="footer-item">
          <span class="footer-dot"></span>
          <span>Server: {{ serverHost }}</span>
        </div>
        <div class="footer-item">
          <span>Last update: {{ lastUpdate }}</span>
        </div>
      </div>
      <div>
        Network Monitor v1.0 · {{ metrics.platform || 'Unknown' }}
      </div>
    </footer>
  </div>
</template>

<script>
import { io } from 'socket.io-client'

export default {
  name: 'App',

  data() {
    return {
      connected: false,
      socket: null,
      serverHost: window.location.host,

      // State
      internet: {
        connected: false,
        latency_ms: 0,
        method: '',
        dns_working: false,
        gateway_reachable: false
      },
      devices: [],
      allMonitored: [],
      metrics: {
        hostname: '',
        platform: '',
        cpu_percent: 0,
        memory_percent: 0,
        disk_percent: 0,
        uptime_hours: 0,
        load_avg: [0, 0, 0],
        interfaces: []
      },
      openwrt: null,
      events: [],
      notifications: [],

      // UI state
      newHostname: '',
      newUsername: '',
      lastUpdate: 'Never',
      eventId: 0,
      notificationId: 0,
      showOfflineHosts: true,
      seenOnlineHosts: new Set(),
      knownDeviceIPs: new Set(),
      pendingRemovals: new Set(),

      // Context menu
      contextMenu: {
        show: false,
        x: 0,
        y: 0,
        items: []
      }
    }
  },

  computed: {
    sortedDevices() {
      return [...this.devices].sort((a, b) => {
        if (a.hostname && b.hostname) {
          return a.hostname.localeCompare(b.hostname)
        }
        return a.ip.localeCompare(b.ip)
      })
    },

    filteredMonitored() {
      let hosts = this.allMonitored
      if (!this.showOfflineHosts) {
        hosts = hosts.filter(h => h.status === 'online')
      }
      // Sort: online first, then by hostname
      return [...hosts].sort((a, b) => {
        if (a.status === 'online' && b.status !== 'online') return -1
        if (a.status !== 'online' && b.status === 'online') return 1
        return a.hostname.localeCompare(b.hostname)
      })
    },

    monitoredOnlineCount() {
      return this.allMonitored.filter(h => h.status === 'online').length
    },

    // Map MAC addresses to SSID from OpenWRT clients
    macToSsid() {
      const map = {}
      if (this.openwrt && this.openwrt.clients) {
        for (const client of this.openwrt.clients) {
          if (client.mac && client.ssid) {
            map[client.mac.toLowerCase()] = client.ssid
          }
        }
      }
      return map
    },

    // Map IP addresses to SSID from OpenWRT clients
    ipToSsid() {
      const map = {}
      if (this.openwrt && this.openwrt.clients) {
        for (const client of this.openwrt.clients) {
          if (client.ip && client.ssid) {
            map[client.ip] = client.ssid
          }
        }
      }
      return map
    },

    // Map IP addresses to signal strength from OpenWRT clients
    ipToSignal() {
      const map = {}
      if (this.openwrt && this.openwrt.clients) {
        for (const client of this.openwrt.clients) {
          if (client.ip && client.signal_strength) {
            map[client.ip] = client.signal_strength
          }
        }
      }
      return map
    },

    // Map MAC addresses to signal strength from OpenWRT clients
    macToSignal() {
      const map = {}
      if (this.openwrt && this.openwrt.clients) {
        for (const client of this.openwrt.clients) {
          if (client.mac && client.signal_strength) {
            map[client.mac.toLowerCase()] = client.signal_strength
          }
        }
      }
      return map
    },

    // Map IP to connection type (SSID for WiFi, "Ethernet" for wired)
    ipToConnection() {
      const map = {}
      if (this.openwrt && this.openwrt.clients) {
        for (const client of this.openwrt.clients) {
          if (client.ip) {
            if (client.ssid) {
              map[client.ip] = client.ssid
            } else if (client.is_wireless === false || !client.signal_strength) {
              map[client.ip] = 'Ethernet'
            }
          }
        }
      }
      return map
    },

    // Map MAC to SSID from OpenWRT clients (hostapd gives MAC+SSID but not IP)
    macToConnection() {
      const map = {}
      if (this.openwrt && this.openwrt.clients) {
        for (const client of this.openwrt.clients) {
          if (client.mac && client.ssid) {
            map[client.mac.toLowerCase()] = client.ssid
          }
        }
      }
      return map
    },

    // Map IP to MAC from network devices (ARP scan gives IP+MAC)
    ipToMac() {
      const map = {}
      for (const device of this.devices) {
        if (device.ip && device.mac) {
          map[device.ip] = device.mac.toLowerCase()
        }
      }
      return map
    },

    // Map hostname to MAC from network devices (includes base hostname without suffix)
    hostnameToMac() {
      const map = {}
      for (const device of this.devices) {
        if (device.hostname && device.mac) {
          const mac = device.mac.toLowerCase()
          const hostname = device.hostname.toLowerCase()
          map[hostname] = mac
          // Also map base hostname (without .local, .lan, etc.)
          const base = this.getBaseHostname(hostname)
          if (base !== hostname) {
            map[base] = mac
          }
        }
      }
      return map
    }
  },

  mounted() {
    this.loadShowOffline()
    this.connectSocket()
  },

  beforeUnmount() {
    if (this.socket) {
      this.socket.disconnect()
    }
  },

  methods: {
    connectSocket() {
      this.socket = io({
        transports: ['websocket', 'polling'],
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000
      })

      this.socket.on('connect', () => {
        this.connected = true
        this.addEvent('success', 'Connected to server')
      })

      this.socket.on('disconnect', () => {
        this.connected = false
        this.addEvent('error', 'Disconnected from server')
      })

      this.socket.on('init', (data) => {
        this.internet = data.internet || this.internet
        this.devices = data.devices || []
        this.allMonitored = data.monitored || []
        this.metrics = data.metrics || this.metrics
        this.openwrt = data.openwrt

        this.allMonitored.forEach(h => {
          if (h.status === 'online') {
            this.seenOnlineHosts.add(h.hostname)
          }
        })

        // Initialize known devices
        this.knownDeviceIPs = new Set(this.devices.map(d => d.ip))

        this.addEvent('info', 'Received initial state')
        this.updateLastUpdate()
      })

      this.socket.on('internet_update', (data) => {
        const wasConnected = this.internet.connected
        this.internet = data

        if (wasConnected && !data.connected) {
          this.addEvent('error', 'Internet connection lost')
          this.showNotification('error', 'Connection Lost', 'Internet connection is down')
        } else if (!wasConnected && data.connected) {
          this.addEvent('success', 'Internet connection restored')
        }
        this.updateLastUpdate()
      })

      this.socket.on('devices_update', (data) => {
        const newIPs = new Set(data.map(d => d.ip))

        // Check for new devices
        data.forEach(device => {
          if (!this.knownDeviceIPs.has(device.ip)) {
            const name = device.hostname || device.ip
            this.addEvent('success', `Device discovered: ${name}`)
          }
        })

        // Check for removed devices
        this.devices.forEach(device => {
          if (!newIPs.has(device.ip)) {
            const name = device.hostname || device.ip
            this.addEvent('warning', `Device left network: ${name}`)
          }
        })

        this.knownDeviceIPs = newIPs
        this.devices = data
        this.updateLastUpdate()
      })

      this.socket.on('ping_update', (data) => {
        // Ignore updates for hosts pending removal
        if (this.pendingRemovals.has(data.hostname)) {
          return
        }

        const index = this.allMonitored.findIndex(h => h.hostname === data.hostname)
        const wasOnline = index >= 0 && this.allMonitored[index].status === 'online'
        const isNowOnline = data.status === 'online'
        const wasSeenBefore = this.seenOnlineHosts.has(data.hostname)

        if (index >= 0) {
          // Preserve local username if not in update
          if (!data.username && this.allMonitored[index].username) {
            data.username = this.allMonitored[index].username
          }
          this.allMonitored[index] = data
        } else {
          this.allMonitored.push(data)
        }

        if (isNowOnline && !wasSeenBefore) {
          this.seenOnlineHosts.add(data.hostname)
          this.addEvent('success', `Host online: ${data.hostname}`)
          this.showNotification('success', 'Host Online', `${data.hostname} is now responding (${this.formatLatency(data.latency_ms)}ms)`)
          this.playSound('connect')
        } else if (!isNowOnline && wasOnline) {
          this.seenOnlineHosts.delete(data.hostname)
          this.addEvent('warning', `Host offline: ${data.hostname}`)
          this.showNotification('error', 'Host Offline', `${data.hostname} is no longer responding`)
          this.playSound('disconnect')
        }

        this.updateLastUpdate()
      })

      this.socket.on('host_removed', (data) => {
        this.addEvent('warning', `Host removed: ${data.hostname}`)
        this.showNotification('error', 'Host Removed', `${data.hostname} was removed from monitoring`)
        this.allMonitored = this.allMonitored.filter(h => h.hostname !== data.hostname)
        this.seenOnlineHosts.delete(data.hostname)
      })

      this.socket.on('metrics_update', (data) => {
        this.metrics = data
        this.updateLastUpdate()
      })

      this.socket.on('openwrt_update', (data) => {
        this.openwrt = data
        this.updateLastUpdate()
      })

      this.socket.on('monitor_added', (data) => {
        this.addEvent('info', `Host added to config: ${data.hostname}`)
      })

      this.socket.on('monitor_removed', (data) => {
        this.addEvent('info', `Host removed from config: ${data.hostname}`)
      })
    },

    addMonitoredHost() {
      if (!this.newHostname.trim()) return

      this.socket.emit('add_monitor', {
        hostname: this.newHostname.trim(),
        username: this.newUsername.trim() || '',
        persist: true
      })

      this.addEvent('info', `Added host to monitor: ${this.newHostname}`)
      this.newHostname = ''
      this.newUsername = ''
    },

    addMonitoredHostFromDevice(device) {
      const hostname = device.hostname || device.ip
      this.socket.emit('add_monitor', {
        hostname: hostname,
        ip: device.ip,
        persist: true
      })
      this.addEvent('info', `Added device to monitor: ${hostname}`)
    },

    removeMonitoredHost(host) {
      // Mark as pending removal to ignore incoming updates
      this.pendingRemovals.add(host.hostname)

      this.socket.emit('remove_monitor', {
        hostname: host.hostname,
        persist: true
      })
      this.allMonitored = this.allMonitored.filter(h => h.hostname !== host.hostname)
      this.seenOnlineHosts.delete(host.hostname)
      this.addEvent('info', `Removed from monitoring: ${host.hostname}`)
    },

    // Context menu methods
    showDeviceContextMenu(event, device) {
      this.contextMenu = {
        show: true,
        x: event.clientX,
        y: event.clientY,
        items: [
          {
            label: 'Add to Monitored Hosts',
            action: () => {
              this.addMonitoredHostFromDevice(device)
              this.hideContextMenu()
            }
          }
        ]
      }
    },

    showMonitoredContextMenu(event, host) {
      const items = []

      // SSH options only for online hosts
      if (host.status === 'online') {
        items.push({
          label: 'Open SSH Terminal',
          action: () => {
            this.openSSH(host)
            this.hideContextMenu()
          }
        })
        items.push({
          label: 'Copy SSH Command',
          action: () => {
            this.copySSHCommand(host)
            this.hideContextMenu()
          }
        })
      }

      items.push({
        label: 'Change Username',
        action: () => {
          this.changeUsername(host)
          this.hideContextMenu()
        }
      })

      items.push({
        label: host.description ? 'Change Description' : 'Set Description',
        action: () => {
          this.changeDescription(host)
          this.hideContextMenu()
        }
      })

      items.push({
        label: 'Remove from Monitoring',
        action: () => {
          this.removeMonitoredHost(host)
          this.hideContextMenu()
        }
      })

      this.contextMenu = {
        show: true,
        x: event.clientX,
        y: event.clientY,
        items
      }
    },

    changeUsername(host) {
      const newUsername = prompt('Enter SSH username:', host.username || '')
      if (newUsername !== null) {
        // Update locally
        const index = this.allMonitored.findIndex(h => h.hostname === host.hostname)
        if (index >= 0) {
          this.allMonitored[index].username = newUsername
        }

        // Send to backend to persist
        this.socket.emit('update_monitor', {
          hostname: host.hostname,
          username: newUsername,
          persist: true
        })

        this.addEvent('info', `Updated username for ${host.hostname}`)
      }
    },

    changeDescription(host) {
      const newDescription = prompt('Enter description (e.g., ROBOT, OPTITRACK SERVER):', host.description || '')
      if (newDescription !== null) {
        // Update locally
        const index = this.allMonitored.findIndex(h => h.hostname === host.hostname)
        if (index >= 0) {
          this.allMonitored[index].description = newDescription
        }

        // Send to backend to persist
        this.socket.emit('update_monitor', {
          hostname: host.hostname,
          description: newDescription,
          persist: true
        })

        this.addEvent('info', `Updated description for ${host.hostname}`)
      }
    },

    openSSH(host) {
      // Use IP if available, otherwise hostname
      const target = host.ip || host.hostname
      // Include username if specified
      const sshUrl = host.username ? `ssh://${host.username}@${target}` : `ssh://${target}`
      // Open ssh:// URL - macOS Terminal handles this natively
      window.open(sshUrl, '_blank')
      this.addEvent('info', `Opening SSH to ${host.username ? host.username + '@' : ''}${target}`)
    },

    copySSHCommand(host) {
      const target = host.ip || host.hostname
      const sshCommand = host.username ? `ssh ${host.username}@${target}` : `ssh ${target}`

      // Use fallback for HTTP (clipboard API requires HTTPS)
      const textarea = document.createElement('textarea')
      textarea.value = sshCommand
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      try {
        document.execCommand('copy')
        this.addEvent('info', `Copied: ${sshCommand}`)
        this.showNotification('success', 'Copied', sshCommand)
      } catch (err) {
        this.addEvent('error', `Failed to copy: ${err}`)
      }
      document.body.removeChild(textarea)
    },

    hideContextMenu() {
      this.contextMenu.show = false
    },

    // Persistence
    saveShowOffline() {
      localStorage.setItem('networkMonitor_showOffline', this.showOfflineHosts)
    },

    loadShowOffline() {
      const saved = localStorage.getItem('networkMonitor_showOffline')
      if (saved !== null) {
        this.showOfflineHosts = saved === 'true'
      }
    },

    addEvent(type, message) {
      this.events.push({
        id: ++this.eventId,
        type,
        message,
        timestamp: Date.now()
      })

      if (this.events.length > 200) {
        this.events = this.events.slice(-200)
      }
    },

    showNotification(type, title, message) {
      const id = ++this.notificationId
      this.notifications.push({ id, type, title, message })

      setTimeout(() => {
        this.dismissNotification(id)
      }, 5000)
    },

    dismissNotification(id) {
      this.notifications = this.notifications.filter(n => n.id !== id)
    },

    updateLastUpdate() {
      this.lastUpdate = new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    },

    formatTime(timestamp) {
      return new Date(timestamp).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    },

    formatLatency(ms) {
      if (ms === null || ms === undefined) return '0.0'
      return Number(ms).toFixed(1)
    },

    formatUptime(hours) {
      if (!hours) return '—'
      if (hours < 1) return `${Math.round(hours * 60)}m`
      if (hours < 24) return `${hours.toFixed(1)}h`
      return `${(hours / 24).toFixed(1)}d`
    },

    formatBytes(bytes) {
      if (!bytes) return '0 B'
      const units = ['B', 'KB', 'MB', 'GB', 'TB']
      let i = 0
      while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024
        i++
      }
      return `${bytes.toFixed(1)} ${units[i]}`
    },

    getSignalLevel(latencyMs) {
      if (!latencyMs || latencyMs <= 0) return 0
      if (latencyMs < 10) return 4
      if (latencyMs < 50) return 3
      if (latencyMs < 100) return 2
      return 1
    },

    getSparklinePoints(history, height, width = 120) {
      if (!history || history.length < 2) return ''
      const max = Math.max(...history, 1)
      const min = Math.min(...history, 0)
      const range = max - min || 1
      const step = width / (history.length - 1)
      return history.map((v, i) => {
        const x = i * step
        const y = height - ((v - min) / range) * (height - 2) - 1
        return `${x.toFixed(1)},${y.toFixed(1)}`
      }).join(' ')
    },

    getSparklineSegments(history, height, width = 120) {
      if (!history || history.length < 2) return []
      const max = Math.max(...history, 1)
      const min = Math.min(...history, 0)
      const range = max - min || 1
      const step = width / (history.length - 1)

      const segments = []
      for (let i = 0; i < history.length - 1; i++) {
        const x1 = i * step
        const x2 = (i + 1) * step
        const y1 = height - ((history[i] - min) / range) * (height - 2) - 1
        const y2 = height - ((history[i + 1] - min) / range) * (height - 2) - 1
        const avgLatency = (history[i] + history[i + 1]) / 2
        segments.push({
          x1: x1.toFixed(1),
          y1: y1.toFixed(1),
          x2: x2.toFixed(1),
          y2: y2.toFixed(1),
          color: this.getLatencyColor(avgLatency)
        })
      }
      return segments
    },

    getLatencyColor(ms) {
      // Color code latency
      if (ms < 10) return 'var(--accent-green)'       // Excellent
      if (ms < 50) return 'var(--accent-yellow)'      // Good
      if (ms < 100) return 'var(--accent-orange)'     // Fair
      return 'var(--status-offline)'                   // Poor
    },

    getSignalColor(dbm) {
      // Color code WiFi signal strength
      if (dbm >= -50) return 'var(--accent-green)'      // Excellent
      if (dbm >= -60) return 'var(--accent-yellow)'     // Good
      if (dbm >= -70) return 'var(--accent-orange)'     // Fair
      return 'var(--status-offline)'                     // Poor
    },

    getHostMac(host) {
      // Find MAC address for a host using various methods
      if (host.hostname) {
        const hostname = host.hostname.toLowerCase()
        let mac = this.hostnameToMac[hostname]
        if (!mac) {
          const base = this.getBaseHostname(hostname)
          mac = this.hostnameToMac[base]
        }
        if (mac) return mac
      }
      if (host.ip) {
        return this.ipToMac[host.ip]
      }
      return null
    },

    getHostSignal(host) {
      // Get WiFi signal strength for a host
      // Try direct IP lookup first
      if (host.ip && this.ipToSignal[host.ip]) {
        return this.ipToSignal[host.ip]
      }
      // Try MAC-based lookup
      const mac = this.getHostMac(host)
      if (mac && this.macToSignal[mac]) {
        return this.macToSignal[mac]
      }
      return null
    },

    playSound(type) {
      // Create oscillator-based sounds using Web Audio API
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)()

        if (type === 'connect') {
          // Pleasant rising tone for connect
          const oscillator = audioCtx.createOscillator()
          const gainNode = audioCtx.createGain()
          oscillator.connect(gainNode)
          gainNode.connect(audioCtx.destination)
          oscillator.frequency.setValueAtTime(400, audioCtx.currentTime)
          oscillator.frequency.linearRampToValueAtTime(800, audioCtx.currentTime + 0.15)
          gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime)
          gainNode.gain.linearRampToValueAtTime(0, audioCtx.currentTime + 0.2)
          oscillator.start(audioCtx.currentTime)
          oscillator.stop(audioCtx.currentTime + 0.2)
        } else if (type === 'disconnect') {
          // Alarming double-beep error sound for disconnect
          const t = audioCtx.currentTime

          // First beep
          const osc1 = audioCtx.createOscillator()
          const gain1 = audioCtx.createGain()
          osc1.type = 'square'
          osc1.connect(gain1)
          gain1.connect(audioCtx.destination)
          osc1.frequency.setValueAtTime(440, t)
          gain1.gain.setValueAtTime(0.25, t)
          gain1.gain.setValueAtTime(0, t + 0.12)
          osc1.start(t)
          osc1.stop(t + 0.12)

          // Second beep (lower pitch)
          const osc2 = audioCtx.createOscillator()
          const gain2 = audioCtx.createGain()
          osc2.type = 'square'
          osc2.connect(gain2)
          gain2.connect(audioCtx.destination)
          osc2.frequency.setValueAtTime(330, t + 0.15)
          gain2.gain.setValueAtTime(0, t)
          gain2.gain.setValueAtTime(0.25, t + 0.15)
          gain2.gain.setValueAtTime(0, t + 0.3)
          osc2.start(t + 0.15)
          osc2.stop(t + 0.3)
        }
      } catch (e) {
        console.log('Audio not available:', e)
      }
    },

    getBaseHostname(hostname) {
      // Strip common suffixes like .local, .lan, .home, .localdomain
      if (!hostname) return hostname
      return hostname.replace(/\.(local|lan|home|localdomain|internal|intranet)$/i, '')
    },

    getHostConnection(host) {
      // Strategy: Find MAC address, then look up SSID from OpenWRT clients
      // If MAC exists but not in WiFi clients, assume Ethernet

      // 1. Try direct IP match in OpenWRT clients
      if (host.ip && this.ipToConnection[host.ip]) {
        return this.ipToConnection[host.ip]
      }

      // 2. Try to find MAC via hostname in network devices (exact or base match)
      let mac = null
      if (host.hostname) {
        const hostname = host.hostname.toLowerCase()
        mac = this.hostnameToMac[hostname]
        // Try base hostname if exact match not found
        if (!mac) {
          const base = this.getBaseHostname(hostname)
          mac = this.hostnameToMac[base]
        }
      }

      // 3. Try to find MAC via IP in network devices
      if (!mac && host.ip) {
        mac = this.ipToMac[host.ip]
      }

      // 4. Try to find device by hostname match and get its MAC
      if (!mac) {
        const device = this.devices.find(d =>
          (d.hostname && d.hostname.toLowerCase() === host.hostname?.toLowerCase()) ||
          d.ip === host.ip ||
          d.hostname === host.ip
        )
        if (device && device.mac) {
          mac = device.mac.toLowerCase()
        }
      }

      // 5. Look up SSID by MAC in OpenWRT clients (WiFi)
      if (mac && this.macToSsid[mac]) {
        return this.macToSsid[mac]
      }

      // 6. If we have a MAC but it's not in WiFi client list, assume Ethernet
      // (Device is on network via ARP but not connected to any WiFi AP)
      if (mac && this.openwrt && this.openwrt.router_online) {
        // Only show Ethernet if router is online (so we know WiFi client list is current)
        return 'Ethernet'
      }

      return null
    },

    getHostIP(host) {
      // Return host's own IP if available
      if (host.ip) {
        return host.ip
      }

      // Try to find IP from matching network device
      if (host.hostname) {
        const hostname = host.hostname.toLowerCase()
        const base = this.getBaseHostname(hostname)

        // Search for matching device by hostname or base hostname
        const device = this.devices.find(d => {
          if (!d.hostname) return false
          const devHostname = d.hostname.toLowerCase()
          const devBase = this.getBaseHostname(devHostname)
          return devHostname === hostname || devBase === base || devHostname === base || devBase === hostname
        })

        if (device && device.ip) {
          return device.ip
        }
      }

      return null
    },

    getRecentUptime(host) {
      // Calculate uptime from last 60 pings (~2 minutes at 2s interval)
      if (!host.latency_history || host.latency_history.length === 0) {
        return host.uptime_percent || 0
      }
      // latency_history contains successful pings, count vs total recent pings
      const recentPings = Math.min(host.total_pings, 60)
      const recentSuccesses = host.latency_history.length
      if (recentPings === 0) return 0
      return Math.round((recentSuccesses / recentPings) * 100)
    }
  }
}
</script>

<style>
.notification-enter-active,
.notification-leave-active {
  transition: all 0.3s ease;
}

.notification-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.notification-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
