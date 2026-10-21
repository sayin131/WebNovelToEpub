#!/usr/bin/env python3
"""GUI for novel2epub.  Run:  python novel2epub_gui.py"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import novel2epub


def reveal(path):
    """Show the saved file in Finder / Explorer / the file manager."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", path])
        elif sys.platform.startswith("win"):
            subprocess.run(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.run(["xdg-open", os.path.dirname(path)])
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Novel to EPUB")
        self.geometry("780x820")
        self.minsize(640, 520)
        self.q = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker = None

        self.mode = tk.StringVar(value="chapter")
        self.url = tk.StringVar()
        self.book_title = tk.StringVar()
        self.author = tk.StringVar(value="Unknown")
        self.count = tk.IntVar(value=50)
        self.delay = tk.DoubleVar(value=2.0)
        self.remove = tk.StringVar()
        self.start = tk.StringVar()
        self.cover = tk.StringVar()
        self.auto_cover = tk.BooleanVar(value=True)
        self.output = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Documents"))

        self._build()
        self.after(100, self._poll)

    # ------------------------------------------------------------ layout
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        f = ttk.Frame(self, padding=10)
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)

        ttk.Label(f, text="Start from:").grid(row=0, column=0, sticky="w", **pad)
        m = ttk.Frame(f)
        m.grid(row=0, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(m, text="First chapter URL (follows Next)", variable=self.mode,
                        value="chapter").pack(side="left", padx=4)
        ttk.Radiobutton(m, text="Novel page (reads chapter list)", variable=self.mode,
                        value="toc").pack(side="left", padx=4)

        rows = [
            ("URL:", self.url), ("Book title:", self.book_title), ("Author:", self.author),
            ("Remove lines matching:", self.remove),
        ]
        r = 1
        for label, var in rows:
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", **pad)
            ttk.Entry(f, textvariable=var).grid(row=r, column=1, columnspan=2, sticky="ew", **pad)
            r += 1
        ttk.Label(f, text="(comma-separated; e.g.  lightnovelpub, read at)", foreground="gray")\
            .grid(row=r, column=1, columnspan=2, sticky="w", padx=8)
        r += 1

        ttk.Label(f, text="Max chapters:").grid(row=r, column=0, sticky="w", **pad)
        n = ttk.Frame(f)
        n.grid(row=r, column=1, sticky="w")
        ttk.Spinbox(n, from_=1, to=5000, textvariable=self.count, width=7).pack(side="left", padx=8)
        ttk.Label(n, text="Delay (s):").pack(side="left", padx=(16, 4))
        ttk.Spinbox(n, from_=0, to=30, increment=0.5, textvariable=self.delay, width=5).pack(side="left")
        r += 1

        ttk.Label(f, text="Start at chapter #:").grid(row=r, column=0, sticky="w", **pad)
        st = ttk.Frame(f)
        st.grid(row=r, column=1, sticky="w")
        ttk.Entry(st, textvariable=self.start, width=8).pack(side="left", padx=8)
        ttk.Label(st, text="(novel page mode only; blank = first chapter)", foreground="gray").pack(side="left")
        r += 1

        ttk.Label(f, text="Cover image:").grid(row=r, column=0, sticky="w", **pad)
        ttk.Entry(f, textvariable=self.cover).grid(row=r, column=1, sticky="ew", **pad)
        ttk.Button(f, text="Browse…", command=self._browse_cover).grid(row=r, column=2, **pad)
        r += 1
        ttk.Label(f, text="Synopsis (optional):").grid(row=r, column=0, sticky="nw", **pad)
        self.synopsis = tk.Text(f, height=5, wrap="word")
        self.synopsis.grid(row=r, column=1, columnspan=2, sticky="ew", **pad)
        r += 1
        ttk.Checkbutton(f, text="If cover / synopsis are empty, try to grab them from the novel page",
                        variable=self.auto_cover).grid(row=r, column=1, columnspan=2, sticky="w", padx=8)
        r += 1

        ttk.Label(f, text="Save to folder:").grid(row=r, column=0, sticky="w", **pad)
        ttk.Entry(f, textvariable=self.output).grid(row=r, column=1, sticky="ew", **pad)
        ttk.Button(f, text="Browse…", command=self._browse).grid(row=r, column=2, **pad)

        b = ttk.Frame(self, padding=(10, 0))
        b.pack(fill="x")
        self.start_btn = ttk.Button(b, text="Start", command=self._start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(b, text="Stop & save", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        self.reset_btn = ttk.Button(b, text="Reset browser data", command=self._reset)
        self.reset_btn.pack(side="left", padx=4)
        self.status = ttk.Label(b, text="Ready")
        self.status.pack(side="right", padx=4)

        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.pack(fill="x", padx=14, pady=6)

        self.log = ScrolledText(self, height=14, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        self._log("Requires Google Chrome (or Edge). A browser window will open: if a verification check appears, click it once and leave the window open.")

    # ------------------------------------------------------------ actions
    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.output.get() or ".")
        if d:
            self.output.set(d)

    def _browse_cover(self):
        p = filedialog.askopenfilename(title="Choose cover image",
                                       filetypes=[("JPG / PNG images", "*.jpg *.jpeg *.png")])
        if p:
            self.cover.set(p)

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self):
        url = self.url.get().strip()
        if not url.startswith("http"):
            messagebox.showerror("Missing URL", "Enter a URL starting with http:// or https://")
            return
        title = self.book_title.get().strip() or "Web Novel"
        folder = self.output.get().strip() or "."
        os.makedirs(folder, exist_ok=True)
        out = os.path.join(folder, novel2epub.slug(title) + ".epub")
        removes = [x.strip() for x in self.remove.get().split(",") if x.strip()]
        kw = dict(
            url=url if self.mode.get() == "chapter" else None,
            toc=url if self.mode.get() == "toc" else None,
            count=max(1, int(self.count.get())), title=title,
            author=self.author.get().strip() or "Unknown",
            output=out, delay=float(self.delay.get()), remove=removes,
            start=int(self.start.get()) if self.start.get().strip().isdigit() else None,
            cover_path=self.cover.get().strip() or None,
            synopsis=self.synopsis.get("1.0", "end").strip() or None,
            auto_meta=bool(self.auto_cover.get()),
        )
        self.stop_flag.clear()
        self.bar.configure(value=0, maximum=kw["count"])
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status.configure(text="Working…")
        self.worker = threading.Thread(target=self._run, args=(kw,), daemon=True)
        self.worker.start()

    def _run(self, kw):
        try:
            result = novel2epub.download(
                log=lambda m: self.q.put(("log", m)),
                should_stop=self.stop_flag.is_set,
                on_progress=lambda d, t: self.q.put(("progress", (d, t))),
                **kw)
        except Exception as e:
            self.q.put(("log", f"Error: {e}"))
            result = None
        self.q.put(("done", result))

    def _reset(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "Wait for the current download to finish (or press Stop) first.")
            return
        if messagebox.askyesno("Reset browser data",
                               "This forgets the saved Cloudflare session.\n"
                               "Use it if the verification gets stuck. Continue?"):
            novel2epub.reset_browser_data()
            self._log("Browser data reset. You may need to pass the verification again.")

    def _stop(self):
        self.stop_flag.set()
        self.stop_btn.configure(state="disabled")
        self.status.configure(text="Stopping…")

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self._log(val)
                elif kind == "progress":
                    done, total = val
                    self.bar.configure(maximum=total, value=done)
                    self.status.configure(text=f"{done} / {total} chapters")
                elif kind == "done":
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.status.configure(text="Done" if val else "Finished (nothing saved)")
                    if val and messagebox.askyesno("Saved", f"EPUB saved:\n{val}\n\nShow it in the folder?"):
                        reveal(val)
        except queue.Empty:
            pass
        self.after(100, self._poll)


if __name__ == "__main__":
    App().mainloop()
