#!/usr/bin/env python3
"""
bilbo_flash.py — Flash the local on-robot software onto every BILBO robot on the network.

Discovers all reachable robots whose hostname starts with "bilbo" (configurable via
``--prefix``) and rsync-deploys the local ``robots/bilbo/software/`` tree to
``admin@<robot>:/home/admin/robot/software`` on each of them.

Robots are discovered through three (additive) channels:
  1. Known/config hostnames  — BILBO_HOST_NAMES plus every ``bilbo*`` config file stem.
  2. mDNS (zeroconf)         — any ``bilbo*`` host advertising on the local network.
  3. Subnet sweep (--scan)   — TCP/22 sweep of the local subnet(s), reverse-resolved.
Every candidate is confirmed by a TCP connect to the SSH port before it is flashed.

Examples:
    # Discover all bilbo* robots and flash them (asks for confirmation):
    python robots/bilbo/utilities/bilbo_flash.py

    # Preview which robots would be flashed, transfer nothing:
    python robots/bilbo/utilities/bilbo_flash.py --dry-run

    # Also sweep the whole subnet (catches robots not in the config/known list):
    python robots/bilbo/utilities/bilbo_flash.py --scan

    # Flash specific robots and restart their main.py afterwards, no prompt:
    python robots/bilbo/utilities/bilbo_flash.py --hosts bilbo1,bilbo-ie-2 --restart -y

Requirements: ``rsync`` and ``sshpass`` must be installed on the host
(macOS: ``brew install rsync hudochenkov/sshpass/sshpass``).
"""
import argparse
import concurrent.futures
import glob
import os
import shutil
import socket
import subprocess
import sys

# --- make 'core' / 'robots' importable regardless of the current directory ----
SOFTWARE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if SOFTWARE_ROOT not in sys.path:
    sys.path.insert(0, SOFTWARE_ROOT)

from robots.bilbo.robot.bilbo_definitions import (  # noqa: E402
    BILBO_HOST_NAMES, BILBO_USER_NAME, BILBO_PASSWORD, PATH_TO_MAIN,
)
from core.utils.network.network import (  # noqa: E402
    resolveHostname, getHostnameFromIP, getAllPrivateIPs,
)
from core.utils.network.ssh import (  # noqa: E402
    stopPythonViaSSH, executePythonViaSSH,
)

# Repo root is the parent of software/ ; the on-robot software lives next to it.
REPO_ROOT = os.path.abspath(os.path.join(SOFTWARE_ROOT, '..'))
DEFAULT_SOURCE = os.path.join(REPO_ROOT, 'robots', 'bilbo', 'software')
DEFAULT_REMOTE = '/home/admin/robot/software'
DEFAULT_PREFIX = 'bilbo'
SSH_PORT = 22

# Files/dirs that must never be pushed to a robot.
RSYNC_EXCLUDES = [
    '.idea', '.git', '.gitignore', '.DS_Store', '__pycache__',
    '*.pyc', '*.pyo', '*.o', '*.a', '.pytest_cache',
]

# Locations whose *.yaml stems double as robot hostnames (e.g. bilbo-ie-1.yaml).
CONFIG_GLOBS = [
    os.path.join(SOFTWARE_ROOT, 'robots', 'bilbo', 'configs', 'robots', '*.yaml'),
    os.path.join(REPO_ROOT, 'robots', 'bilbo', 'software', 'configs', 'hardware', '*.yaml'),
]

# Colour helpers (degrade gracefully if stdout is not a TTY).
_C = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if _C else s
def green(s):  return _c('32', s)
def red(s):    return _c('31', s)
def yellow(s): return _c('33', s)
def bold(s):   return _c('1', s)


# === Discovery ========================================================================================================
def candidate_hostnames_from_configs(prefix):
    """Hostnames inferred from config-file stems (e.g. 'bilbo-ie-1.yaml' -> 'bilbo-ie-1')."""
    names = set()
    for pattern in CONFIG_GLOBS:
        for path in glob.glob(pattern):
            stem = os.path.splitext(os.path.basename(path))[0]
            if stem == 'template':
                continue
            if stem.lower().startswith(prefix.lower()):
                names.add(stem)
    return names


def discover_mdns(prefix, duration=3.0):
    """Best-effort mDNS browse for ``<prefix>*`` hosts. Returns {hostname: ip|None}."""
    try:
        from zeroconf import Zeroconf, ServiceBrowser
    except Exception:
        return {}

    import threading
    import time

    collected = []
    lock = threading.Lock()

    class _Listener:
        def _record(self, type_, name):
            with lock:
                collected.append((type_, name))
        def add_service(self, zc, type_, name):    self._record(type_, name)
        def update_service(self, zc, type_, name): self._record(type_, name)
        def remove_service(self, zc, type_, name): pass

    service_types = [
        '_workstation._tcp.local.', '_ssh._tcp.local.', '_sftp-ssh._tcp.local.',
        '_device-info._tcp.local.', '_http._tcp.local.',
    ]

    found = {}
    zc = Zeroconf()
    try:
        listener = _Listener()
        for st in service_types:
            ServiceBrowser(zc, st, listener)
        time.sleep(duration)
        # Resolve outside the browser callback to avoid blocking zeroconf's thread.
        for type_, name in dict.fromkeys(collected):
            try:
                info = zc.get_service_info(type_, name, timeout=1500)
            except Exception:
                info = None
            if not info:
                continue
            server = (getattr(info, 'server', '') or '').rstrip('.')
            host = server.split('.')[0] if server else ''
            if not host or not host.lower().startswith(prefix.lower()):
                continue
            ip = None
            try:
                addrs = info.parsed_addresses()
                ip = addrs[0] if addrs else None
            except Exception:
                pass
            found[host] = ip
    finally:
        zc.close()
    return found


