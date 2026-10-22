# WebNovel to EPUB

Turn web novels into clean, well-formatted **EPUB** files for your Kindle (via KOReader), phone or e-reader.
Click-to-run desktop app for **Windows, macOS and Linux**. It drives a real browser window, so it also works on sites protected by Cloudflare "verify you are human" checks.

> Inspired by [Novel-Grabber](https://github.com/Flameish/Novel-Grabber).

---

## ⚠️ Disclaimer & Warning

- **Most sites prohibit scraping of their content. Use at your own risk.** You are solely responsible for how you use this tool and for complying with the terms of service of any site you use it on.
- **Please use appropriate wait times** between chapters (the default delay is 2 seconds; increase it if a site is slow or rate-limits you). Do not hammer servers.
- **Downloaded chapters are for private use only.** Do not redistribute, publish or sell the generated EPUBs. The content belongs to its authors, translators and publishers.
- This project is provided "as is", without warranty of any kind. The author takes no responsibility for any consequences of its use, including blocked IP addresses or banned accounts.
- This tool does not bypass or break any security system; a human passes the site's verification in the visible browser window.

---

## Features

- Click-to-run app with a simple window: no terminal needed
- Works with Cloudflare-protected sites (you click the check once; the session is remembered)
- **Two ways to start:** the novel's main page (finds chapter 1 automatically) or any chapter URL
- Follows the "Next" button in the correct order, with a fallback to the next chapter number
- Extracts only the text: no ads, menus or comments
- EPUB output with a **cover image**, a **title + synopsis** page, a **clickable table of contents**, and justified, indented paragraphs
- Cover and synopsis can be added by hand or grabbed automatically from the novel page
- Remove unwanted lines (watermarks, ads) with simple filters
- **Stop & save** at any time; start at any chapter number to continue a novel

---

## 1. Easiest: download the app

1. Install **Google Chrome** (https://www.google.com/chrome/), which is required on macOS and Linux. On Windows, Microsoft Edge also works. On Linux, Chromium installed through Playwright also works.
2. Go to the **[Releases](../../releases)** page and download the file for your system
3. Unzip it and double-click **NovelToEpub**.

**The app is not code-signed**, so your system will warn you the first time:

- **macOS:** *"NovelToEpub can't be opened because Apple cannot check it for malicious software."* → **Right-click the app → Open → Open**. If macOS still refuses, run this once in Terminal:
  `xattr -dr com.apple.quarantine /path/to/NovelToEpub.app`
  (or: *System Settings → Privacy & Security → "Open Anyway"*).
- **Windows:** *"Windows protected your PC"* → **More info → Run anyway**.
- **Linux:** `chmod +x NovelToEpub` then run it.

Intel Mac? Use option 2 below.

## 2. Run from source with a double-click launcher

Needs Python 3.10+ (with Tkinter) and Google Chrome.

1. Download or clone this repository.
2. Double-click:
   - **macOS:** `Start-Mac.command` (first time: right-click → Open. If it says permission denied, run `chmod +x Start-Mac.command` once)
   - **Windows:** `Start-Windows.bat`

The first run creates a private environment and installs what it needs (takes a minute); after that it starts instantly.

## 3. Run from the terminal

```bash
git clone https://github.com/sayin131/WebNovelToEpub.git
cd NovelToEpub

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

python3 novel2epub_gui.py         # the app window
# or the command line:
python3 novel2epub.py "https://example.com/novel/some-novel/" -n 50 --title "Some Novel"
```

**Tkinter** (for the window) comes with the python.org installers. If you see `No module named '_tkinter'`:
Homebrew → `brew install python-tk@3.12` (match your Python version), Debian/Ubuntu → `sudo apt install python3-tk`.

---

## Using the app

1. Paste the **novel's main page URL** (or a chapter URL) and fill in the title and author.
2. Choose **Max chapters**. Optionally pick a **cover image**, paste a **synopsis**, set **Start at chapter #**.
3. Press **Start**. A browser window opens. **If a verification check appears, click it once and leave the window open.**
4. When it finishes, the EPUB is saved to the folder you chose, and the app offers to show it.

| Field | Meaning |
|---|---|
| **Start from** | *First chapter URL* follows Next from that chapter. *Novel page* finds the first chapter itself. (A main page pasted into the first option switches automatically.) |
| **Remove lines matching** | Comma-separated words or regexes; matching paragraphs are dropped (e.g. `visit novelsite, read at`) |
| **Delay (s)** | Pause between chapters. Be polite: 2-5 seconds |
| **Start at chapter #** | Novel page mode only. Blank = chapter 1 |
| **Cover image** | Optional JPG/PNG. WebP and other formats are converted automatically |
| **Synopsis** | Optional text shown at the start of the book |
| **Auto-grab checkbox** | If cover/synopsis are empty, try to take them from the novel page |
| **Stop & save** | Ends early but still writes the EPUB with what was downloaded |
| **Reset browser data** | Forgets the saved verification session (use it if the check gets stuck) |

### Command-line options

```bash
python3 novel2epub.py "https://example.com/novel/some-novel/" -n 100 \
    --title "Some Novel" --author "Author" --cover cover.png --synopsis-file synopsis.txt
```

| Option | Description |
|---|---|
| `url` | Chapter URL or novel main page |
| `--toc URL` | Force novel-page mode |
| `-n, --count N` | Max chapters (default 50) |
| `--title`, `--author` | Book metadata |
| `-o, --output FILE` | Output path |
| `--delay SECONDS` | Wait between chapters (default 2) |
| `--remove REGEX` | Drop matching paragraphs (repeatable) |
| `--start N` | Start at chapter N (novel page mode) |
| `--cover FILE` | Cover image |
| `--synopsis TEXT` / `--synopsis-file FILE` | Synopsis |
| `--no-auto-meta` | Don't try to grab cover/synopsis from the novel page |

---

## Reading on a Kindle (KOReader) or other devices

1. Connect the Kindle (jailbroken, with [KOReader](https://github.com/koreader/koreader)) by USB.
2. Copy the `.epub` into the `documents` folder.
3. Open it in KOReader. You can change font, margins and justification there.

The EPUB also works in Apple Books, Calibre, Kobo, Moon+ Reader, etc.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not start a browser" | Install Google Chrome, and close any browser windows opened earlier by this app |
| Stuck on "Cloudflare check…" | Click the checkbox in the browser window. If it spins forever, press **Reset browser data** and try again |
| "Could not get chapter text" | The check wasn't passed, or the site layout isn't recognised. Retry with a longer delay and open an issue with the log |
| Cover not used | Make sure it is a real image file. If you run from source, `pip install -r requirements.txt` includes Pillow, which converts WebP |
| Chapters in the wrong order / only one page | Use the novel's main page URL, or the **first** chapter, not a later chapter |
| Junk lines in the text | Add them to **Remove lines matching** |
| Browser shows an "unsupported command-line flag" bar | Harmless; it is how the app looks less like an automated browser |
| macOS / Windows warns about an unknown developer | See the notes in section 1 |

Where the app stores its saved browser session:
macOS `~/Library/Application Support/NovelToEpub` · Windows `%APPDATA%\NovelToEpub` · Linux `~/.local/share/NovelToEpub`.

## How it works

1. Opens your installed Chrome (or Edge) through [Playwright](https://playwright.dev/python/) with a saved profile, so verification cookies are remembered.
2. For each chapter, finds the element holding the most paragraph text, takes its paragraphs and title, and finds the "Next" link.
3. Builds a valid EPUB 3 (with an EPUB 2 NCX fallback) using only the Python standard library.

Text extraction is heuristic (not tied to one site), so unusual layouts may need tweaks. Issues and pull requests are welcome.

---

## For developers: building the app

**Automatically (recommended):** push a version tag and GitHub Actions builds Windows, macOS (Apple Silicon) and Linux apps and attaches them to a Release:

```bash
git tag v1.0.0
git push --tags
```
You can also run the workflow manually from the **Actions** tab (**Build apps → Run workflow**); the zips appear as build artifacts.

**Locally:**

```bash
pip install -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm --windowed --name NovelToEpub --collect-all playwright --hidden-import PIL.Image novel2epub_gui.py
# macOS/Linux output: dist/NovelToEpub(.app)   Windows: add --onefile -> dist/NovelToEpub.exe
```

Project layout:

```
novel2epub.py          core downloader + EPUB builder (also the CLI)
novel2epub_gui.py      desktop window
Start-Mac.command      double-click launcher (macOS)
Start-Windows.bat      double-click launcher (Windows)
requirements.txt       runtime dependencies
requirements-build.txt packaging dependency (PyInstaller)
.github/workflows/     automatic app builds
```

## Privacy & security

The saved browser session (cookies) is stored only on your computer, outside this repository. Never share that folder.

## License

Released under the [MIT License](LICENSE): free for anyone to use, copy, modify and share, including for commercial use, as long as the copyright notice is kept.

The license covers **this software only**. It does not give you any rights to the novels or other content you download with it, and it does not override the terms of service of any website. See the Disclaimer & Warning above.

Third-party libraries keep their own licenses (Playwright: Apache-2.0, Pillow: HPND, PyInstaller: GPL with a special exception that allows bundling apps under any license).
