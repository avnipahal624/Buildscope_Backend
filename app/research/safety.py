"""URL safety checks (SSRF protection).

TinyFish does the actual fetching, but we still refuse dangerous URLs so that
the same code stays safe if you ever fetch pages directly from your own server.
"""
import ipaddress
import socket
from urllib.parse import urlparse


def resolve_host(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return [info[4][0].split("%")[0] for info in infos]


def is_safe_url(url: str, resolve=None) -> tuple[bool, str]:
    """Return (ok, reason). Rejects non-http(s), credentials, and private/internal IPs."""
    resolve = resolve or resolve_host
    try:
        p = urlparse(url)
        host = p.hostname
    except ValueError:
        return False, "unparseable url"
    if p.scheme not in ("http", "https"):
        return False, f"scheme '{p.scheme}' not allowed"
    if not host:
        return False, "missing host"
    if p.username or p.password:
        return False, "credentials in url"
    h = host.lower()
    if h == "localhost" or h.endswith((".local", ".internal", ".localhost")):
        return False, "internal hostname"
    try:
        addresses = resolve(host)
    except (socket.gaierror, OSError):
        return False, "host does not resolve"
    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            return False, f"address {addr} is not public"
    return True, "ok"
