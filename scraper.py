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


def scrape_cambridge(word: str, base_url: str = "") -> dict:
    base = base_url.strip().rstrip("/") if base_url else _DEFAULT_BASE_URL
    url = f"{base}/{word.lower().strip()}"
    result = {"word": word.strip(), "url": url, "pronunciations": [], "entries": []}

    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            last_err = None
            break
        except requests.RequestException as e:
            last_err = e
    if last_err:
        result["error"] = str(last_err)
        return result

    soup = BeautifulSoup(resp.text, "lxml")

    # ── 音标 ──────────────────────────────────────────────────────────────────
    # 直接找所有 .ipa 元素，再向上找最近的 region 标签
    seen_pron: set = set()
    for ipa_el in soup.select(".ipa"):
        ipa = ipa_el.get_text(strip=True)   # 不加 separator，保留完整音标符号
        if not ipa:
            continue

        region = ""
        parent = ipa_el.parent
        while parent and parent.name not in ("body", None):
            region_el = parent.find(class_=re.compile(r"\bregion\b|\bdreg\b"))
            if region_el:
                region = _text(region_el)
                break
            parent = parent.parent

        key = (region.lower(), ipa)
        if key in seen_pron:
            continue
        seen_pron.add(key)
        result["pronunciations"].append({"label": region, "ipa": ipa})
        if len(result["pronunciations"]) >= 2:   # 最多 UK + US
            break

    # ── 词条 ──────────────────────────────────────────────────────────────────
    blocks = soup.select(".pr.entry-body__el") or soup.select(".entry-body__el")
    if not blocks:
        result["error"] = "No dictionary entry found"
        return result

    for block in blocks:
        pos_el = block.select_one(".pos.dpos") or block.select_one(".pos")
        pos = _text(pos_el)

        # Entry-level grammar note e.g. "[ C or U ]"
        pos_header = block.select_one(".pos-header") or block.select_one(".dpos-h")
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
                "pos": pos, "pos_gram": pos_gram, "definitions": definitions})

    if not result["entries"]:
        result["error"] = "No definitions found"

    return result
