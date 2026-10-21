# core/netguard.py
"""Pengaman jaringan: anti-SSRF untuk pengambilan URL, serta validasi Host/Origin untuk server lokal."""
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterable, Optional, Tuple


class UnsafeURL(ValueError):
    pass


def _is_public(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


def validate_public_url(url: str) -> str:
    """Terima hanya http(s) ke host yang SEMUA alamat IP-nya publik. Tolak localhost, LAN, link-local, dsb."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL("Hanya URL http/https yang diizinkan.")
    host = parsed.hostname
    if not host:
        raise UnsafeURL("URL tidak memiliki host.")
    if parsed.username or parsed.password:
        raise UnsafeURL("URL dengan kredensial tidak diizinkan.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise UnsafeURL(f"Host tidak dapat di-resolve: {error}") from error
    addresses = {info[4][0] for info in infos}
    if not addresses or not all(_is_public(address) for address in addresses):
        raise UnsafeURL("Alamat tujuan bukan alamat internet publik (localhost/jaringan privat ditolak).")
    return url


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            validate_public_url(urllib.parse.urljoin(req.full_url, newurl))
        except UnsafeURL as error:
            raise urllib.error.URLError(f"Redirect ditolak: {error}") from error
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_fetch(
    url: str,
    *,
    timeout: float = 10,
    max_bytes: int = 2_000_000,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[bytes, str]:
    """Ambil URL dengan validasi anti-SSRF di setiap lompatan redirect dan batas ukuran. Return (isi, url_akhir)."""
    validate_public_url(url)
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    request = urllib.request.Request(url, headers=headers or {})
    with opener.open(request, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        return body[:max_bytes], response.geturl()


# ── Server lokal: Host / Origin ──
def host_allowed(host_header: str, allowed: Iterable[str]) -> bool:
    return (host_header or "").strip().lower() in {h.lower() for h in allowed}


def origin_allowed(origin: Optional[str], host_header: str) -> bool:
    """Tanpa Origin (klien non-browser / same-origin GET) diizinkan; selain itu harus sama dengan Host."""
    if not origin:
        return True
    if origin == "null":
        return False
    netloc = origin.split("://", 1)[-1].strip("/").lower()
    return netloc == (host_header or "").strip().lower()
