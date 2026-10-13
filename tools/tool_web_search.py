# tools/tool_web_search.py
import urllib.request
import urllib.parse
import re
import html as html_lib
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple


def _format_date(date_str: str) -> str:
    """Format string tanggal ISO/DDG menjadi format yang mudah dibaca."""
    if not date_str:
        return "Tidak tercantum (Waktu akses: " + datetime.now().strftime("%d %b %Y, %H:%M WIB") + ")"
    try:
        # Contoh format ISO: 2026-10-12T08:30:00+00:00
        clean_date = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_date)
        if dt.tzinfo is None:
            return dt.strftime("%d %B %Y pukul %H:%M") + " (zona waktu tidak diketahui)"
        jakarta_timezone = timezone(timedelta(hours=7))
        return dt.astimezone(jakarta_timezone).strftime(
            "%d %B %Y pukul %H:%M WIB"
        )
    except Exception:
        return date_str


def _normalize_search_query(query: str) -> str:
    """Mengubah pertanyaan percakapan menjadi kata kunci pencarian berita yang efektif."""
    q = query.strip()
    low = q.lower()
    # Tangani pertanyaan percakapan umum
    if low in ["apa berita hari ini", "ada berita apa hari ini", "berita hari ini", "kabar hari ini", "berita hari ini apa", "apa berita terkini"]:
        return "berita utama terkini hari ini indonesia"
    
    for prefix in ["apa berita tentang ", "ada berita tentang ", "tolong cari berita ", "cari berita ", "berita tentang "]:
        if low.startswith(prefix):
            return "berita " + q[len(prefix):].strip() + " terkini"
    return q


def _search_ddg(query: str) -> List[Dict[str, str]]:
    """Pencarian web & berita menggunakan DuckDuckGo dengan penanganan tanggal publikasi."""
    search_q = _normalize_search_query(query)
    results = []
    is_news = any(k in search_q.lower() for k in ["berita", "news", "terkini", "terbaru", "hari ini", "kejadian", "isu"])

    # 1. Coba duckduckgo_search / ddgs (News Mode jika query berita)
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS(timeout=10) as ddgs:
            if is_news:
                try:
                    raw_news = list(ddgs.news(search_q, region="id-id", max_results=5))
                    if not raw_news:
                        raw_news = list(ddgs.news(search_q, max_results=5))
                    for item in raw_news:
                        results.append({
                            "title": item.get("title", ""),
                            "snippet": item.get("body", "") or item.get("snippet", ""),
                            "url": item.get("url", "") or item.get("href", ""),
                            "source": item.get("source", "") or "Media Berita Online",
                            "date": _format_date(item.get("date", ""))
                        })
                except Exception:
                    pass

            # Fallback ke text search jika news kosong atau bukan pencarian berita
            if not results:
                raw_text = list(ddgs.text(query, max_results=5))
                for item in raw_text:
                    results.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("body", "") or item.get("snippet", ""),
                        "url": item.get("href", "") or item.get("link", ""),
                        "source": item.get("source", "") or "Situs Web",
                        "date": _format_date(item.get("date", ""))
                    })
        if results:
            return results
    except Exception:
        pass

    # 2. Fallback: DuckDuckGo HTML endpoint via urllib
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=6) as response:
            html = response.read().decode('utf-8', errors='ignore')

        parser = _DuckDuckGoHtmlResultsParser()
        parser.feed(html)
        snippets = re.findall(
            r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )

        now_str = datetime.now().strftime("%d %B %Y pukul %H:%M WIB")
        for index, item in enumerate(parser.results[:5]):
            target_url = _unwrap_duckduckgo_url(item["url"])
            snippet = ""
            if index < len(snippets):
                snippet = html_lib.unescape(
                    re.sub(r"<[^>]+>", "", snippets[index])
                ).strip()
            if not target_url.startswith(("http://", "https://")) or not snippet:
                continue
            results.append({
                "title": item["title"],
                "snippet": snippet,
                "url": target_url,
                "source": urllib.parse.urlparse(target_url).netloc or "Situs Web",
                "date": f"Waktu akses {now_str}; tanggal publikasi tidak tersedia",
            })
    except Exception:
        pass

    return results


