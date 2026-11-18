"""Tradutor Runeteria - traduz as telas do servidor Runeteria (Hytale) para portugues.

So funciona quando: a janela do Hytale esta em foco E o log do jogo mostra que voce
esta dentro do play.runeteria.com. Em qualquer outro servidor ele fica desligado.
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import font as tkfont

import config
import theme as T
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
        self.ocr_error = None
        self.translator = None
        self.capture_safe = True
        self.hidden_for_capture = threading.Event()

        self.lib = Library()
        self.lock = RuneteriaLock(HYTALE_LOGS, self.cfg["servidor"])

        # ---- janela de controle (Runeteria Design System, ver theme.py) ----
        T.load_fonts(config.FONTS_DIR)
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=T.APP)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        try:
            self.root.iconbitmap(config.ICON_FILE)
        except Exception:
            pass
        self.game_state = (None, False, False)  # (descricao do servidor, ativo, janela achada)
        self.new_version = None
        self._build_window()
        if "--minimizado" in sys.argv:
            self.root.iconify()

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
        winutil.dark_titlebar(self.ctrl_hwnd)
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
        self.refresh_status()
        threading.Thread(target=self.load_models, daemon=True).start()
        threading.Thread(target=self.worker, daemon=True).start()
        if self.cfg["atualizar_pela_internet"]:
            threading.Thread(target=self.online_check, daemon=True).start()
        self.root.after(50, self.pump)

    # ---------- janela ----------
    def _build_window(self):
        root, cfg = self.root, self.cfg
        W = 440
        panel = tk.Frame(root, bg=T.PANEL, width=W)
        panel.pack(fill="both", expand=True, padx=1, pady=1)

        # cabecalho: titulo in-game (Cormorant dourado) + filete com losango
        head = tk.Frame(panel, bg=T.PANEL)
        head.pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(head, text=APP_NAME, font=T.font("title"), fg=T.GOLD_HI, bg=T.PANEL).pack(side="left")
        tk.Label(head, text=f"v{config.APP_VERSION}", font=T.font("caption"), fg=T.DISABLED, bg=T.PANEL).pack(
            side="right", anchor="s", pady=(0, 6))
        tk.Label(panel, text="As telas do Runeteria em português do Brasil", font=T.font("caption"),
                 fg=T.MUTED, bg=T.PANEL, anchor="w").pack(fill="x", padx=16)
        T.gold_divider(panel).pack(fill="x", padx=16, pady=(10, 12))

        # estado: o que o tradutor esta fazendo agora, em uma frase
        outer, box = T.card(panel)
        outer.pack(fill="x", padx=16)
        line = tk.Frame(box, bg=T.CARD)
        line.pack(fill="x", padx=12, pady=(12, 0))
        self.state_dot = tk.Canvas(line, width=12, height=12, bg=T.CARD, highlightthickness=0, bd=0)
        self.state_dot.pack(side="left", padx=(0, 8))
        self._state_oval = self.state_dot.create_oval(1, 1, 11, 11, fill=T.DISABLED, outline="")
        self.lbl_state = tk.Label(line, text="Iniciando...", font=T.font("label"), fg=T.TEXT_STRONG, bg=T.CARD)
        self.lbl_state.pack(side="left")
        self.lbl_hint = tk.Label(box, text="", font=T.font("body"), fg=T.MUTED, bg=T.CARD, anchor="w",
                                 justify="left", wraplength=W - 60)
        self.lbl_hint.pack(fill="x", padx=12, pady=(4, 12))

        self.btn_toggle = T.RButton(panel, f"Desligar ({cfg['atalho_liga_desliga']})", self.toggle,
                                    kind="secondary", height=42)
        self.btn_toggle.pack(fill="x", padx=16, pady=(10, 12))

        # o que o tradutor precisa para funcionar; cada linha diz o que falta e resolve com um botao
        outer, box = T.card(panel, "Preparação")
        outer.pack(fill="x", padx=16)
        self.row_ocr = T.StatusRow(box, "Leitor de tela")
        self.row_mt = T.StatusRow(box, "Tradutor offline")
        self.row_lib = T.StatusRow(box, "Biblioteca")
        self.row_game = T.StatusRow(box, "Hytale")
        for r in (self.row_ocr, self.row_mt, self.row_lib, self.row_game):
            r.pack(fill="x", pady=3)
        tk.Frame(box, bg=T.CARD, height=8).pack()

        outer, box = T.card(panel, "Opções")
        outer.pack(fill="x", padx=16, pady=(12, 0))
        can_auto = self.w.autostart_command() is not None
        self.tg_auto = self._option(box, "Abrir junto com o Windows",
                                    self.w.autostart_enabled() if can_auto else False, self.set_autostart)
        if not can_auto:
            self.tg_auto.set(enabled=False)  # so existe no programa instalado
        self.tg_online = self._option(box, "Buscar traduções novas na internet",
                                      cfg["atualizar_pela_internet"], self.set_online)
        tk.Frame(box, bg=T.CARD, height=8).pack()

        bar = tk.Frame(panel, bg=T.PANEL)
        bar.pack(fill="x", padx=16, pady=(12, 0))
        for i, (text, cmd) in enumerate((("Telas novas", self.run_updater_async),
                                         ("Traduções", lambda: os.startfile(USER_DIR)),
                                         ("Recarregar", self.reload_user))):
            T.RButton(bar, text, cmd, kind="secondary", height=34, small=True).grid(
                row=0, column=i, sticky="we", padx=(0 if i == 0 else 6, 0))
            bar.columnconfigure(i, weight=1, uniform="b")

        self.lbl_info = tk.Label(panel, text="", font=T.font("body"), fg=T.TEXT, bg=T.PANEL, anchor="w",
                                 justify="left", wraplength=W - 34)
        self.lbl_info.pack(fill="x", padx=16, pady=(10, 0))

        # aviso de versao nova (so aparece quando existe)
        self.update_box = tk.Frame(panel, bg=T.GOLD)
        inner = tk.Frame(self.update_box, bg=T.CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.lbl_update = tk.Label(inner, text="", font=T.font("label"), fg=T.GOLD_HI, bg=T.CARD)
        self.lbl_update.pack(side="left", padx=12, pady=8)
        b = T.RButton(inner, "Baixar", self.open_download, kind="primary", height=30, bg=T.CARD, small=True)
        b.config(width=90)
        b.pack(side="right", padx=10, pady=6)
        self.footer = tk.Label(
            panel, font=T.font("caption"), fg=T.DISABLED, bg=T.PANEL, justify="left", anchor="w",
            text=f"{cfg['atalho_liga_desliga']} liga/desliga  •  {cfg['atalho_esconder']} mostra o original  •  "
                 f"{cfg['atalho_salvar_tela']} salva a tela em texto")
        self.footer.pack(fill="x", padx=16, pady=(10, 14))

    def _option(self, parent, text, value, command):
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x", padx=12, pady=4)
        tk.Label(row, text=text, font=T.font("body"), fg=T.TEXT, bg=T.CARD).pack(side="left")
        tg = T.Toggle(row, value, command)
        tg.pack(side="right")
        return tg

    def refresh_status(self):
        """Atualiza a frase de estado e as linhas de preparacao. Sempre na thread da interface."""
        desc, active, has_win = self.game_state
        # leitor de tela (OCR do Windows)
        if self.ocr is None:
            if self.ocr_error:
                self.row_ocr.set("bad", "Não instalado")
                self.row_ocr.action("Instalar", self.install_ocr)
            else:
                self.row_ocr.set("off", "Carregando...")
        elif self.ocr.warning:
            self.row_ocr.set("warn", "Sem o inglês")
            self.row_ocr.action("Instalar", self.install_ocr)
        else:
            self.row_ocr.set("ok", "Pronto")
            self.row_ocr.action(None, None)
        # tradutor offline
        if self.translator is None:
            self.row_mt.set("off", "Carregando...")
        elif self.mt is not None and self.mt.ok:
            self.row_mt.set("ok", "Pronto")
        else:
            self.row_mt.set("warn", "Só a biblioteca")
        # jogo
        if not has_win:
            self.row_game.set("off", "Fechado")
        elif active:
            self.row_game.set("ok", "No Runeteria")
        else:
            self.row_game.set("warn", "Fora do Runeteria")
        # frase principal: o proximo passo para a pessoa
        ready = self.ocr is not None and self.translator is not None
        if not self.enabled:
            state, color, hint = "Desligado", T.DISABLED, "Aperte Ligar para voltar a traduzir."
        elif self.ocr is None and self.ocr_error:
            state, color = "Falta o leitor de tela", T.RED
            hint = "Clique em Instalar, na linha Leitor de tela, e aceite o pedido do Windows."
        elif not ready:
            state, color, hint = "Preparando...", T.YELLOW, "Carregando o tradutor. Leva alguns segundos."
        elif not has_win:
            state, color, hint = "Abra o Hytale", T.YELLOW, "O tradutor liga sozinho quando você entrar no Runeteria."
        elif not active:
            state, color = "Entre no Runeteria", T.YELLOW
            hint = "Conecte em play.runeteria.com. Em outros servidores o tradutor fica parado."
        else:
            state, color = "Traduzindo", T.GREEN
            hint = "Deixe o jogo em Janela ou Tela cheia sem borda para a tradução aparecer."
        self.state_dot.itemconfig(self._state_oval, fill=color)
        self.lbl_state.config(text=state)
        self.lbl_hint.config(text=hint)
        self.btn_toggle.set(text=("Desligar" if self.enabled else "Ligar") + f" ({self.cfg['atalho_liga_desliga']})",
                            kind="secondary" if self.enabled else "primary")

    def set_autostart(self, on):
        try:
            self.w.set_autostart(on)
        except Exception:
            log_error()
            self.tg_auto.set(value=self.w.autostart_enabled())

    def set_online(self, on):
        self.cfg["atualizar_pela_internet"] = on
        config.save_config(self.cfg)
        if on:
            threading.Thread(target=self.online_check, daemon=True).start()

    def open_download(self):
        import webbrowser
        from online import RELEASES_PAGE
        webbrowser.open(RELEASES_PAGE)

    def install_ocr(self):
        self.row_ocr.action(None, None)
        self.row_ocr.set("off", "Instalando...")
        self.lbl_info.config(text="Aceite o pedido do Windows. A instalação leva cerca de um minuto.")
        threading.Thread(target=self._install_ocr, daemon=True).start()

    def _install_ocr(self):
        self.w.install_english_ocr()
        try:
            from ocr_engine import WindowsOcr
            ocr = WindowsOcr()
            self.ocr, self.ocr_error = ocr, None
            self.ui_q.put(("info", "Leitor de tela em inglês instalado." if not ocr.warning
                           else "Não foi possível instalar o leitor em inglês. O tradutor segue com o do Windows."))
        except Exception as e:
            log_error()
            self.ocr_error = str(e)
            self.ui_q.put(("info", "Não foi possível instalar o leitor de tela."))
        self.ui_q.put(("status",))

    # ---------- internet (opcional) ----------
    def online_check(self):
        try:
            import online
            if online.sync_translations():
                self.lib.reload_seed()
                if self.mt is not None:
                    self.mt.glossary, self.mt.terms = self.lib.glossary, self.lib.terms
                self.ui_q.put(("libstats",))
                self.ui_q.put(("info", "Traduções atualizadas pela internet."))
            v = online.newer_version()
            if v:
                self.ui_q.put(("update", v))
        except Exception:
            log_error()

    # ---------- carregamento ----------
    def load_models(self):
        try:
            from mt import OfflineTranslator
            self.mt = OfflineTranslator(MODEL_DIR, self.lib.glossary, self.lib.terms)
        except Exception:
            log_error()
            self.mt = None
        self.translator = Translator(self.lib, self.mt, self.cfg)
        self.ui_q.put(("status",))
        try:
            from ocr_engine import WindowsOcr
            self.ocr = WindowsOcr()
        except Exception as e:
            log_error()
            self.ocr, self.ocr_error = None, str(e)
            self.ui_q.put(("status",))
            return
        self.ui_q.put(("status",))
        self.run_updater(quiet=True)

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
                    self.game_state = msg[1:]
                    self.refresh_status()
                elif kind == "status":
                    self.refresh_status()
                elif kind == "update":
                    self.lbl_update.config(text=f"Versão {msg[1]} disponível")
                    self.update_box.pack(fill="x", padx=16, pady=(10, 0), before=self.footer)
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
        if not self.enabled:
            self.hide_overlay()
        self.refresh_status()

    def reload_user(self):
        self.lib.reload_user_files()
        if self.mt is not None:
            self.mt.glossary = self.lib.glossary
            self.mt.terms = self.lib.terms
        self.refresh_lib_label()
        self.lbl_info.config(text="Suas traduções e glossário foram recarregados.")

    def refresh_lib_label(self):
        s = self.lib.stats()
        extra = "".join(f"  •  {n} {nome if n > 1 else nome[:-1]}"
                        for n, nome in ((s["automaticas"], "automáticas"), (s["suas"], "suas")) if n)
        self.row_lib.set("ok" if s["revisadas"] else "bad", f"{s['revisadas']:,} textos".replace(",", ".") + extra)

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
