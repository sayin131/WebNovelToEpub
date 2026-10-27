#!/usr/bin/env python3
"""
novel2epub - download web novel chapters (Cloudflare-protected sites included) into an EPUB.

Setup (once):
    pip install -r requirements.txt     # needs Google Chrome (or Edge) installed

Usage:
    python novel2epub.py NOVEL_PAGE_OR_FIRST_CHAPTER_URL -n 100 --title "My Novel" --cover cover.png
"""
import argparse
import html
import io
import os
import re
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

def app_data_dir():
    """Per-user folder for the saved browser session (works for scripts and packaged apps)."""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    d = os.path.join(base, "NovelToEpub")
    os.makedirs(d, exist_ok=True)
    return d


PROFILE_DIR = os.path.join(app_data_dir(), "browser_profile")
MIN_CHARS = 200   # a page with less text than this is not treated as a chapter
LAUNCH_OPTS = dict(
    # --test-type hides Chrome's "unsupported command-line flag" warning bar
    args=["--disable-blink-features=AutomationControlled", "--test-type"],
    ignore_default_args=["--enable-automation"],
    chromium_sandbox=True,
)

# ---------------------------------------------------------------- in-page JS
JS_EXTRACT = r"""
() => {
  let best = null, bestScore = 0;
  for (const el of document.querySelectorAll("div,article,section,main,td")) {
    let score = 0;
    for (const c of el.children) {
      if (c.tagName === "P") score += (c.innerText || "").trim().length;
    }
    if (score > bestScore) { bestScore = score; best = el; }
  }
  let paras = [];
  if (best && bestScore > 300) {
    for (const c of best.children) {
      if (c.tagName === "P") {
        for (const line of (c.innerText || "").split("\n")) {
          const t = line.trim();
          if (t) paras.push(t);
        }
      }
    }
  } else {
    const cands = document.querySelectorAll("[id*=content],[class*=content],[id*=chapter],[class*=chapter],[class*=reading],[class*=text]");
    let top = null, topLen = 0;
    for (const el of cands) {
      const l = (el.innerText || "").length;
      if (l > topLen && l < 200000) { topLen = l; top = el; }
    }
    if (top) paras = top.innerText.split("\n").map(s => s.trim()).filter(Boolean);
  }

  let title = "";
  const sels = [".chapter-title", ".chr-title", "#chapter-title", "h2", "h1"];
  const found = [];
  for (const s of sels) {
    const e = document.querySelector(s);
    if (e && e.innerText.trim()) found.push(e.innerText.trim().split("\n")[0]);
  }
  title = found.find(t => /chapter|^\s*\d+|ch\./i.test(t)) || found[0] || document.title;

  let next = null;
  const bad = a => !a.href || a.getAttribute("href").startsWith("javascript") ||
      a.getAttribute("href") === "#" || a.classList.contains("disabled") ||
      a.classList.contains("isDisabled") || a.getAttribute("aria-disabled") === "true";
  for (const s of ['a[rel="next"]', "#next_chap", "a.nextchap", "a.next_chap", "a.btn-next", "a.next"]) {
    const a = document.querySelector(s);
    if (a && !bad(a)) { next = a.href; break; }
  }
  if (!next) {
    for (const a of document.querySelectorAll("a")) {
      const t = (a.innerText || "").trim().toLowerCase();
      if (/^(next|next chapter|next ›|next »|›|»|next >)$/.test(t) && !bad(a)) { next = a.href; break; }
    }
  }
  return { title, paras, next };
}
"""

JS_TOC = r"""
() => {
  const seen = new Set(), out = [];
  for (const a of document.querySelectorAll("a[href]")) {
    if (!/chapter|chap-|\/ch-|\/c\d+/i.test(a.href)) continue;
    if (a.href.includes("#") || seen.has(a.href)) continue;
    seen.add(a.href); out.push(a.href);
  }
  return out;
}
"""

JS_COVER = """
() => {
  const m = document.querySelector('meta[property="og:image"]');
  return m ? m.content : null;
}
"""

