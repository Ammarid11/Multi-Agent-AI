# tools/tool_web_search.py
import urllib.request
import urllib.parse
import re
import json
import html as html_lib
from html.parser import HTMLParser
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple

from core.netguard import safe_fetch

def _format_date(date_str: str) -> str:
    """Format string tanggal ISO/tanggal biasa menjadi format yang mudah dibaca."""
    if not date_str:
        return "Tanggal publikasi/pembaruan tidak tercantum"
    
    # Kamus bulan Bahasa Indonesia agar tidak bergantung pada locale sistem (mengatasi isu %B)
    bulan_indo = {
        1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
        5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
        9: "September", 10: "Oktober", 11: "November", 12: "Desember"
    }

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        try:
            dt_parsed = datetime.strptime(date_str, "%Y-%m-%d")
            return f"{dt_parsed.day} {bulan_indo[dt_parsed.month]} {dt_parsed.year}"
        except ValueError:
            return date_str
            
    try:
        # Contoh format ISO: 2026-10-12T08:30:00+00:00
        clean_date = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_date)
        
        # Format tanggal & bulan menggunakan mapping Bahasa Indonesia
        tgl_str = f"{dt.day} {bulan_indo[dt.month]} {dt.year}"
        
        if dt.tzinfo is None:
            return f"{tgl_str} pukul {dt.strftime('%H:%M')} (zona waktu tidak diketahui)"
            
        jakarta_timezone = timezone(timedelta(hours=7))
        dt_jakarta = dt.astimezone(jakarta_timezone)
        
        return f"{tgl_str} pukul {dt_jakarta.strftime('%H:%M')} WIB"
        
    except Exception:
        return date_str


class _ArticleMetadataParser(HTMLParser):
    """Collect publication metadata from article HTML."""
    
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_values: Dict[str, str] = {}
        self.json_ld_blocks: List[str] = []
        self._in_json_ld = False
        self._json_ld_content: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): (value if value is not None else "") for key, value in attrs}
        tag_lower = tag.casefold()
        
        if tag_lower == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
                or attributes.get("itemprop")
                or ""
            ).casefold()
            content = attributes.get("content", "").strip()
            if key and content:
                self.meta_values[key] = content
                
        elif (
            tag_lower == "script"
            and attributes.get("type", "").split(";", 1)[0].strip().casefold() == "application/ld+json"
        ):
            self._in_json_ld = True
            self._json_ld_content = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_content.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._in_json_ld:
            # Membersihkan spasi/newline berlebih di awal dan akhir blok JSON
            json_text = "".join(self._json_ld_content).strip()
            if json_text:
                self.json_ld_blocks.append(json_text)
            self._in_json_ld = False
            self._json_ld_content = []


def _json_ld_article_dates(value: object) -> Tuple[str, str]:
    published = ""
    modified = ""
    if isinstance(value, dict):
        for key, date in value.items():
            normalized_key = key.casefold()
            if isinstance(date, str):
                if normalized_key in {"datepublished", "datecreated", "uploaddate"} and not published:
                    published = date
                elif normalized_key == "datemodified" and not modified:
                    modified = date
            elif isinstance(date, (dict, list)):
                nested_published, nested_modified = _json_ld_article_dates(date)
                published = published or nested_published
                modified = modified or nested_modified
    elif isinstance(value, list):
        for item in value:
            nested_published, nested_modified = _json_ld_article_dates(item)
            published = published or nested_published
            modified = modified or nested_modified
    return published, modified


def _extract_article_dates(html: str) -> Tuple[str, str]:
    parser = _ArticleMetadataParser()
    parser.feed(html)

    published = next(
        (
            parser.meta_values[key]
            for key in (
                "article:published_time",
                "og:published_time",
                "datepublished",
                "publishdate",
                "pubdate",
                "parsely-pub-date",
            )
            if key in parser.meta_values
        ),
        "",
    )
    modified = next(
        (
            parser.meta_values[key]
            for key in (
                "article:modified_time",
                "og:updated_time",
                "datemodified",
                "last-modified",
            )
            if key in parser.meta_values
        ),
        "",
    )
    for block in parser.json_ld_blocks:
        try:
            json_published, json_modified = _json_ld_article_dates(json.loads(block))
        except (json.JSONDecodeError, TypeError):
            continue
        published = published or json_published
        modified = modified or json_modified
    return published, modified