def tcp_open(host, port=SSH_PORT, timeout=0.5):
    """True if a TCP connection to host:port succeeds within timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def confirm_reachable(hostnames, timeout, jobs=64):
    """Return {hostname: ip} for every hostname whose SSH port is reachable."""
    reachable = {}
    if not hostnames:
        return reachable
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        futures = {ex.submit(tcp_open, h, SSH_PORT, timeout): h for h in hostnames}
        for fut in concurrent.futures.as_completed(futures):
            host = futures[fut]
            if fut.result():
                reachable[host] = resolveHostname(host)
    return reachable


def discover_subnet(prefix, timeout, jobs=128):
    """TCP/22 sweep of every local subnet; keep hosts that reverse-resolve to ``<prefix>*``."""
    groups = getAllPrivateIPs()
    own_ips, bases = set(), set()
    for key in ('local_ips', 'enterprise_ips', 'usb_ips'):
        for ip in groups.get(key, []):
            own_ips.add(ip)
            bases.add(ip.rsplit('.', 1)[0])
    targets = [f"{base}.{host}" for base in bases for host in range(1, 255)
               if f"{base}.{host}" not in own_ips]
    if not targets:
        return {}

    found = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        futures = {ex.submit(tcp_open, ip, SSH_PORT, timeout): ip for ip in targets}
        for fut in concurrent.futures.as_completed(futures):
            ip = futures[fut]
            if not fut.result():
                continue
            name = getHostnameFromIP(ip)
            if not name:
                continue
            host = name.split('.')[0]
            if host.lower().startswith(prefix.lower()):
                found[host] = ip
    return found


def discover_robots(prefix, explicit_hosts, timeout, use_mdns, use_scan):
    """Discover all reachable ``<prefix>*`` robots. Returns a sorted [(hostname, ip)] list."""
    robots = {}  # hostname -> ip

    if explicit_hosts:
        candidates = {h for h in explicit_hosts if h.lower().startswith(prefix.lower())}
        skipped = [h for h in explicit_hosts if not h.lower().startswith(prefix.lower())]
        for h in skipped:
            print(yellow(f"  skipping '{h}': does not start with '{prefix}'"))
    else:
        candidates = set(n for n in BILBO_HOST_NAMES if n.lower().startswith(prefix.lower()))
        candidates |= candidate_hostnames_from_configs(prefix)
        if use_mdns:
            print("  browsing mDNS ...")
            candidates |= set(discover_mdns(prefix).keys())

    print(f"  probing {len(candidates)} candidate hostname(s) on port {SSH_PORT} ...")
    robots.update(confirm_reachable(candidates, timeout))

    if use_scan and not explicit_hosts:
        print("  sweeping local subnet(s) ...")
        robots.update(discover_subnet(prefix, timeout))

    # Deduplicate by resolved IP (a robot may answer to several names).
    deduped, seen_ips = {}, set()
    for host in sorted(robots):
        ip = robots[host]
        if ip and ip in seen_ips:
            continue
        if ip:
            seen_ips.add(ip)
        deduped[host] = ip
    return sorted(deduped.items())


# === Deployment =======================================================================================================
def ssh_options(connect_timeout=10):
    return (
        f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
        f"-o ConnectTimeout={connect_timeout} -o LogLevel=ERROR"
    )


def flash_robot(host, source, remote, user, password, restart):
    """Flash one robot. Returns a result dict."""
    result = {'host': host, 'ok': False, 'restarted': None, 'error': ''}

    if restart:
        stopPythonViaSSH(host, user, password, PATH_TO_MAIN)

    cmd = ['sshpass', '-p', password, 'rsync', '-az', '--delete', '--delete-excluded']
    for pattern in RSYNC_EXCLUDES:
        cmd += ['--exclude', pattern]
    cmd += ['-e', ssh_options(), f"{source}/", f"{user}@{host}:{remote}"]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    result['ok'] = proc.returncode == 0
    if not result['ok']:
        result['error'] = (proc.stderr or proc.stdout or '').strip().splitlines()
        result['error'] = result['error'][-1] if result['error'] else f"rsync exit {proc.returncode}"
        return result

    if restart:
        try:
            result['restarted'] = executePythonViaSSH(host, user, password, PATH_TO_MAIN, use_pyenv=True)
        except Exception as e:  # noqa: BLE001
            result['restarted'] = False
            result['error'] = f"started rsync ok but restart failed: {e}"
    return result


def flash_all(robots, source, remote, user, password, restart, jobs):
    """Flash every robot concurrently; print per-robot results; return (n_ok, n_fail)."""
    n_ok = 0
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        futures = {
            ex.submit(flash_robot, host, source, remote, user, password, restart): host
            for host, _ip in robots
        }
        for fut in concurrent.futures.as_completed(futures):
            host = futures[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                res = {'host': host, 'ok': False, 'restarted': None, 'error': str(e)}
            results.append(res)
            if res['ok']:
                n_ok += 1
                suffix = ''
                if restart:
                    suffix = (green('  (restarted)') if res['restarted']
                              else red('  (RESTART FAILED)'))
                print(f"  {green('✓')} {host} flashed{suffix}")
            else:
                print(f"  {red('✗')} {host}: {res['error']}")
    return n_ok, len(results) - n_ok


# === CLI ==============================================================================================================
def parse_args():
    p = argparse.ArgumentParser(
        description="Flash the local on-robot software onto all bilbo* robots on the network.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('--source', default=DEFAULT_SOURCE,
                   help=f"Local software directory to flash (default: {DEFAULT_SOURCE})")
    p.add_argument('--remote', default=DEFAULT_REMOTE,
                   help=f"Remote target directory on each robot (default: {DEFAULT_REMOTE})")
    p.add_argument('--prefix', default=DEFAULT_PREFIX,
                   help=f"Only flash hosts whose name starts with this (default: '{DEFAULT_PREFIX}')")
    p.add_argument('--hosts', default='',
                   help="Comma-separated explicit hostnames; skips discovery.")
    p.add_argument('--scan', action='store_true',
                   help="Also sweep the whole local subnet (finds robots not in the config/known list).")
    p.add_argument('--no-mdns', action='store_true', help="Disable mDNS discovery.")
    p.add_argument('--restart', action='store_true',
                   help="Stop the robot's main.py before flashing and start it again afterwards.")
    p.add_argument('--dry-run', action='store_true', help="Discover and list robots, but transfer nothing.")
    p.add_argument('-y', '--yes', action='store_true', help="Do not ask for confirmation.")
    p.add_argument('--jobs', type=int, default=4, help="How many robots to flash in parallel (default: 4).")
    p.add_argument('--timeout', type=float, default=0.6, help="Per-host probe timeout in seconds (default: 0.6).")
    p.add_argument('--user', default=BILBO_USER_NAME, help=f"SSH username (default: {BILBO_USER_NAME}).")
    p.add_argument('--password', default=BILBO_PASSWORD, help="SSH password.")
    return p.parse_args()


def main():
    args = parse_args()

    source = os.path.abspath(os.path.expanduser(args.source))
    if not os.path.isdir(source):
        print(red(f"Source directory not found: {source}"))
        return 1
    if not os.path.isfile(os.path.join(source, 'main.py')):
        print(red(f"'{source}' does not look like the on-robot software (no main.py)."))
        return 1
    if not os.path.isfile(os.path.join(source, 'VERSION')):
        print(yellow(f"Warning: no VERSION file in {source} — flashing anyway."))

    # Tool availability (not needed for a dry run).
    if not args.dry_run:
        missing = [t for t in ('rsync', 'sshpass') if shutil.which(t) is None]
        if missing:
            print(red(f"Missing required tool(s): {', '.join(missing)}"))
            print("Install on macOS with: brew install rsync hudochenkov/sshpass/sshpass")
            return 1

    print(bold(f"Discovering '{args.prefix}*' robots ..."))
    explicit = [h.strip() for h in args.hosts.split(',') if h.strip()]
    robots = discover_robots(
        prefix=args.prefix,
        explicit_hosts=explicit,
        timeout=args.timeout,
        use_mdns=not args.no_mdns,
        use_scan=args.scan,
    )

    if not robots:
        print(red("No reachable robots found."))
        if not args.scan and not explicit:
            print("Tip: try --scan to sweep the whole subnet, or pass --hosts explicitly.")
        return 1

    print(bold(f"\nFound {len(robots)} robot(s):"))
    for host, ip in robots:
        print(f"  • {host}" + (f"  ({ip})" if ip else ""))
    print(f"\n  source : {source}")
    print(f"  target : {args.user}@<robot>:{args.remote}")
    print(f"  restart: {'yes' if args.restart else 'no'}")

    if args.dry_run:
        print(yellow("\nDry run — nothing was transferred."))
        return 0

    if not args.yes:
        answer = input(bold(f"\nFlash these {len(robots)} robot(s)? [y/N] ")).strip().lower()
        if answer not in ('y', 'yes'):
            print("Aborted.")
            return 1

    print(bold("\nFlashing ..."))
    n_ok, n_fail = flash_all(
        robots, source, args.remote, args.user, args.password, args.restart, args.jobs,
    )

    print(bold(f"\nDone: {green(str(n_ok) + ' succeeded')}"
               + (f", {red(str(n_fail) + ' failed')}" if n_fail else "")) + ".")
    return 0 if n_fail == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