JS_SYNOPSIS = r"""
() => {
  const sels = ["[class*=summary]", "[class*=synopsis]", "[class*=description]",
                "[id*=summary]", "[id*=synopsis]", "[id*=description]"];
  let best = "";
  for (const s of sels) for (const e of document.querySelectorAll(s)) {
    const ps = [...e.querySelectorAll("p")].map(p => p.innerText.trim()).filter(Boolean);
    const t = ps.length ? ps.join("\n") : (e.innerText || "").trim();
    if (t.length > best.length && t.length < 5000) best = t;
  }
  if (!best) {
    const m = document.querySelector('meta[property="og:description"],meta[name="description"]');
    if (m) best = m.content || "";
  }
  return best;
}
"""

CHAPTER_URL_RE = re.compile(r"chapter|chap-|/ch-|/ch\d+|/c\d+", re.I)

# ---------------------------------------------------------------- browser
CHALLENGE_JS = r"""
() => {
  const t = (document.body ? document.body.innerText : "").toLowerCase();
  if (t.length < 3000) {
    const phrases = ["verifying you are human", "verify you are human", "just a moment",
      "checking your browser", "protect against malicious bots", "enable javascript and cookies"];
    if (phrases.some(p => t.includes(p))) return true;
    if (document.querySelector("#challenge-form, #cf-challenge-running, .cf-turnstile, iframe[src*='challenges.cloudflare.com']")) return true;
  }
  return false;
}
"""


def challenged(page):
    try:
        t = page.title().lower()
        if "just a moment" in t or "attention required" in t:
            return True
        return bool(page.evaluate(CHALLENGE_JS))
    except Exception:
        return True      # page is mid-navigation: treat as not ready yet


class Stopped(Exception):
    pass


def load(page, url, log=print, should_stop=lambda: False):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    waited = 0
    while challenged(page):
        if should_stop():
            raise Stopped()
        if waited == 0:
            log("  Cloudflare check or any other popups - please click it in the browser window...")
        page.wait_for_timeout(1000)
        waited += 1
        if waited > 180:
            raise RuntimeError("Cloudflare check or any other popups not passed in 3 minutes")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(500)


def launch_browser(p):
    """Open Chrome (or Edge, or Playwright's Chromium) with the saved session."""
    last = None
    for channel in ("chrome", "msedge", None):
        try:
            kw = dict(headless=False, **LAUNCH_OPTS)
            if channel:
                kw["channel"] = channel
            return p.chromium.launch_persistent_context(PROFILE_DIR, **kw)
        except Exception as e:
            last = e
    raise RuntimeError(
        "Could not start a browser. Please install Google Chrome "
        "(https://www.google.com/chrome/), close any Chrome windows opened by this app, and try again.\n"
        "Details: " + str(last).strip().splitlines()[0])


def reset_browser_data():
    """Forget the saved browser session (fixes a stuck Cloudflare check)."""
    import shutil
    shutil.rmtree(PROFILE_DIR, ignore_errors=True)