def _normalize_search_query(query: str) -> str:
    """Mengubah pertanyaan percakapan menjadi kata kunci pencarian berita yang efektif."""
    if not query:
        return ""
        
    q = query.strip()
    low = q.lower()
    
    # Tanggapi pertanyaan percakapan umum
    if low in ["apa berita hari ini", "ada berita apa hari ini", "berita hari ini", "kabar hari ini", "berita hari ini apa", "apa berita terkini"]:
        return "berita utama terkini hari ini indonesia"

    for prefix in ["apa berita tentang ", "ada berita tentang ", "tolong cari berita ", "cari berita ", "berita tentang "]:
        if low.startswith(prefix):
            # Mengambil sisa teks dan membersihkan tanda baca di akhir kalimat
            cleaned_query = q[len(prefix):].rstrip("?.,!").strip()
            return f"berita {cleaned_query} terkini"
            
    # Bersihkan juga tanda baca di akhir jika tidak menggunakan prefix khusus
    return q.rstrip("?.,!").strip()


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

            # PERBAIKAN: Menggunakan search_q (yang sudah dinormalisasi) alih-alih query mentah
            if not results:
                raw_text = list(ddgs.text(search_q, max_results=5))
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

    # 2. Fallback: DuckDuckGo HTML endpoint via urllib (menggunakan search_q agar konsisten)
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(search_q)}"
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
                "date": "",
                "date_label": (
                    "Tanggal publikasi/pembaruan tidak tersedia; "
                    f"halaman pencarian diakses {now_str}"
                ),
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
            
        # Perbaikan aman untuk atribut yang bernilai None
        attributes = {key.casefold(): (value if value is not None else "") for key, value in attrs}
        classes = attributes.get("class", "").split()
        href = attributes.get("href", "") or ""
        
        if "result_a" in classes and href:
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
                title_clean = self._current["title"].strip()
                if title_clean:
                    self.results.append({
                        "url": self._current["url"],
                        "title": title_clean,
                    })
                self._current = None
                self._anchor_depth = 0
        elif self._anchor_depth > 1:
            self._anchor_depth -= 1


def _unwrap_duckduckgo_url(url: str) -> str:
    """Resolve DuckDuckGo redirect URLs to the actual cited destination."""
    if not url or not isinstance(url, str):
        return ""
        
    parsed = urllib.parse.urlparse(url)
    if "duckduckgo.com" not in parsed.netloc.casefold():
        return url
        
    target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])
    if not target or not target[0]:
        return ""
        
    return urllib.parse.unquote(target[0])


def _fetch_article_page(
    url: str,
    max_chars: int,
    timeout: int,
) -> Tuple[str, str, str]:
    """Fetch article text and publication metadata from one HTTP response."""
    if not url or not url.startswith("http"):
        return "", "", ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        body, _ = safe_fetch(url, timeout=timeout, max_bytes=1_500_000, headers=headers)
        html = body.decode('utf-8', errors='ignore')
        published_date, modified_date = _extract_article_dates(html)

        # PERBAIKAN: Mengubah </1> menjadi </\1> agar backreference regex berfungsi normal
        clean = re.sub(r'<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Ekstrak paragraf
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', clean, flags=re.DOTALL | re.IGNORECASE)
        text_blocks = [re.sub(r'<[^>]+>', '', p).strip() for p in paragraphs if len(p.strip()) > 40]

        full_text = " ".join(text_blocks)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text[:max_chars] if full_text else "", published_date, modified_date
    except Exception:
        return "", "", ""


def fetch_article_content(url: str, max_chars: int = 1500, timeout: int = 4) -> str:
    """Membaca isi teks artikel secara mendalam dari URL web."""
    content, _, _ = _fetch_article_page(url, max_chars, timeout)
    return content


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
        for r in results[:5]:
            url = r.get("url", "")
            if url and "duckduckgo.com" not in url:
                deep, published_date, modified_date = _fetch_article_page(url, 1500, 4)
                if deep:
                    r["deep_content"] = deep
                
                # TAMBAHAN FILTER: Abaikan jika berupa placeholder (misal: [publishdate])
                if published_date and published_date.startswith("["):
                    published_date = ""
                if modified_date and modified_date.startswith("["):
                    modified_date = ""

                if published_date:
                    r["published_date"] = published_date
                if modified_date:
                    r["modified_date"] = modified_date
                if published_date and modified_date:
                    r["verified_date"] = modified_date
                    r["date_label"] = (
                        "Metadata halaman — dipublikasikan: "
                        f"{_format_date(published_date)}; diperbarui: "
                        f"{_format_date(modified_date)}"
                    )
                elif published_date:
                    r["verified_date"] = published_date
                    r["date_label"] = (
                        "Tanggal publikasi di metadata halaman: "
                        f"{_format_date(published_date)}"
                    )
                elif modified_date:
                    r["verified_date"] = modified_date
                    r["date_label"] = (
                        "Tanggal pembaruan di metadata halaman: "
                        f"{_format_date(modified_date)}"
                    )
                elif r.get("date"):
                    r["date_label"] = (
                        "Tanggal dari indeks pencarian (belum diverifikasi di halaman): "
                        f"{_format_date(r['date'])}"
                    )
                else:
                    r["date_label"] = "Tanggal publikasi/pembaruan tidak terverifikasi"

    formatted = [f"### 🌐 Hasil Pencarian Web Terkini: '{clean_q}'\n"]
    for i, r in enumerate(results, 1):
        content_snippet = r.get('deep_content') or r['snippet']
        date_label = r.get("date_label") or (
            f"Tanggal dari indeks pencarian (belum diverifikasi di halaman): {_format_date(r['date'])}"
            if r.get("date")
            else "Tanggal publikasi/pembaruan tidak terverifikasi"
        )
        formatted.append(
            f"**[{i}] {r['title']}**\n"
            f"- 🏢 **Media / Sumber:** {r['source']}\n"
            f"- 📅 **Tanggal sumber:** {date_label}\n"
            f"- 🔗 **Tautan URL:** {r['url']}\n"
            f"- 📝 **Isi Konten ({'Baca Mendalam' if 'deep_content' in r else 'Cuplikan'}):** {content_snippet}\n"
        )

    return "\n".join(formatted), results


def web_search(query: str) -> str:
    """Wrapper kompatibel lama."""
    text, _ = web_search_structured(query)
    return text
