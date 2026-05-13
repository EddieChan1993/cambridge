"""
Cambridge Dictionary scraper — requests + BeautifulSoup4.
URL: https://dictionary.cambridge.org/zhs/词典/英语-汉语-繁体/{word}
"""

import re
import requests
from bs4 import BeautifulSoup

_DEFAULT_BASE_URL = (
    "https://dictionary.cambridge.org/zhs/"
    "%E8%AF%8D%E5%85%B8/%E8%8B%B1%E8%AF%AD-%E6%B1%89%E8%AF%AD-%E7%B9%81%E4%BD%93"
)

# Fallback chain: simplified Chinese → English-only
_FALLBACK_URLS = [
    "https://dictionary.cambridge.org/zhs/"
    "%E8%AF%8D%E5%85%B8/%E8%8B%B1%E8%AF%AD-%E6%B1%89%E8%AF%AD-%E7%AE%80%E4%BD%93",
    "https://dictionary.cambridge.org/dictionary/english",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


def _text(el, sep=" ") -> str:
    """Extract clean text, preserving word boundaries and fixing punctuation spacing."""
    if not el:
        return ""
    raw = el.get_text(separator=sep)
    text = re.sub(r"\s+", " ", raw).strip()
    # Remove space before punctuation: "word ; next" → "word; next"
    text = re.sub(r"\s+([;:,!?.])", r"\1", text)
    return text


def _fetch(url: str) -> tuple:
    """Fetch URL, return (response, soup) or raise RequestException."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp, BeautifulSoup(resp.text, "lxml")


def scrape_cambridge(word: str, base_url: str = "") -> dict:
    primary = base_url.strip().rstrip("/") if base_url else _DEFAULT_BASE_URL
    slug = word.lower().strip()
    url = f"{primary}/{slug}"
    result = {"word": word.strip(), "url": url, "pronunciations": [], "entries": []}

    # Try primary URL, then fallbacks if the server redirected away from the word.
    # Skip fallback URLs that duplicate the primary to avoid redundant requests.
    fallbacks = [u for u in _FALLBACK_URLS if u.rstrip("/") != primary]
    last_err = None
    resp = soup = None
    for base in [primary] + fallbacks:
        try_url = f"{base}/{slug}"
        try:
            last_err = None
            resp, soup = _fetch(try_url)
        except requests.RequestException as e:
            last_err = e
            continue
        # Cambridge redirects unknown words back to the dictionary root — detect that
        if slug in resp.url.lower():
            result["url"] = try_url
            break
        # This base had no entry; try next fallback
        resp = soup = None

    if last_err and soup is None:
        result["error"] = str(last_err)
        return result
    if soup is None:
        result["error"] = "No dictionary entry found"
        return result

    # ── 音标 ──────────────────────────────────────────────────────────────────
    # 直接找所有 .ipa 元素，再向上找最近的 region 标签
    CAMBRIDGE_ORIGIN = "https://dictionary.cambridge.org"

    def _abs(src: str) -> str:
        if not src:
            return ""
        if src.startswith("http"):
            return src
        if src.startswith("//"):
            return "https:" + src
        return CAMBRIDGE_ORIGIN + src

    seen_pron: set = set()
    for ipa_el in soup.select(".ipa"):
        ipa = ipa_el.get_text(strip=True)
        if not ipa:
            continue

        # Walk up to find the dpron-i container (.uk/.us dpron-i)
        region = ""
        audio_url = ""
        container = ipa_el.parent
        while container and container.name not in ("body", None):
            if "dpron-i" in (container.get("class") or []):
                break
            container = container.parent

        if container:
            region_el = container.find(class_=re.compile(r"\bdreg\b"))
            if region_el:
                region = _text(region_el)
            # Prefer mpeg source inside .daud
            daud = container.find(class_="daud")
            if daud:
                src_el = daud.select_one('audio source[type="audio/mpeg"]')
                if not src_el:
                    src_el = daud.find("source")
                audio_url = _abs(src_el.get("src", "")) if src_el else ""

        key = (region.lower(), ipa)
        if key in seen_pron:
            continue
        seen_pron.add(key)
        result["pronunciations"].append({"label": region, "ipa": ipa, "audio": audio_url})
        if len(result["pronunciations"]) >= 2:   # 最多 UK + US
            break

    # ── 词条 ──────────────────────────────────────────────────────────────────
    blocks = soup.select(".pr.entry-body__el") or soup.select(".entry-body__el")
    if not blocks:
        result["error"] = "No dictionary entry found"
        return result

    for block in blocks:
        # Collect all POS labels from the entry header (e.g. "adjective, adverb")
        pos_header = block.select_one(".pos-header") or block.select_one(".dpos-h")
        if pos_header:
            pos_els = pos_header.select(".pos.dpos") or pos_header.select(".pos")
        else:
            pos_els = block.select(".pos.dpos") or block.select(".pos")
        pos = ", ".join(_text(e) for e in pos_els if _text(e))

        # Source dictionary name from ancestor superentry/dictionary header
        source = ""
        ancestor = block.parent
        while ancestor and ancestor.name not in ("body", None):
            if any(c in (ancestor.get("class") or [])
                   for c in ("superentry", "dictionary")):
                title_el = ancestor.select_one(".c_hh")
                if title_el:
                    raw = title_el.get_text(separator="", strip=True)
                    if "|" in raw:
                        source = raw.split("|", 1)[1].strip()
                break
            ancestor = ancestor.parent

        # Entry-level grammar note e.g. "[ C or U ]"
        if pos_header:
            eg = pos_header.select_one(".gram.dgram") or pos_header.select_one(".gram")
            pos_gram = _text(eg) if eg else ""
        else:
            pos_gram = ""

        definitions = []
        for db in block.select(".ddef_block"):
            def_el = db.select_one(".def.ddef_d") or db.select_one(".def")
            en = _text(def_el).rstrip(":")

            trans_el = db.select_one(".trans.dtrans") or db.select_one(".trans")
            zh = _text(trans_el)

            # Definition-level grammar and usage labels
            gram_el  = db.select_one(".gram.dgram")
            gram     = _text(gram_el) if gram_el else ""

            lab_el   = db.select_one(".lab.dlab")
            label    = _text(lab_el) if lab_el else ""

            # Extra usage note (e.g. "not usually before noun")
            # .gc.dgc is the grammar code element (same info as .gram.dgram) — skip it
            gc_el    = db.select_one(".usage.dusage")
            usage    = _text(gc_el) if gc_el else ""

            examples = []
            for ex_el in db.select(".examp.dexamp")[:3]:
                eg = ex_el.select_one(".eg.deg") or ex_el.select_one(".eg")
                if eg:
                    ex_trans = ex_el.select_one(".trans.dtrans") or ex_el.select_one(".trans")
                    examples.append({"en": _text(eg), "zh": _text(ex_trans) if ex_trans else ""})

            if en or zh:
                definitions.append({
                    "en": en, "zh": zh,
                    "gram": gram, "label": label, "usage": usage,
                    "examples": examples,
                })

        if pos or definitions:
            result["entries"].append({
                "pos": pos, "pos_gram": pos_gram,
                "source": source, "definitions": definitions})

    if not result["entries"]:
        result["error"] = "No definitions found"

    return result