class _DuckDuckGoHtmlResultsParser(HTMLParser):
    """Extract real result-link destinations instead of citing the search page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: List[Dict[str, str]] = []
        self._current: Dict[str, str] | None = None
        self._anchor_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        if tag != "a":
            if self._current is not None:
                self._anchor_depth += 1
            return
        attributes = dict(attrs)
        classes = attributes.get("class", "").split()
        href = attributes.get("href", "") or ""
        if "result__a" in classes and href:
            self._current = {"url": href, "title": ""}
            self._anchor_depth = 1

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["title"] += data

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a":
            self._anchor_depth -= 1
            if self._anchor_depth <= 0:
                if self._current["title"].strip():
                    self.results.append({
                        "url": self._current["url"],
                        "title": self._current["title"].strip(),
                    })
                self._current = None
                self._anchor_depth = 0
        elif self._anchor_depth > 1:
            self._anchor_depth -= 1


def _unwrap_duckduckgo_url(url: str) -> str:
    """Resolve DuckDuckGo redirect URLs to the actual cited destination."""
    parsed = urllib.parse.urlparse(url)
    if "duckduckgo.com" not in parsed.netloc.casefold():
        return url
    target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
    return urllib.parse.unquote(target) if target else ""


def fetch_article_content(url: str, max_chars: int = 1500, timeout: int = 4) -> str:
    """Membaca isi teks artikel secara mendalam dari URL web."""
    if not url or not url.startswith("http"):
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        # Bersihkan elemen noise (script, style, nav, footer)
        clean = re.sub(r'<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Ekstrak paragraf
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', clean, flags=re.DOTALL | re.IGNORECASE)
        text_blocks = [re.sub(r'<[^>]+>', '', p).strip() for p in paragraphs if len(p.strip()) > 40]

        full_text = " ".join(text_blocks)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text[:max_chars] if full_text else ""
    except Exception:
        return ""


def web_search_structured(query: str, deep_read: bool = True) -> Tuple[str, List[Dict[str, str]]]:
    """
    Mencari informasi web dan mengembalikan:
    1. Teks konteks untuk LLM (termasuk deep read artikel jika tersedia)
    2. Data terstruktur list referensi (title, url, source, date)
    """
    clean_q = query.strip()
    if not clean_q:
        return "❌ Masukkan kata kunci pencarian web.", []

    results = _search_ddg(clean_q)
    if not results:
        now_str = datetime.now().strftime("%d %B %Y pukul %H:%M WIB")
        return f"⚠️ Tidak ditemukan hasil pencarian web untuk: '{clean_q}'. (Waktu cek: {now_str})", []

    # Deep reading untuk 2 sumber berita/artikel teratas
    if deep_read:
        for r in results[:2]:
            url = r.get("url", "")
            if url and "duckduckgo.com" not in url:
                deep = fetch_article_content(url)
                if deep:
                    r["deep_content"] = deep

    formatted = [f"### 🌐 Hasil Pencarian Web Terkini: '{clean_q}'\n"]
    for i, r in enumerate(results, 1):
        content_snippet = r.get('deep_content') or r['snippet']
        formatted.append(
            f"**[{i}] {r['title']}**\n"
            f"- 🏢 **Media / Sumber:** {r['source']}\n"
            f"- 📅 **Tanggal & Waktu Publish:** {r['date']}\n"
            f"- 🔗 **Tautan URL:** {r['url']}\n"
            f"- 📝 **Isi Konten ({'Baca Mendalam' if 'deep_content' in r else 'Cuplikan'}):** {content_snippet}\n"
        )

    return "\n".join(formatted), results


def web_search(query: str) -> str:
    """Wrapper kompatibel lama."""
    text, _ = web_search_structured(query)
    return text
