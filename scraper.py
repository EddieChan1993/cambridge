"""
Cambridge Dictionary scraper — requests + BeautifulSoup4.
URL: https://dictionary.cambridge.org/zhs/词典/英语-汉语-繁体/{word}
"""

import re
import requests
from bs4 import BeautifulSoup

_DEFAULT_BASE_URL = (
    "https://dictionary.cambridge.org/zhs/"
    "%E8%AF%8D%E5%85%B8/%E8%8B%B1%E8%AF%AD-%E6%B1%89%E8%AF%AD-%E7%AE%80%E4%BD%93"
)

# Fallback: English-only as last resort. Never put another Chinese variant here —
# it would silently override the user's configured URL when the primary redirects.
_FALLBACK_URLS = [
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


def _def_trans(db) -> str:
    """Return the definition-level Chinese translation, skipping example translations."""
    for t in db.select(".trans.dtrans, .trans"):
        if not t.find_parent(class_="examp"):
            raw = t.get_text(separator=" ")
            return re.sub(r"\s+", " ", raw).strip()
    return ""


def _parse_xrefs(db) -> dict:
    """Extract synonym/antonym lists from a ddef_block. Returns {"synonyms": [...], "antonyms": [...]}."""
    synonyms, antonyms = [], []
    for xref in db.select(".xref"):
        cls = set(xref.get("class") or [])
        if cls & {"synonym", "synonyms"}:
            target = synonyms
        elif "opposite" in cls:
            target = antonyms
        else:
            continue
        for item in xref.select(".item"):
            # Word can be in .x-h (single word) or .x-p (phrase like "the poor")
            word_el = item.select_one(".x-h.dx-h") or item.select_one(".x-p.dx-p")
            if not word_el:
                continue
            word = re.sub(r"\s+", " ", word_el.get_text(separator=" ")).strip()
            guide_el = item.select_one(".x-num.dx-num")
            guide = guide_el.get_text(strip=True).strip("()") if guide_el else ""
            label_el = item.select_one(".x-lab.dx-lab")
            label = label_el.get_text(strip=True) if label_el else ""
            if word:
                target.append({"word": word, "guide": guide, "label": label})
    return {"synonyms": synonyms, "antonyms": antonyms}


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
    # Cambridge URLs use hyphens for multi-word phrases (e.g. "feel free" → "feel-free")
    slug = word.lower().strip().replace(" ", "-")
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

    # ── 页面实际 headword（修正用户查询与页面词条不一致的情况）─────────────────
    # Cambridge may redirect the query (e.g. "feel like") to a page whose
    # headword is different from the search term. Always use the page's
    # actual headword so the app doesn't show a misleading word heading.
    page_hw_el = (soup.select_one(".headword.dhw")
                  or soup.select_one(".hw.dhw")
                  or soup.select_one(".di-title .hw"))
    if page_hw_el:
        hw_raw = _text(page_hw_el)
        if hw_raw:
            result["word"] = hw_raw

    # ── 词条 ──────────────────────────────────────────────────────────────────
    # Collect entry-body__el and top-level phrase-di-blocks in DOM order.
    # phrase-di-blocks sit directly in di-body alongside .entry containers,
    # so we walk the superentry structure to preserve the page's interleaving.
    blocks = []
    for di_body in soup.select(".pr.di.superentry .di-body, .di.superentry .di-body"):
        for child in di_body.children:
            if not hasattr(child, "get"):
                continue
            child_cls = set(child.get("class") or [])
            if child_cls & {"phrase-di-block", "dphrase-di-block"}:
                blocks.append(child)
            elif "entry" in child_cls:
                for el in (child.select(".pr.entry-body__el") or
                           child.select(".entry-body__el")):
                    blocks.append(el)
    if not blocks:
        # Fallback for pages without superentry wrapper
        blocks = soup.select(".pr.entry-body__el") or soup.select(".entry-body__el")

    for block in blocks:
        block_cls = set(block.get("class") or [])
        is_phrase_di = bool(block_cls & {"phrase-di-block", "dphrase-di-block"})

        if is_phrase_di:
            # POS comes from .di-info, not .pos-header
            di_info = block.select_one(".di-info")
            pos_els = di_info.select(".pos.dpos") if di_info else []
            if not pos_els:
                pos_els = block.select(".di-info .pos")
            pos = ", ".join(_text(e) for e in pos_els if _text(e))
            pos_gram = ""
            source = ""
        else:
            # Collect all POS labels from the entry header (e.g. "adjective, adverb")
            pos_header = block.select_one(".pos-header") or block.select_one(".dpos-h")
            if pos_header:
                pos_els = pos_header.select(".pos.dpos") or pos_header.select(".pos")
            else:
                pos_els = block.select(".pos.dpos") or block.select(".pos")
            pos = ", ".join(_text(e) for e in pos_els if _text(e))
            # Entry-level grammar note e.g. "[ C or U ]"
            if pos_header:
                eg = pos_header.select_one(".gram.dgram") or pos_header.select_one(".gram")
                pos_gram = _text(eg) if eg else ""
            else:
                pos_gram = ""

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

        def _parse_phrase_block(pb):
            title_el    = pb.select_one(".phrase-title")
            phrase_txt  = _text(title_el) if title_el else ""
            if not phrase_txt:
                return None
            gram_el     = pb.select_one(".phrase-head .gram")
            phrase_gram = _text(gram_el) if gram_el else ""
            cefr_el     = pb.select_one(".epp-xref")
            cefr        = _text(cefr_el) if cefr_el else ""
            var_els = pb.select(".phrase-head .var.dvar")
            variant = "; ".join(_text(v) for v in var_els) if var_els else ""
            ph_defs = []
            for db in pb.select(".ddef_block"):
                def_el = db.select_one(".def.ddef_d") or db.select_one(".def")
                en = _text(def_el).rstrip(":")
                zh = _def_trans(db)
                gram2   = _text(db.select_one(".gram.dgram"))
                label2  = _text(db.select_one(".lab.dlab"))
                usage2  = _text(db.select_one(".usage.dusage"))
                examples = []
                for ex_el in db.select(".examp.dexamp")[:3]:
                    eg = ex_el.select_one(".eg.deg") or ex_el.select_one(".eg")
                    en_text = _text(eg) if eg else ""
                    if not en_text:
                        continue
                    ex_trans = ex_el.select_one(".trans.dtrans") or ex_el.select_one(".trans")
                    examples.append({"en": en_text, "zh": _text(ex_trans) if ex_trans else ""})
                if en or zh:
                    xrefs = _parse_xrefs(db)
                    ph_defs.append({"en": en, "zh": zh, "gram": gram2,
                                    "label": label2, "usage": usage2,
                                    "examples": examples,
                                    "synonyms": xrefs["synonyms"],
                                    "antonyms": xrefs["antonyms"]})
            if not ph_defs:
                return None
            return {"phrase": phrase_txt, "gram": phrase_gram,
                    "cefr": cefr, "variant": variant, "definitions": ph_defs}

        # Iterate dsense blocks so phrases are associated with their parent sense
        definitions = []
        # For phrase-di-block entries, defs live directly in .phrase-di-body
        if is_phrase_di:
            search_root = block.select_one(".phrase-di-body") or block
            for db in search_root.select(".ddef_block"):
                def_el = db.select_one(".def.ddef_d") or db.select_one(".def")
                en = _text(def_el).rstrip(":")
                zh = _def_trans(db)
                gram_el = db.select_one(".gram.dgram")
                gram    = _text(gram_el) if gram_el else ""
                lab_el  = db.select_one(".lab.dlab")
                label   = _text(lab_el) if lab_el else ""
                gc_el   = db.select_one(".usage.dusage")
                usage   = _text(gc_el) if gc_el else ""
                examples = []
                for ex_el in db.select(".examp.dexamp")[:3]:
                    eg = ex_el.select_one(".eg.deg") or ex_el.select_one(".eg")
                    en_text = _text(eg) if eg else ""
                    if not en_text:
                        continue
                    ex_trans = ex_el.select_one(".trans.dtrans") or ex_el.select_one(".trans")
                    examples.append({"en": en_text, "zh": _text(ex_trans) if ex_trans else ""})
                if en or zh:
                    xrefs = _parse_xrefs(db)
                    definitions.append({
                        "en": en, "zh": zh,
                        "gram": gram, "label": label, "usage": usage,
                        "guideword": "", "examples": examples, "phrases": [],
                        "synonyms": xrefs["synonyms"], "antonyms": xrefs["antonyms"],
                    })
        dsense_blocks = ([] if is_phrase_di else block.select(".dsense"))
        if dsense_blocks:
            for ds in dsense_blocks:
                gw_el     = ds.select_one(".guideword.dsense_gw") or ds.select_one(".guideword")
                guideword = _text(gw_el) if gw_el else ""
                # Strip surrounding parens: "( POSITION )" → "POSITION"
                guideword = re.sub(r"^\(\s*|\s*\)$", "", guideword).strip()

                # Walk sense-body children in DOM order so each phrase-block
                # is attached to the definition that immediately precedes it.
                sense_body = ds.select_one(".sense-body") or ds
                last_def = None
                for child in sense_body.children:
                    if not hasattr(child, "get"):
                        continue
                    child_cls = set(child.get("class") or [])

                    if "ddef_block" in child_cls or "def-block" in child_cls:
                        db = child
                        if db.find_parent(class_="phrase-block"):
                            continue
                        def_el = db.select_one(".def.ddef_d") or db.select_one(".def")
                        en = _text(def_el).rstrip(":")
                        zh = _def_trans(db)
                        gram_el = db.select_one(".gram.dgram")
                        gram    = _text(gram_el) if gram_el else ""
                        lab_el  = db.select_one(".lab.dlab")
                        label   = _text(lab_el) if lab_el else ""
                        gc_el   = db.select_one(".usage.dusage")
                        usage   = _text(gc_el) if gc_el else ""
                        examples = []
                        for ex_el in db.select(".examp.dexamp")[:3]:
                            if ex_el.find_parent(class_="phrase-block"):
                                continue
                            eg = ex_el.select_one(".eg.deg") or ex_el.select_one(".eg")
                            en_text = _text(eg) if eg else ""
                            if not en_text:
                                continue
                            ex_trans = ex_el.select_one(".trans.dtrans") or ex_el.select_one(".trans")
                            examples.append({"en": en_text,
                                             "zh": _text(ex_trans) if ex_trans else ""})
                        if en or zh:
                            xrefs = _parse_xrefs(db)
                            last_def = {
                                "en": en, "zh": zh,
                                "gram": gram, "label": label, "usage": usage,
                                "guideword": guideword,
                                "examples": examples,
                                "phrases": [],
                                "synonyms": xrefs["synonyms"],
                                "antonyms": xrefs["antonyms"],
                            }
                            definitions.append(last_def)

                    elif "phrase-block" in child_cls or "dphrase-block" in child_cls:
                        p = _parse_phrase_block(child)
                        if p:
                            if last_def is not None:
                                last_def["phrases"].append(p)
                            else:
                                # No preceding def — store as a standalone phrase def
                                standalone = {
                                    "en": "", "zh": "",
                                    "gram": "", "label": "", "usage": "",
                                    "guideword": guideword,
                                    "examples": [],
                                    "phrases": [p],
                                }
                                definitions.append(standalone)
                                last_def = standalone
        elif not is_phrase_di:
            # Fallback: no dsense grouping — collect ddef_blocks directly
            for db in block.select(".ddef_block"):
                if db.find_parent(class_="phrase-block"):
                    continue
                def_el = db.select_one(".def.ddef_d") or db.select_one(".def")
                en = _text(def_el).rstrip(":")
                trans_el = db.select_one(".trans.dtrans") or db.select_one(".trans")
                zh = _text(trans_el)
                gram_el = db.select_one(".gram.dgram")
                gram    = _text(gram_el) if gram_el else ""
                lab_el  = db.select_one(".lab.dlab")
                label   = _text(lab_el) if lab_el else ""
                gc_el   = db.select_one(".usage.dusage")
                usage   = _text(gc_el) if gc_el else ""
                examples = []
                for ex_el in db.select(".examp.dexamp")[:3]:
                    if ex_el.find_parent(class_="phrase-block"):
                        continue
                    eg = ex_el.select_one(".eg.deg") or ex_el.select_one(".eg")
                    en_text = _text(eg) if eg else ""
                    if not en_text:
                        continue
                    ex_trans = ex_el.select_one(".trans.dtrans") or ex_el.select_one(".trans")
                    examples.append({"en": en_text, "zh": _text(ex_trans) if ex_trans else ""})
                if en or zh:
                    xrefs = _parse_xrefs(db)
                    definitions.append({
                        "en": en, "zh": zh,
                        "gram": gram, "label": label, "usage": usage,
                        "examples": examples, "phrases": [],
                        "synonyms": xrefs["synonyms"], "antonyms": xrefs["antonyms"],
                    })

        if pos or definitions:
            result["entries"].append({
                "pos": pos, "pos_gram": pos_gram,
                "source": source, "definitions": definitions})

    # ── Idiom pages (e.g. "feel free") ───────────────────────────────────────
    # These pages have no .entry-body__el; content lives in .idiom-block instead.
    if not result["entries"]:
        idiom_block = None
        for ib in soup.select(".idiom-block"):
            if ib.select_one(".idiom-body, .didiom-body"):
                idiom_block = ib
                break

        if idiom_block:
            # Update word from the page headword (slug uses hyphens, headword has spaces)
            hw_el = (idiom_block.select_one(".headword.dhw") or
                     idiom_block.select_one(".headword") or
                     idiom_block.select_one("h2"))
            if hw_el:
                hw = _text(hw_el)
                # Clean up spaces around punctuation in headwords like
                # "be in the mood ( for something /to do something )"
                hw = re.sub(r"\(\s+", "(", hw)
                hw = re.sub(r"\s+\)", ")", hw)
                hw = re.sub(r"\s*/\s*", "/", hw)
                result["word"] = hw

            pos_el = idiom_block.select_one(".di-info .pos.dpos") or \
                     idiom_block.select_one(".di-info .pos")
            pos = _text(pos_el) if pos_el else "idiom"

            definitions = []
            idiom_body = idiom_block.select_one(".idiom-body, .didiom-body")
            for db in idiom_body.select(".ddef_block, .def-block"):
                def_el = db.select_one(".def.ddef_d") or db.select_one(".def")
                en     = _text(def_el).rstrip(":") if def_el else ""
                zh     = _def_trans(db)
                gram   = _text(db.select_one(".gram.dgram") or db.select_one(".gram"))
                label  = _text(db.select_one(".lab.dlab")   or db.select_one(".lab"))
                usage  = _text(db.select_one(".usage.dusage"))
                examples = []
                for ex_el in db.select(".examp.dexamp")[:3]:
                    eg = ex_el.select_one(".eg.deg") or ex_el.select_one(".eg")
                    en_text = _text(eg) if eg else ""
                    if not en_text:
                        continue
                    ex_trans = ex_el.select_one(".trans.dtrans") or ex_el.select_one(".trans")
                    examples.append({"en": en_text,
                                     "zh": _text(ex_trans) if ex_trans else ""})
                if en or zh:
                    xrefs = _parse_xrefs(db)
                    definitions.append({
                        "en": en, "zh": zh, "gram": gram, "label": label,
                        "usage": usage, "guideword": "", "examples": examples,
                        "phrases": [],
                        "synonyms": xrefs["synonyms"], "antonyms": xrefs["antonyms"],
                    })

            if definitions:
                result["entries"].append({
                    "pos": pos, "pos_gram": "", "source": "", "definitions": definitions,
                })

    if not result["entries"]:
        result["error"] = "No definitions found"

    return result
