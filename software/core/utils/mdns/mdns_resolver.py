import socket

from aiohttp import DefaultResolver
from zeroconf._services.info import AsyncServiceInfo
from zeroconf.asyncio import AsyncZeroconf


class MDNSResolver(DefaultResolver):
    def __init__(self):
        super().__init__()
        # this will spin up its own multicast listener
        self.async_zc = AsyncZeroconf()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        # logger.debug(f"→ resolve() called: host={host!r}")
        # intercept only .local names
        if host.endswith(".local"):
            svc_type = "_http._tcp.local."
            # strip the final “.local” so “app1.local” → “app1._http._tcp.local.”
            name = host.rsplit(".", 1)[0]
            svc_name = f"{name}.{svc_type}"
            # logger.debug(f"   trying AsyncServiceInfo.async_request for {svc_name!r}")

            info = AsyncServiceInfo(svc_type, svc_name)
            try:
                # Pass the underlying Zeroconf instance (has .started)
                found = await info.async_request(self.async_zc.zeroconf, timeout=3.0)
            except Exception as e:
                logger.error(f"Some error: {e}")
                found = False

            if found:
                # one or more IPv4 addresses
                addresses = [socket.inet_ntoa(a) for a in info.addresses]
                # logger.debug(f"mDNS → {addresses}:{info.port}")
                return [
                    {
                        "hostname": host,
                        "host": addr,
                        "port": info.port,
                        "family": family,
                        "proto": 0,
                        "flags": 0,
                    }
                    for addr in addresses
                ]
            else:
                ...
                # logger.debug("mDNS lookup failed, falling back to DefaultResolver")

        # fallback to normal DNS/hosts
        result = await super().resolve(host, port, family)
        # logger.debug(f"DefaultResolver → {result}")
        return result