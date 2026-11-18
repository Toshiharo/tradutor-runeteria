"""Tradutor Runeteria - traduz as telas do servidor Runeteria (Hytale) para portugues.

So funciona quando: a janela do Hytale esta em foco E o log do jogo mostra que voce
esta dentro do play.runeteria.com. Em qualquer outro servidor ele fica desligado.
"""
import os
import queue
import threading
import time
import tkinter as tk
import traceback
from tkinter import font as tkfont

import config
from config import APP_NAME, ERROR_LOG, HYTALE_LOGS, MODEL_DIR, SCREEN_DUMP, USER_DIR
from library import Library
from lock import RuneteriaLock
from pipeline import Translator
from style import DESCENDERS, add_colors, avail_width, font_px

KEY_COLOR = "#ff00fe"  # cor "invisivel" do overlay


def log_error():
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("\n[%Y-%m-%d %H:%M:%S]\n") + traceback.format_exc())


class App:
    def __init__(self):
        import winutil
        self.w = winutil
        winutil.set_dpi_aware()
        self.cfg = config.load_config()
        self.ui_q = queue.Queue()
        self.enabled = True
        self.visible = True
        self.last_lines = []
        self.last_boxes = []
        self.drawn_sig = None
        self.mt = None
        self.ocr = None
        self.translator = None
        self.capture_safe = True
        self.hidden_for_capture = threading.Event()

        self.lib = Library()
        self.lock = RuneteriaLock(HYTALE_LOGS, self.cfg["servidor"])

        # ---- janela de controle ----
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("380x260")
        self.root.configure(bg="#1b1f2a")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        st = {"bg": "#1b1f2a", "fg": "#e8e2d0", "anchor": "w", "font": ("Segoe UI", 10)}
        tk.Label(self.root, text="Tradutor Runeteria", bg="#1b1f2a", fg="#f0c869",
                 font=("Segoe UI", 14, "bold")).pack(fill="x", padx=12, pady=(10, 2))
        self.lbl_server = tk.Label(self.root, text="Servidor: ...", **st)
        self.lbl_server.pack(fill="x", padx=12)
        self.lbl_state = tk.Label(self.root, text="Iniciando...", **st)
        self.lbl_state.pack(fill="x", padx=12)
        self.lbl_lib = tk.Label(self.root, text="", **st)
        self.lbl_lib.pack(fill="x", padx=12)
        self.lbl_info = tk.Label(self.root, text="", wraplength=350, justify="left", **st)
        self.lbl_info.pack(fill="x", padx=12, pady=(0, 6))
        bar = tk.Frame(self.root, bg="#1b1f2a")
        bar.pack(fill="x", padx=10)
        bs = {"bg": "#2c3343", "fg": "#e8e2d0", "relief": "flat", "font": ("Segoe UI", 9), "padx": 6}
        self.btn_toggle = tk.Button(bar, text=f"Desligar ({self.cfg['atalho_liga_desliga']})", command=self.toggle, **bs)
        self.btn_toggle.grid(row=0, column=0, padx=2, pady=2, sticky="we")
        tk.Button(bar, text="Procurar telas novas", command=self.run_updater_async, **bs).grid(row=0, column=1, padx=2, pady=2, sticky="we")
        tk.Button(bar, text="Recarregar minhas traduções", command=self.reload_user, **bs).grid(row=1, column=0, padx=2, pady=2, sticky="we")
        tk.Button(bar, text="Abrir pasta de traduções", command=lambda: os.startfile(USER_DIR), **bs).grid(row=1, column=1, padx=2, pady=2, sticky="we")
        bar.columnconfigure(0, weight=1)
        bar.columnconfigure(1, weight=1)
        tk.Label(self.root, text=f"{self.cfg['atalho_liga_desliga']} liga/desliga · {self.cfg['atalho_esconder']} mostra o original · "
                 f"{self.cfg['atalho_salvar_tela']} salva a tela em texto", bg="#1b1f2a", fg="#8f96a8",
                 font=("Segoe UI", 8)).pack(fill="x", padx=12, pady=(6, 0))

        # ---- overlay ----
        self.ov = tk.Toplevel(self.root)
        self.ov.overrideredirect(True)
        self.ov.attributes("-topmost", True)
        self.ov.configure(bg=KEY_COLOR)
        self.ov.attributes("-transparentcolor", KEY_COLOR)
        self.canvas = tk.Canvas(self.ov, bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.ov.geometry("10x10+0+0")
        self.ov.update_idletasks()
        self.ov_hwnd = winutil.toplevel_hwnd(self.ov.winfo_id())
        self.capture_safe = winutil.make_overlay(self.ov_hwnd)
        self.ov.withdraw()
        self.ov_shown = False
        self.root.update_idletasks()
        self.ctrl_hwnd = winutil.toplevel_hwnd(self.root.winfo_id())
        self.fonts = {}

        hk = winutil.Hotkeys({
            self.cfg["atalho_liga_desliga"]: lambda: self.ui_q.put(("toggle",)),
            self.cfg["atalho_esconder"]: lambda: self.ui_q.put(("peek",)),
            self.cfg["atalho_salvar_tela"]: lambda: self.ui_q.put(("dump",)),
        }, on_failed=lambda keys: self.ui_q.put(
            ("info", "Atalho indisponível (em uso por outro programa?): " + ", ".join(keys)
             + ". Troque em config.json.")))
        hk.start()

        self.refresh_lib_label()
        threading.Thread(target=self.load_models, daemon=True).start()
        threading.Thread(target=self.worker, daemon=True).start()
        self.root.after(50, self.pump)

    # ---------- carregamento ----------
    def load_models(self):
        self.ui_q.put(("info", "Carregando tradução offline..."))
        try:
            from mt import OfflineTranslator
            self.mt = OfflineTranslator(MODEL_DIR, self.lib.glossary, self.lib.terms)
            if not self.mt.ok:
                self.ui_q.put(("info", "Tradução automática indisponível (só biblioteca). " + (self.mt.error or "")))
        except Exception:
            log_error()
            self.mt = None
        self.translator = Translator(self.lib, self.mt, self.cfg)
        try:
            from ocr_engine import WindowsOcr
            self.ocr = WindowsOcr()
        except Exception as e:
            log_error()
            self.ocr = None
            self.ui_q.put(("info", f"OCR indisponível: {e}"))
            return
        if self.ocr.warning:
            self.ui_q.put(("info", self.ocr.warning))
        elif self.mt is not None and self.mt.ok:
            self.ui_q.put(("info", "Pronto."))
        self.run_updater(quiet=bool(self.ocr.warning))

    def run_updater_async(self):
        threading.Thread(target=self.run_updater, daemon=True).start()

    def run_updater(self, quiet=False):
        """quiet: nao troca o aviso que esta na tela se nao houver novidade."""
        if self.translator is None:
            return
        try:
            from updater import Updater
            up = Updater(self.lib, self.mt, self.cfg["servidor"], status_cb=lambda s: self.ui_q.put(("info", s)))
            n = up.scan()
            if n is None:
                return  # ja tem uma verificacao rodando
            if n:
                self.ui_q.put(("info", f"Telas verificadas. {n} textos novos traduzidos."))
            elif not quiet:
                self.ui_q.put(("info", "Telas verificadas. Nada novo."))
        except Exception:
            log_error()
            self.ui_q.put(("info", "Erro ao procurar telas novas (veja erros.log)."))
        self.ui_q.put(("libstats",))

    # ---------- loop de captura (thread) ----------
    def worker(self):
        import mss
        from PIL import Image
        sct = (getattr(mss, "MSS", None) or mss.mss)()  # mss 10 renomeou mss.mss para mss.MSS
        hwnd, hwnd_time = None, 0
        last_sig = None
        last_status = None
        hidden = False
        was_active = False
        while True:
            time.sleep(self.cfg["intervalo_segundos"])
            try:
                self.lib.save(force=False)  # grava a memoria automatica aos poucos (no maximo a cada 10 s)
                if not hwnd or time.time() - hwnd_time > 3:
                    hwnd, hwnd_time = self.w.find_hytale_window(), time.time()
                active = self.lock.active()
                status = ("server", self.lock.describe(), active, bool(hwnd))
                if (status, self.enabled) != last_status:  # so mexe na interface quando algo muda
                    self.ui_q.put(status)
                    last_status = (status, self.enabled)
                if active and not was_active:
                    self.run_updater_async()  # acabou de entrar: confere se veio tela nova
                was_active = active
                if not self.enabled or self.translator is None or self.ocr is None or \
                        not hwnd or not active or self.w.is_minimized(hwnd) or \
                        not self.w.is_foreground(hwnd, (self.ov_hwnd,)):
                    # so com o JOGO em foco: com outra janela na frente (Discord, navegador) a captura
                    # pegaria o texto dela e mandaria para a traducao automatica
                    if not hidden:
                        self.ui_q.put(("hide",))
                        hidden = True
                    last_sig = None
                    continue
                hidden = False
                rect = self.w.client_rect(hwnd)
                if not rect:
                    continue
                x, y, w, h = rect
                if not self.capture_safe and self.ov_shown:
                    self.hidden_for_capture.clear()
                    self.ui_q.put(("hide",))
                    self.hidden_for_capture.wait(0.4)
                    time.sleep(0.03)
                shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                sig = img.resize((96, 54)).convert("L").tobytes()
                if sig == last_sig:
                    boxes = self.translator.boxes(self.last_lines)  # pega traducoes que acabaram de ficar prontas
                else:
                    lines = self.ocr.recognize(img, self.cfg["escala_ocr"])
                    if self.cfg["usar_cores_da_tela"]:
                        add_colors(img, lines)
                    self.last_lines = lines
                    boxes = self.translator.boxes(lines)
                    last_sig = sig
                self.ui_q.put(("boxes", rect, boxes))
            except Exception:
                log_error()
                time.sleep(2)

    # ---------- thread da interface ----------
    def pump(self):
        try:
            while True:
                msg = self.ui_q.get_nowait()
                kind = msg[0]
                if kind == "boxes":
                    self.draw(msg[1], msg[2])
                elif kind == "hide":
                    self.hide_overlay()
                    self.hidden_for_capture.set()
                elif kind == "toggle":
                    self.toggle()
                elif kind == "peek":
                    self.visible = not self.visible
                    if not self.visible:
                        self.hide_overlay()
                elif kind == "dump":
                    self.dump_screen()
                elif kind == "info":
                    self.lbl_info.config(text=msg[1])
                elif kind == "libstats":
                    self.refresh_lib_label()
                elif kind == "server":
                    _, desc, active, has_win = msg
                    self.lbl_server.config(text=f"Servidor: {desc}")
                    if not has_win:
                        st = "Hytale não encontrado"
                    elif active:
                        st = "Traduzindo (Runeteria)" if self.enabled else "Desligado"
                    else:
                        st = "Aguardando você entrar no Runeteria"
                    self.lbl_state.config(text=f"Estado: {st}")
        except queue.Empty:
            pass
        self.root.after(40, self.pump)

    def hide_overlay(self):
        if self.ov_shown:
            self.ov.withdraw()
            self.ov_shown = False

    def font(self, px, italic=False, bold=True):
        key = (px, italic, bold)
        f = self.fonts.get(key)
        if f is None:
            f = self.fonts[key] = tkfont.Font(family=self.cfg["fonte"], size=-px,
                                              weight="bold" if bold else "normal",
                                              slant="italic" if italic else "roman")
        return f

    def looks_bold(self, b, px):
        """O texto original era negrito? Compara a largura lida na tela com a da nossa fonte nos dois pesos."""
        text, width = b.get("ref", (b["en"], b["w"]))
        if text.isupper():
            return True  # rotulos em MAIUSCULAS sao quase sempre negrito, e em texto curto a medida engana
        wb = self.font(px, False, True).measure(text)
        wn = self.font(px, False, False).measure(text)
        return abs(wb - width) <= abs(wn - width)

    def draw(self, rect, boxes):
        self.last_boxes = boxes
        if not self.visible or not self.enabled:
            return
        sig = (rect, [(b["x"], b["y"], b["w"], b["h"], b["pt"], b.get("bg"), b.get("fg")) for b in boxes])
        if sig == self.drawn_sig and self.ov_shown:
            return  # nada mudou: nao redesenha (evita piscar)
        self.drawn_sig = sig
        x, y, w, h = rect
        self.ov.geometry(f"{w}x{h}+{x}+{y}")
        c = self.canvas
        c.delete("all")
        min_px = self.cfg["tamanho_fonte_min"]
        screen_colors = self.cfg["usar_cores_da_tela"]
        for b in boxes:
            auto = b["origin"] == "auto"
            if screen_colors and "bg" in b:
                # mesmas cores do texto original; traducao automatica aparece em italico
                bg, fg, italic = b["bg"], b["fg"], auto
                if bg.lower() == KEY_COLOR:
                    bg = "#ff00ff"
            else:
                bg, italic = self.cfg["opacidade_fundo"], False
                fg = self.cfg["cor_texto_auto"] if auto else self.cfg["cor_texto"]
            center = b.get("align") == "center"
            single = b.get("lines", 1) == 1
            px = max(min_px, font_px(b["ref"][0] if "ref" in b else b["en"], b["line_h"]))
            bold = self.looks_bold(b, px)
            avail = avail_width(b)  # o texto pode ocupar o fundo liso que existe ao lado do original
            if single:
                # uma linha continua uma linha: usa o espaco livre, depois diminui a letra ate 80%;
                # so quebra em duas se ainda assim nao couber
                floor = max(min_px, int(px * 0.8))
                while px > floor and self.font(px, italic, bold).measure(b["pt"]) > avail:
                    px -= 1
                wrap = avail if self.font(px, italic, bold).measure(b["pt"]) > avail else 0
            else:
                wrap = avail
            ax = b["x"] + b["w"] / 2 if center else b["x"]
            while True:
                item = c.create_text(ax, b["y"], text=b["pt"], anchor="n" if center else "nw",
                                     justify="center" if center else "left", width=wrap,
                                     font=self.font(px, italic, bold), fill=fg)
                bx = c.bbox(item)
                if single or bx[3] - bx[1] <= b["h"] * 1.2 + 2 or px <= min_px:
                    break
                c.delete(item)
                px -= 1
            # centraliza na altura do texto original (a caixa do tk inclui espaco acima/abaixo das letras)
            dy = (b["y"] + b["h"] / 2) - (bx[1] + bx[3]) / 2
            if bx[3] - bx[1] < px * 2:  # ficou em uma linha
                dy -= px * (0.15 if any(ch in DESCENDERS for ch in b["pt"]) else 0.06)
            dx = 0
            if bx[0] < 2:
                dx = 2 - bx[0]
            elif bx[2] > w - 2:
                dx = w - 2 - bx[2]
            c.move(item, dx, dy)
            bx = c.bbox(item)
            pad = 2
            r = c.create_rectangle(min(bx[0], b["x"]) - pad, min(bx[1], b["y"]) - pad,
                                   max(bx[2], b["x"] + b["w"]) + pad, max(bx[3], b["y"] + b["h"]) + pad,
                                   fill=bg, outline="")
            c.tag_lower(r, item)
        if not self.ov_shown:
            self.ov.deiconify()
            self.ov.attributes("-topmost", True)
            self.ov_shown = True

    # ---------- acoes ----------
    def toggle(self):
        self.enabled = not self.enabled
        self.btn_toggle.config(text=("Desligar" if self.enabled else "Ligar") + f" ({self.cfg['atalho_liga_desliga']})")
        if not self.enabled:
            self.hide_overlay()

    def reload_user(self):
        self.lib.reload_user_files()
        if self.mt is not None:
            self.mt.glossary = self.lib.glossary
            self.mt.terms = self.lib.terms
        self.refresh_lib_label()
        self.lbl_info.config(text="Suas traduções e glossário foram recarregados.")

    def refresh_lib_label(self):
        s = self.lib.stats()
        self.lbl_lib.config(text=f"Biblioteca: {s['revisadas']} revisadas · {s['automaticas']} automáticas · {s['suas']} suas")

    def dump_screen(self):
        done = {b["en"] for b in self.last_boxes}
        with open(SCREEN_DUMP, "w", encoding="utf-8") as f:
            f.write("Textos da última tela. Para corrigir, copie para minhas_traducoes.json no formato\n"
                    '  "Texto em ingles": "Tradução certa",\n\n')
            for b in self.last_boxes:
                f.write(f"[{b['origin']}] {b['en']}  =>  {b['pt']}\n")
            f.write("\n--- Sem tradução ---\n")
            for ln in self.last_lines:
                if ln["text"] not in done:
                    f.write(ln["text"] + "\n")
        self.lbl_info.config(text="Tela salva em ultima_tela.txt (pasta de traduções).")

    def quit(self):
        self.lib.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        import winutil
        if not winutil.single_instance("RuneteriaTradutor.instancia"):
            from tkinter import messagebox
            _r = tk.Tk()
            _r.withdraw()
            messagebox.showinfo(APP_NAME, "O Tradutor Runeteria já está aberto.")
            raise SystemExit(0)
        App().run()
    except Exception:
        log_error()
        raise