# ---------------------------------------------------------------- cover images
def convert_cover(data):
    """Convert any other image format (WebP, GIF, ...) to JPEG. Needs Pillow, or macOS 'sips'."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        return (buf.getvalue(), "jpg", "image/jpeg")
    except Exception:
        pass
    if sys.platform == "darwin":
        try:
            with tempfile.TemporaryDirectory() as d:
                src, dst = os.path.join(d, "in.img"), os.path.join(d, "out.jpg")
                with open(src, "wb") as f:
                    f.write(data)
                r = subprocess.run(["sips", "-s", "format", "jpeg", src, "--out", dst],
                                   capture_output=True, timeout=30)
                if r.returncode == 0 and os.path.exists(dst):
                    with open(dst, "rb") as f:
                        return (f.read(), "jpg", "image/jpeg")
        except Exception:
            pass
    return None


def cover_from_bytes(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return (data, "png", "image/png")
    if data[:3] == b"\xff\xd8\xff":
        return (data, "jpg", "image/jpeg")
    return convert_cover(data)


# ---------------------------------------------------------------- EPUB
CSS = """body{margin:0 5%;}h1,h2{text-align:center;margin:1em 0;}
p{text-align:justify;text-indent:1.2em;margin:0 0 .5em 0;line-height:1.4;}
.booktitle{font-size:1.7em;margin-top:2em;}.author{text-align:center;text-indent:0;margin-bottom:2em;}
.toc{margin:.45em 0;}.toc a{text-decoration:none;color:inherit;}"""

XH = ('<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" '
      'xmlns:epub="http://www.idpf.org/2007/ops">')


def build_epub(path, book_title, author, chapters, cover=None, synopsis=None):
    uid = "urn:uuid:" + str(uuid.uuid4())
    esc = html.escape
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def page(title, body):
        return (XH + f'<head><title>{esc(title)}</title>'
                '<link rel="stylesheet" type="text/css" href="style.css"/></head>'
                f'<body>{body}</body></html>')

    manifest, spine, nav_entries = [], [], []     # nav_entries: (title, href)
    cover_meta = ""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>')
        z.writestr("OEBPS/style.css", CSS)

        # 1) cover
        if cover:
            cdata, cext, cmime = cover
            z.writestr("OEBPS/cover." + cext, cdata)
            z.writestr("OEBPS/cover.xhtml", XH + '<head><title>Cover</title>'
                '<style>body{margin:0;text-align:center;}img{max-width:100%;max-height:100%;}</style></head>'
                f'<body><img src="cover.{cext}" alt="Cover"/></body></html>')
            manifest.append(f'<item id="cover-image" href="cover.{cext}" media-type="{cmime}" properties="cover-image"/>')
            manifest.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
            spine.append('<itemref idref="cover"/>')
            cover_meta = '<meta name="cover" content="cover-image"/>'

        # 2) title + synopsis
        if synopsis and synopsis.strip():
            paras = [p.strip() for p in re.split(r"\n+", synopsis) if p.strip()]
            body = (f'<h1 class="booktitle">{esc(book_title)}</h1><p class="author">{esc(author)}</p>'
                    '<h2>Synopsis</h2>' + "".join(f"<p>{esc(p)}</p>" for p in paras))
            z.writestr("OEBPS/synopsis.xhtml", page("Synopsis", body))
            manifest.append('<item id="synopsis" href="synopsis.xhtml" media-type="application/xhtml+xml"/>')
            spine.append('<itemref idref="synopsis"/>')
            nav_entries.append(("Synopsis", "synopsis.xhtml"))

        # 3) clickable table of contents page
        links = "".join(f'<div class="toc"><a href="ch{i:04d}.xhtml">{esc(t)}</a></div>\n'
                        for i, (t, _) in enumerate(chapters, 1))
        z.writestr("OEBPS/contents.xhtml", page("Table of Contents", f"<h2>Table of Contents</h2>\n{links}"))
        manifest.append('<item id="contents" href="contents.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="contents"/>')
        nav_entries.append(("Table of Contents", "contents.xhtml"))

        # 4) chapters
        for i, (title, paras) in enumerate(chapters, 1):
            fn = f"ch{i:04d}.xhtml"
            body = f"<h2>{esc(title)}</h2>\n" + "".join(f"<p>{esc(p)}</p>\n" for p in paras)
            z.writestr("OEBPS/" + fn, page(title, body))
            manifest.append(f'<item id="c{i}" href="{fn}" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="c{i}"/>')
            nav_entries.append((title, fn))

        # navigation documents (the reader's own TOC menu)
        z.writestr("OEBPS/nav.xhtml", XH + '<head><title>Contents</title></head><body>'
            '<nav epub:type="toc"><h2>Contents</h2><ol>' +
            "".join(f'<li><a href="{h}">{esc(t)}</a></li>' for t, h in nav_entries) +
            '</ol></nav></body></html>')
        z.writestr("OEBPS/toc.ncx",
            '<?xml version="1.0" encoding="utf-8"?>'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head>'
            f'<meta name="dtb:uid" content="{uid}"/></head>'
            f'<docTitle><text>{esc(book_title)}</text></docTitle><navMap>' +
            "".join(f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{esc(t)}</text></navLabel>'
                    f'<content src="{h}"/></navPoint>' for i, (t, h) in enumerate(nav_entries, 1)) +
            '</navMap></ncx>')

        desc = f'<dc:description>{esc(synopsis.strip())}</dc:description>' if synopsis and synopsis.strip() else ""
        z.writestr("OEBPS/content.opf",
            '<?xml version="1.0" encoding="utf-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:identifier id="bookid">{uid}</dc:identifier>'
            f'<dc:title>{esc(book_title)}</dc:title><dc:creator>{esc(author)}</dc:creator>{desc}'
            f'<dc:language>en</dc:language><meta property="dcterms:modified">{now}</meta>{cover_meta}</metadata>'
            '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            '<item id="css" href="style.css" media-type="text/css"/>' + "".join(manifest) + '</manifest>'
            '<spine toc="ncx">' + "".join(spine) + '</spine></package>')


# ---------------------------------------------------------------- core
def slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:60] or "novel"


def chap_num(u):
    nums = re.findall(r"\d+", urlparse(u).path)
    return int(nums[-1]) if nums else None


def with_num(u, n):
    p = urlparse(u)
    ms = list(re.finditer(r"\d+", p.path))
    if not ms:
        return None
    m = ms[-1]
    return p._replace(path=p.path[:m.start()] + str(n) + p.path[m.end():]).geturl()


def clean_synopsis(t):
    lines = [l.strip() for l in (t or "").splitlines() if l.strip()]
    if lines and lines[0].lower().rstrip(":") in ("synopsis", "summary", "description"):
        lines = lines[1:]
    return "\n".join(lines)


def download(url=None, toc=None, count=50, title="Web Novel", author="Unknown",
             output=None, delay=2.0, remove=(), log=print, should_stop=lambda: False,
             on_progress=lambda done, total: None, start=None, cover_path=None,
             synopsis=None, auto_meta=True):
    """Download chapters and write an EPUB. Returns the output path or None."""
    if not url and not toc:
        raise ValueError("Give a first-chapter URL or a novel page URL")
    removers = [re.compile(r, re.I) for r in remove if r.strip()]
    out = output or slug(title) + ".epub"
    chapters, visited = [], set()
    synopsis = clean_synopsis(synopsis)
    cover = None
    if cover_path:
        try:
            with open(cover_path, "rb") as f:
                cover = cover_from_bytes(f.read())
            if cover:
                log(f"Cover loaded ({cover[1].upper()}).")
            else:
                log("Could not use that cover image (unknown format). Install Pillow "
                    "(pip install pillow) so other formats like WebP can be converted. "
                    "Continuing without a cover.")
        except OSError as e:
            log(f"Could not read cover image ({e}) - continuing without a cover.")

    with sync_playwright() as p:
        ctx = launch_browser(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        try:
            # A novel's main page pasted into "first chapter" mode -> switch automatically
            if url and not toc and not CHAPTER_URL_RE.search(urlparse(url).path):
                load(page, url, log, should_stop)
                if len(page.evaluate(JS_TOC)) >= 3:
                    log("That looks like the novel's main page, not a chapter - using novel page mode.")
                    toc, url = url, None

            if toc:
                log("Reading novel page...")
                load(page, toc, log, should_stop)
                links = [(chap_num(l), l) for l in page.evaluate(JS_TOC)]
                links = [(n, l) for n, l in links if n is not None]
                if not links:
                    log("No chapter links found on that page. Use the first-chapter URL instead.")
                    return None
                url = with_num(links[0][1], int(start)) if start else min(links)[1]
                log(f"Starting at: {url}")

                if auto_meta and not cover:
                    try:
                        img = page.evaluate(JS_COVER)
                        if img:
                            resp = ctx.request.get(img)
                            cover = cover_from_bytes(resp.body()) if resp.ok else None
                        log("Cover grabbed from the novel page." if cover else
                            "No usable cover found on the novel page.")
                    except Exception as e:
                        log(f"Could not fetch a cover automatically ({e}).")
                if auto_meta and not synopsis:
                    try:
                        synopsis = clean_synopsis(page.evaluate(JS_SYNOPSIS))
                        log("Synopsis grabbed from the novel page." if synopsis else
                            "No synopsis found on the novel page.")
                    except Exception as e:
                        log(f"Could not fetch a synopsis automatically ({e}).")

            guessed = False
            while url and len(chapters) < count:
                if should_stop():
                    log("Stopped by user - saving what we have.")
                    break
                if url in visited:
                    log("Reached an already-visited page, stopping.")
                    break
                visited.add(url)
                log(f"[{len(chapters) + 1}] {url}")
                data = None
                for _ in (1, 2, 3):
                    load(page, url, log, should_stop)
                    data = page.evaluate(JS_EXTRACT)
                    if sum(len(t) for t in data["paras"]) >= MIN_CHARS and not challenged(page):
                        break
                    log("  Page not ready / not a chapter yet, retrying...")
                    page.wait_for_timeout(4000)
                else:
                    if guessed:
                        log("  No further chapter found - reached the end.")
                    else:
                        log("  Could not get chapter text (verification not passed, or the site "
                            "layout is unsupported). Stopping without saving this page.")
                    break
                paras = [t for t in data["paras"] if not any(r.search(t) for r in removers)]
                if paras and paras[0].strip().lower() == data["title"].strip().lower():
                    paras = paras[1:]
                if not paras:
                    log("  No text found on this page, stopping.")
                    break
                chapters.append((data["title"], paras))
                log(f"    {data['title']}  ({len(paras)} paragraphs)")
                on_progress(len(chapters), count)

                url, guessed = data["next"], False
                if not url and toc:                      # no Next button: try chapter number + 1
                    n = chap_num(page.url)
                    url = with_num(page.url, n + 1) if n is not None else None
                    guessed = bool(url)
                    if url:
                        log("  (no Next button found, trying the next chapter number)")
                if url:
                    page.wait_for_timeout(int(delay * 1000))
        except Stopped:
            log("Stopped by user - saving what we have.")
        except KeyboardInterrupt:
            log("Stopped by user - saving what we have.")
        except Exception as e:
            log(f"Error: {e} - saving what we have.")
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    if not chapters:
        log("Nothing downloaded.")
        return None
    build_epub(out, title, author, chapters, cover, synopsis)
    extras = [x for x, ok in (("cover", cover), ("synopsis", synopsis)) if ok]
    log(f"Saved {len(chapters)} chapters{' with ' + ' and '.join(extras) if extras else ''} -> {out}")
    return out


def main():
    ap = argparse.ArgumentParser(description="Download web novel chapters into an EPUB")
    ap.add_argument("url", nargs="?", help="URL of the FIRST chapter (or the novel's main page)")
    ap.add_argument("--toc", help="novel page URL; starts from its first chapter")
    ap.add_argument("-n", "--count", type=int, default=50, help="max chapters (default 50)")
    ap.add_argument("--title", default="Web Novel")
    ap.add_argument("--author", default="Unknown")
    ap.add_argument("-o", "--output", help="output .epub path")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between chapters (default 2)")
    ap.add_argument("--remove", action="append", default=[], help="regex; matching paragraphs are dropped")
    ap.add_argument("--start", type=int, help="novel page mode: start at this chapter number")
    ap.add_argument("--cover", help="cover image file")
    ap.add_argument("--synopsis", help="synopsis text")
    ap.add_argument("--synopsis-file", help="text file containing the synopsis")
    ap.add_argument("--no-auto-meta", action="store_true", help="don't try to grab cover/synopsis from the novel page")
    a = ap.parse_args()
    if not a.url and not a.toc:
        ap.error("give a chapter URL or --toc NOVEL_PAGE_URL")
    syn = a.synopsis
    if a.synopsis_file:
        with open(a.synopsis_file, encoding="utf-8") as f:
            syn = f.read()
    if not download(a.url, a.toc, a.count, a.title, a.author, a.output, a.delay, a.remove,
                    start=a.start, cover_path=a.cover, synopsis=syn, auto_meta=not a.no_auto_meta):
        sys.exit(1)


if __name__ == "__main__":
    main()
