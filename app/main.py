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
from pipeline import Translator, chat_split, tidy_lines
from style import (DESCENDERS, _rgb, add_colors, avail_width, font_px, init_faces, pick_face,
                   region_changed, region_thumb, restyle_spans, screen_diff, split_by_color)

KEY_COLOR = "#ff00fe"  # cor "invisivel" do overlay


def _overlap(a, b):
    """As duas caixas ocupam (quase) o mesmo lugar? (mais de 30% da menor)"""
    ix = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    iy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    if ix <= 0 or iy <= 0:
        return False
    return ix * iy > 0.3 * min(a["w"] * a["h"], b["w"] * b["h"])


def _contains_text(big, small):
    """As palavras de `small` aparecem todas, na ordem, em `big`, e `big` tem mais? ("1 in stock" contem
    "in stock": e a mesma linha lida por inteiro)"""
    a, b = big.lower().split(), small.lower().split()
    if len(a) <= len(b):
        return False
    it = iter(a)
    return all(w in it for w in b)


def _inside(a, b):
    """A caixa a cabe dentro da b (com folga de 2 px)?"""
    return (a["x"] >= b["x"] - 2 and a["x"] + a["w"] <= b["x"] + b["w"] + 2
            and a.get("align") == b.get("align") and a["w"] < b["w"])


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
        self.last_img = self.last_rect = None  # captura (e janela) de onde sairam as last_lines
        self.last_boxes = []
        self.drawn_sig = None
        self._faces_memo, self._faces_pruned = {}, 0.0  # fonte escolhida por texto (ver stable_face)
        self._slots, self._slot_n = [], 0  # o que esta em cada lugar da tela (ver settle)
        self._flaky = {}  # texto en -> (quando saiu da tela, ate quando fica sem traducao)
        self._scale, self._scale_for = 1.6, None  # escala do OCR (ver ocr_scale)
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
        self.game_state = (None, False, False, False)  # (descricao do servidor, ativo, janela achada, no Runeteria)
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
        init_faces(config.FONTS_DIR)  # para medir e reproduzir a fonte do jogo no overlay
        self.fallback_font = "Segoe UI" if self.cfg["fonte_overlay"] == "auto" else self.cfg["fonte_overlay"]

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
        if self.cfg["atualizar_pela_internet"] and config.FROZEN:  # pelo codigo-fonte vale o arquivo local
            threading.Thread(target=self.online_check, daemon=True).start()
        self.root.after(50, self.pump)

    # ---------- janela ----------
    def _build_window(self):
        root, cfg = self.root, self.cfg
        W = T.S(440)
        panel = tk.Frame(root, bg=T.PANEL, width=W)
        panel.pack(fill="both", expand=True, padx=1, pady=1)

        # cabecalho: logo oficial do Runeteria + "TRADUTOR" + filete com losango
        try:
            from PIL import Image, ImageTk
            logo = Image.open(config.LOGO_FILE).convert("RGBA")
            logo.thumbnail((T.S(250), T.S(96)), Image.LANCZOS)
            self._logo = ImageTk.PhotoImage(logo)  # guarda a referencia, senao o tkinter descarta a imagem
            tk.Label(panel, image=self._logo, bg=T.PANEL, bd=0).pack(pady=(T.S(14), T.S(0)))
            title = "TRADUTOR"
        except Exception:
            title = None  # sem o arquivo do logo: o nome vai escrito no titulo
            tk.Label(panel, text=APP_NAME, font=T.font("title"), fg=T.GOLD_HI, bg=T.PANEL).pack(pady=(T.S(14), T.S(0)))
        if title:
            tk.Label(panel, text=title, font=T.font("button"), fg=T.GOLD_HI, bg=T.PANEL).pack(pady=(T.S(2), T.S(0)))
        tk.Label(panel, text="As telas do jogo em português do Brasil", font=T.font("caption"),
                 fg=T.MUTED, bg=T.PANEL).pack()
        if config.APP_STAGE:
            tk.Label(panel, text="Versão de testes: algumas traduções ainda podem sair erradas",
                     font=T.font("caption"), fg=T.GOLD_HI, bg=T.PANEL).pack(pady=(T.S(2), 0))
        stage = f" {config.APP_STAGE.upper()}" if config.APP_STAGE else ""
        tk.Label(panel, text=f"v{config.APP_VERSION}{stage}", font=T.font("caption"), fg=T.DISABLED,
                 bg=T.PANEL).place(relx=1.0, x=-14, y=10, anchor="ne")
        T.gold_divider(panel).pack(fill="x", padx=T.S(16), pady=(T.S(10), T.S(12)))

        # estado: o que o tradutor esta fazendo agora, em uma frase
        outer, box = T.card(panel)
        outer.pack(fill="x", padx=T.S(16))
        line = tk.Frame(box, bg=T.CARD)
        line.pack(fill="x", padx=T.S(12), pady=(T.S(12), T.S(0)))
        self.state_dot = tk.Canvas(line, width=T.S(12), height=T.S(12), bg=T.CARD, highlightthickness=0, bd=0)
        self.state_dot.pack(side="left", padx=(T.S(0), T.S(8)))
        self._state_oval = self.state_dot.create_oval(T.S(1), T.S(1), T.S(11), T.S(11), fill=T.DISABLED, outline="")
        self.lbl_state = tk.Label(line, text="Iniciando...", font=T.font("label"), fg=T.TEXT_STRONG, bg=T.CARD)
        self.lbl_state.pack(side="left")
        self.lbl_hint = tk.Label(box, text="", font=T.font("body"), fg=T.MUTED, bg=T.CARD, anchor="w",
                                 justify="left", wraplength=W - T.S(60))
        self.lbl_hint.pack(fill="x", padx=T.S(12), pady=(T.S(4), T.S(12)))

        self.btn_toggle = T.RButton(panel, f"Desligar ({cfg['atalho_liga_desliga']})", self.toggle,
                                    kind="secondary", height=42)
        self.btn_toggle.pack(fill="x", padx=T.S(16), pady=(T.S(10), T.S(12)))

        # o que o tradutor precisa para funcionar; cada linha diz o que falta e resolve com um botao
        outer, box = T.card(panel, "Preparação")
        outer.pack(fill="x", padx=T.S(16))
        self.row_ocr = T.StatusRow(box, "Leitor de tela")
        self.row_mt = T.StatusRow(box, "Tradutor offline")
        self.row_lib = T.StatusRow(box, "Biblioteca")
        self.row_game = T.StatusRow(box, "Hytale")
        for r in (self.row_ocr, self.row_mt, self.row_lib, self.row_game):
            r.pack(fill="x", pady=T.S(3))
        tk.Frame(box, bg=T.CARD, height=T.S(8)).pack()

        outer, box = T.card(panel, "Opções")
        outer.pack(fill="x", padx=T.S(16), pady=(T.S(12), T.S(0)))
        can_auto = self.w.autostart_command() is not None
        self.tg_auto = self._option(box, "Abrir junto com o Windows",
                                    self.w.autostart_enabled() if can_auto else False, self.set_autostart)
        if not can_auto:
            self.tg_auto.set(enabled=False)  # so existe no programa instalado
        self.tg_online = self._option(box, "Buscar traduções novas na internet",
                                      cfg["atualizar_pela_internet"], self.set_online)
        if config.ONLINE_MT_URL:
            self.tg_mt = self._option(box, "Tradução online (melhor e mais rápida)",
                                      cfg.get("traducao_online", True), self.set_online_mt)
        self.tg_chat = self._option(box, "Traduzir o chat (não recomendado)",
                                    cfg.get("traduzir_chat", False), self.set_chat)
        tk.Frame(box, bg=T.CARD, height=T.S(8)).pack()

        # um botao so: baixa as traducoes corrigidas e confere se saiu versao nova do programa
        self.btn_check = T.RButton(panel, "Verificar atualizações", self.check_updates, kind="secondary", height=38)
        self.btn_check.pack(fill="x", padx=T.S(16), pady=(T.S(12), T.S(0)))

        self.lbl_info = tk.Label(panel, text="", font=T.font("body"), fg=T.TEXT, bg=T.PANEL, anchor="w",
                                 justify="left", wraplength=W - T.S(34))
        self.lbl_info.pack(fill="x", padx=T.S(16), pady=(T.S(10), T.S(0)))

        # aviso de versao nova (so aparece quando existe)
        self.update_box = tk.Frame(panel, bg=T.GOLD)
        inner = tk.Frame(self.update_box, bg=T.CARD)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.lbl_update = tk.Label(inner, text="", font=T.font("label"), fg=T.GOLD_HI, bg=T.CARD)
        self.lbl_update.pack(side="left", padx=T.S(12), pady=T.S(8))
        b = T.RButton(inner, "Atualizar", self.start_update, kind="primary", height=30, bg=T.CARD, small=True)
        b.config(width=T.S(104))
        b.pack(side="right", padx=T.S(10), pady=T.S(6))
        self.btn_update = b
        self.footer = tk.Label(
            panel, font=T.font("caption"), fg=T.DISABLED, bg=T.PANEL, justify="left", anchor="w",
            text=f"{cfg['atalho_liga_desliga']} liga/desliga  •  {cfg['atalho_esconder']} mostra o original  •  "
                 f"{cfg['atalho_salvar_tela']} salva a tela em texto")
        self.footer.pack(fill="x", padx=T.S(16), pady=(T.S(10), T.S(14)))

    def load_shared(self):
        try:
            from online_mt import load_shared
            if self.mt is not None:
                self.mt.shared = load_shared()
        except Exception:
            log_error()

    def apply_online_mt(self):
        """Liga/desliga a traducao online (o texto em ingles que nao esta na biblioteca vai para o servidor)."""
        if self.mt is None:
            return
        on = bool(config.ONLINE_MT_URL) and self.cfg.get("traducao_online", True)
        if on and self.mt.online is None:
            from online_mt import OnlineMT
            self.mt.online = OnlineMT(config.ONLINE_MT_URL)
        elif not on:
            self.mt.online = None

    def set_chat(self, value):
        self.cfg["traduzir_chat"] = bool(value)  # o laco de captura e o Translator leem do mesmo cfg
        config.save_config(self.cfg)
        # nao recomendado: o chat sobe o tempo todo e so da para traduzir a mensagem em que o mouse esta
        self.lbl_info.config(text="Chat: a tradução é parcial. Abra o chat e passe o mouse em cima de uma mensagem "
                                  "para traduzir só ela. Como o chat sobe o tempo todo, nem tudo é traduzido."
                             if value else "")

    def set_online_mt(self, value):
        self.cfg["traducao_online"] = bool(value)
        config.save_config(self.cfg)
        self.apply_online_mt()

    def _option(self, parent, text, value, command):
        row = tk.Frame(parent, bg=T.CARD)
        row.pack(fill="x", padx=T.S(12), pady=T.S(4))
        tk.Label(row, text=text, font=T.font("body"), fg=T.TEXT, bg=T.CARD).pack(side="left")
        tg = T.Toggle(row, value, command)
        tg.pack(side="right")
        return tg

    def refresh_status(self):
        """Atualiza a frase de estado e as linhas de preparacao. Sempre na thread da interface."""
        desc, active, has_win, in_rt = self.game_state
        # leitor de tela (OCR do Windows)
        if getattr(self, "_ocr_since", None) is not None:
            pass  # instalando: a linha mostra o contador (_ocr_tick); o botao Instalar nao volta no meio
        elif self.ocr is None:
            if self.ocr_error:
                self.row_ocr.set("bad", "Não instalado")
                self.row_ocr.action(*(("Abrir", self.ocr_by_settings) if getattr(self, "ocr_failed", False)
                                      else ("Instalar", self.install_ocr)))
            else:
                self.row_ocr.set("off", "Carregando...")
        elif self.ocr.warning:
            self.row_ocr.set("warn", "Sem o inglês")
            self.row_ocr.action(*(("Abrir", self.ocr_by_settings) if getattr(self, "ocr_failed", False)
                                  else ("Instalar", self.install_ocr)))
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
        elif in_rt:
            self.row_game.set("ok", "No Runeteria")
        elif active:
            self.row_game.set("ok", "Aberto")
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
            state, color, hint = "Abra o Hytale", T.YELLOW, "O tradutor liga sozinho quando o jogo abrir."
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

    # ---------- atualizar o programa sem sair dele ----------
    def start_update(self):
        """Botao "Atualizar": baixa o instalador da versao nova, instala por cima e reabre o tradutor.
        Rodando pelo codigo-fonte nao ha o que instalar: abre a pagina de download."""
        if not config.FROZEN:
            self.open_download()
            return
        self.btn_update.set(text="Baixando...", enabled=False)
        threading.Thread(target=self._download_update, daemon=True).start()

    def _download_update(self):
        try:
            import online
            info = online.latest_installer()
            if not info:
                raise OSError("sem instalador na ultima versao")
            self.ui_q.put(("info", f"Baixando a versão {info['version']}... 0%"))
            path = online.download_installer(
                info, lambda p: self.ui_q.put(("info", f"Baixando a versão {info['version']}... {p}%")))
            self.ui_q.put(("install", path))
        except Exception:
            log_error()
            self.ui_q.put(("update_failed",))

    def install_update(self, installer):
        """Fecha o tradutor, roda o instalador sem perguntas (ele mostra so a barra de progresso) e abre o
        tradutor de novo. Quem faz isso e um script a parte, porque o programa nao pode se trocar aberto."""
        import subprocess
        import tempfile
        script = os.path.join(tempfile.gettempdir(), "TradutorRuneteria-Atualizar.cmd")
        try:
            with open(script, "w", encoding="utf-8", newline="\r\n") as f:
                f.write("@echo off\n"
                        "chcp 65001 >nul\n"
                        "ping -n 3 127.0.0.1 >nul\n"                      # espera o tradutor fechar
                        f'"{installer}" /SILENT /SUPPRESSMSGBOXES /NORESTART\n'
                        f'start "" "{sys.executable}"\n'
                        f'del "{installer}" >nul 2>nul\n'
                        'del "%~f0" >nul 2>nul\n')
            subprocess.Popen(["cmd", "/c", script], close_fds=True,
                             creationflags=0x08000000 | 0x00000200)   # sem janela, grupo proprio
        except Exception:
            log_error()
            self.ui_q.put(("update_failed",))
            return False
        self.quit()
        return True

    def install_ocr(self):
        self.row_ocr.action(None, None)
        self.row_ocr.set("off", "Instalando...")
        self.lbl_info.config(text="Aceite o pedido do Windows para começar.")
        self._ocr_since = time.monotonic()
        threading.Thread(target=self._install_ocr, daemon=True).start()
        self.root.after(1000, self._ocr_tick)

    def _ocr_tick(self):
        """Enquanto o Windows instala o leitor: mostra ha quanto tempo esta instalando. Quem faz a instalacao
        e o Windows (baixa pelo Windows Update) e nao da para apressar; sem um contador parecia travado."""
        since = getattr(self, "_ocr_since", None)
        if since is None:
            return
        t = int(time.monotonic() - since)
        clock = f"{t // 60}:{t % 60:02d}"
        self.row_ocr.set("off", f"Instalando... {clock}")
        if t < 300:
            msg = ("O Windows está baixando e instalando o leitor de tela. Costuma levar de 1 a 5 minutos, "
                   "depende da sua internet. Pode usar o computador enquanto isso; o tradutor avisa quando terminar.")
        else:
            msg = ("Está demorando mais que o normal, mas o Windows ainda está instalando. Deixe o tradutor aberto. "
                   "Se passar de 15 minutos ele mesmo mostra outro jeito de instalar.")
        self.lbl_info.config(text=msg)
        self.root.after(1000, self._ocr_tick)

    def _install_ocr(self):
        try:
            code = self.w.install_english_ocr(os.path.join(config.USER_DIR, "instalar_leitor.log"))
        finally:
            self._ocr_since = None  # para o contador
        try:
            from ocr_engine import WindowsOcr
            ocr = WindowsOcr()
            if not ocr.warning:
                self.ocr, self.ocr_error = ocr, None
                self.ui_q.put(("info", "Leitor de tela em inglês instalado."))
            elif self.w.english_ocr_files():
                # instalou, mas o Windows so mostra o leitor novo para programas abertos depois
                self.ui_q.put(("info", "Leitor instalado. Reabrindo o tradutor..."))
                self.ui_q.put(("restart",))
                return
            elif code == 1223:
                self.ui_q.put(("info", "O pedido do Windows foi recusado. Clique em Instalar para tentar de novo."))
            else:
                self.ui_q.put(("ocr_failed",))
        except Exception as e:
            log_error()
            self.ocr_error = str(e)
            if self.w.english_ocr_files():
                self.ui_q.put(("restart",))
                return
            self.ui_q.put(("ocr_failed",))
        self.ui_q.put(("status",))

    def ocr_by_settings(self):
        """Plano B quando a instalacao automatica falha (Windows Update bloqueado, PC da empresa...):
        instalar o idioma ingles pelas Configuracoes tambem instala o leitor."""
        self.w.open_language_settings()
        self.lbl_info.config(text="Na tela que abriu, clique em Adicionar um idioma, escolha English (United States) "
                                  "e instale. Depois feche e abra o tradutor de novo.")

    def restart(self):
        """Abre o tradutor de novo (o leitor recem-instalado so aparece para programas abertos depois)."""
        import subprocess
        args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
        try:
            subprocess.Popen(args + ["--reiniciar"], close_fds=True)
        except Exception:
            log_error()
            return
        self.quit()

    def check_updates(self):
        """Botao "Verificar atualizacoes": traducoes novas do repositorio + versao nova do programa.
        Tambem recarrega as correcoes do usuario e procura telas novas no cache do jogo."""
        self.btn_check.set(text="Verificando...", enabled=False)
        self.lbl_info.config(text="")
        threading.Thread(target=self._check_updates, daemon=True).start()

    def _check_updates(self):
        msg = ""
        try:
            import online
            self.lib.reload_user_files()
            got = online.sync_translations() if config.FROZEN else False
            if got:
                self.lib.reload_seed()
                self.load_shared()
            if self.mt is not None:
                self.mt.glossary, self.mt.terms = self.lib.glossary, self.lib.terms
            v = online.newer_version()
            if v:
                self.ui_q.put(("update", v))
                msg = f"Saiu a versão {v} do programa. Clique em Atualizar: ele baixa e instala sozinho."
            elif online.reachable():
                msg = "Traduções atualizadas." if got else "Você já tem as traduções mais recentes."
            else:
                msg = "Sem conexão com a internet. Tente de novo mais tarde."
            self.run_updater(quiet=True)
        except Exception:
            log_error()
            msg = "Não foi possível verificar agora. Tente de novo mais tarde."
        self.ui_q.put(("libstats",))
        self.ui_q.put(("info", msg))
        self.ui_q.put(("checked",))

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
            self.apply_online_mt()
            self.load_shared()
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
        """Loop de captura.

        Roda a cada ~0,1 s, mas o OCR (caro) so roda quando precisa:
        - a cada passada, confere so a regiao de cada traducao na tela: se o jogo trocou o texto ali
          (mudou de menu, fechou a janela), aquela traducao sai NA HORA, sem esperar o OCR;
        - quando a tela muda de verdade, o OCR roda assim que ela para de mudar (fim da animacao);
        - fora isso, uma releitura a cada "intervalo_segundos" pega textos novos e traducoes prontas.
        """
        import mss
        from PIL import Image
        sct = (getattr(mss, "MSS", None) or mss.mss)()  # mss 10 renomeou mss.mss para mss.MSS
        TICK = 0.15          # segundos entre capturas (cada passada sem OCR custa ~20 ms)
        BIG = 4.0            # diferenca media da tela que conta como "mudou de verdade"
        STABLE = 2.5         # abaixo disso entre duas capturas seguidas = parou de mudar
        MAX_WAIT = 0.5       # traducao tirada da tela e animacao longa: le assim mesmo depois disso
        MIN_GAP = 0.3        # nunca dois OCRs em menos que isso
        hwnd, hwnd_time = None, 0
        last_status = None
        hidden = False
        was_active = False
        prev_sig = ocr_sig = None
        last_ocr = 0.0
        urgent_since = None  # quando a tela mudou e ainda nao foi relida
        removed = False      # tirou traducao da tela e ainda nao releu (ai a pressa e maior)
        last_rect = None
        ocr_pass = 0
        window_grab = None   # None = ainda nao testou; True = le so a janela do jogo; False = le a tela
        cap = None           # captura pelo Windows Graphics Capture (captura.py); None = nao aberta
        cap_ok = self.cfg.get("captura", "auto") in ("auto", "wgc") and hasattr(self.w, "open_capture")
        cap_last = None      # ultimo quadro: com a tela parada o Windows nao manda outro, vale este
        cap_tries = 0
        grab_tries = 0       # a primeira imagem pode vir preta (tela de carregamento): tenta algumas vezes
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(1)  # o OCR roda aqui; a conferencia rapida continua enquanto ele le
        job = None           # (leitura em andamento, imagem lida, janela)
        resume = False       # o jogo voltou ao foco: redesenha na hora o que continua valendo
        last_ptr = None      # cursor na ultima conferencia (chat: traduz a mensagem sob o mouse)
        ptr_dirty = False    # o cursor mudou e as caixas ainda nao foram remontadas
        while True:
            time.sleep(TICK)
            try:
                self.lib.save(force=False)  # grava a memoria automatica aos poucos (no maximo a cada 10 s)
                if not hwnd or time.time() - hwnd_time > 3:
                    hwnd, hwnd_time = self.w.find_hytale_window(), time.time()
                # o tradutor funciona com o jogo aberto, em qualquer lugar: a conferencia "esta no Runeteria"
                # (pelo log do Hytale) deixava gente de fora quando o log nao era achado ou lido. Ela so volta
                # com "so_no_runeteria": true no config.json; aqui serve para a janela e para procurar telas novas
                in_rt = self.lock.active()
                active = in_rt or not self.cfg.get("so_no_runeteria", False)
                status = ("server", self.lock.describe(), active, bool(hwnd), in_rt)
                if (status, self.enabled) != last_status:  # so mexe na interface quando algo muda
                    self.ui_q.put(status)
                    last_status = (status, self.enabled)
                if in_rt and not was_active:
                    self.run_updater_async()  # acabou de entrar: confere se veio tela nova
                was_active = in_rt
                if not self.enabled or self.translator is None or self.ocr is None or \
                        not hwnd or not active or self.w.is_minimized(hwnd) or \
                        not self.w.is_foreground(hwnd, (self.ov_hwnd,)):
                    # so com o JOGO em foco: com outra janela na frente (Discord, navegador) a captura
                    # pegaria o texto dela e mandaria para a traducao automatica
                    if not hidden:
                        self.ui_q.put(("hide",))
                        hidden = True
                    prev_sig = None
                    if not (self.enabled and active and hwnd):
                        self._slots, ocr_sig = [], None
                    else:
                        resume = bool(self._slots)  # so perdeu o foco (Alt+Tab): guarda o que estava na tela
                    if job:
                        job[0].cancel()
                        job = None
                    continue
                hidden = False
                self.game_hwnd = hwnd
                rect = self.w.client_rect(hwnd)
                if not rect:
                    continue
                x, y, w, h = rect
                if rect != last_rect:  # janela mexeu ou mudou de tamanho: tudo que esta desenhado vale menos
                    self._slots, ocr_sig, last_rect = [], None, rect
                    urgent_since = urgent_since or time.monotonic()
                now = time.monotonic()
                periodic = now - last_ocr >= self.cfg["intervalo_segundos"]
                if not self.capture_safe:
                    # Windows antigo: o overlay aparece na captura, entao tem que sumir antes de capturar.
                    # Nesse caso nao da para fazer a conferencia rapida; fica so a releitura periodica.
                    if not periodic:
                        continue
                    if self.ov_shown:
                        self.hidden_for_capture.clear()
                        self.ui_q.put(("hide",))
                        self.hidden_for_capture.wait(0.4)
                        time.sleep(0.03)
                img = None
                if cap_ok:
                    # 1a escolha: o quadro que a placa de video ja desenhou (mais leve, e de graca com a tela
                    # parada). Qualquer problema - Windows antigo, quadro preto, erro - desliga e segue com
                    # os metodos de sempre, sem o jogador perceber
                    try:
                        if cap is None or cap.hwnd != hwnd:
                            if cap is not None:
                                cap.close()
                            cap, cap_last, cap_tries = self.w.open_capture(hwnd), None, 0
                        img = cap.grab(w, h)
                        if img is not None and cap_last is None:
                            lo, hi = img.convert("L").reduce(16).getextrema()
                            if hi - lo < 12:
                                img = None  # preto: tela de carregamento, ou este PC nao entrega a janela assim
                        if img is not None:
                            if cap_last is None and window_grab is not True:
                                window_grab = True  # le so a janela: o overlay pode aparecer em gravacoes
                                self.ui_q.put(("recordable", self.cfg.get("permitir_gravar", True)))
                            cap_last = img
                        elif cap_last is not None and cap_last.size == (w, h):
                            img = cap_last  # tela parada
                        else:
                            cap_tries += 1
                            if cap_tries >= 20:  # ~3 s sem um quadro que preste: desiste deste metodo
                                raise OSError("sem quadro do Windows Graphics Capture")
                    except Exception:
                        log_error()
                        cap_ok, img = False, None
                        if cap is not None:
                            cap.close()
                        cap = None
                if img is None and window_grab is not False:
                    # le so a janela do jogo: o overlay fica de fora sem precisar ser escondido das
                    # capturas, e o jogador consegue gravar video/transmitir com a traducao aparecendo
                    try:
                        img = self.w.grab_window(hwnd, w, h)
                    except Exception:
                        img = None
                    if img is not None and window_grab is None:
                        lo, hi = img.convert("L").reduce(16).getextrema()
                        if hi - lo < 12:
                            img = None  # veio preta/vazia: pode ser tela de carregamento ou PC sem suporte
                        else:
                            window_grab = True
                            self.ui_q.put(("recordable", self.cfg.get("permitir_gravar", True)))
                    if img is None and window_grab is None:
                        grab_tries += 1
                        if grab_tries >= 20:  # ~3 s sempre preta: este PC nao suporta, fica com a captura da tela
                            window_grab = False
                    elif img is None:
                        continue  # falha momentanea: tenta de novo no proximo ciclo
                if img is None:
                    shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                sig = img.reduce(20).convert("L")  # assinatura da tela inteira (~1 ms)

                # 1) conferencia rapida: tira na hora o que ficou em cima de texto que ja nao existe
                if self._slots and self.capture_safe:
                    left = self.drop_changed(img)
                    if left is not None:
                        self.ui_q.put(("boxes", rect, left))
                        urgent_since, removed = urgent_since or now, True
                    elif resume:
                        self.ui_q.put(("boxes", rect, [sl["box"] for sl in self._slots]))
                resume = False

                # cursor: com o chat aberto o mouse aparece; a mensagem embaixo dele e traduzida. Mexeu de
                # mensagem (ou abriu/fechou o chat): remonta as caixas da ultima leitura, sem OCR (~10 ms)
                # o cursor e lido sempre (sem ele o tradutor sabe que nao ha menu aberto e ignora a regiao do
                # chat); a opcao "traduzir_chat" so decide se a mensagem sob o mouse e traduzida
                cur = self.w.cursor_pos()
                chat_on = bool(self.cfg.get("traduzir_chat", False))
                ptr = (cur[0] - x, cur[1] - y) if cur and 0 <= cur[0] - x < w and 0 <= cur[1] - y < h else None
                self.translator.pointer = ptr
                self.translator.view = (w, h)
                ptr_moved = (ptr is None) != (last_ptr is None) or (
                    chat_on and ptr and last_ptr and abs(ptr[0] - last_ptr[0]) + abs(ptr[1] - last_ptr[1]) > 6)
                if ptr_moved:
                    last_ptr, ptr_dirty = ptr, True

                # leitura que terminou: so entra o que nao mudou na tela enquanto o OCR lia
                if job and job[0].done():
                    fut, jimg, jrect = job
                    job = None
                    boxes = None
                    try:
                        boxes = fut.result()
                    except Exception:
                        log_error()
                    if boxes is not None and jrect == rect:
                        boxes = [b for b in boxes
                                 if not region_changed(img, region_thumb(jimg, b["x"], b["y"], b["w"], b["h"]))]
                        if not self.capture_safe:
                            self._slots = []  # Windows antigo: sem conferencia de regiao, vale so a leitura nova
                        self.ui_q.put(("boxes", rect, self.settle(img, boxes)))

                # 2) quando reler a tela
                moving = screen_diff(sig, prev_sig)
                prev_sig = sig
                if screen_diff(sig, ocr_sig) > BIG:
                    urgent_since = urgent_since or now
                if urgent_since is not None:
                    # le quando a tela parar de mexer. Se so o cenario 3D esta se mexendo (andando pelo
                    # mundo, sem menu), nao para nunca: ai fica na releitura periodica de sempre, para nao
                    # gastar processador; com traducao recem tirada da tela, le de qualquer jeito em 0,5 s
                    due = moving < STABLE or (removed and now - urgent_since >= MAX_WAIT) or periodic
                else:
                    due = periodic
                if ptr_dirty and job is None and self.last_lines and self.last_img is not None and not due:
                    # as linhas sao da ULTIMA LEITURA, que pode ser de uma tela que ja trocou: o resultado e
                    # conferido contra a captura daquela leitura (nao a de agora), senao a traducao da tela
                    # antiga era desenhada em cima da tela nova e ficava la ate o jogo mexer naquele lugar
                    job = (pool.submit(self.translator.boxes, self.last_lines), self.last_img, self.last_rect)
                    ptr_dirty = False
                    continue
                due = due and now - last_ocr >= MIN_GAP and job is None
                if not due:
                    continue

                if urgent_since is None and screen_diff(sig, ocr_sig) == 0 and self.last_lines:
                    lines = self.last_lines
                    fut = pool.submit(self.translator.boxes, lines)  # traducoes que acabaram de ficar prontas
                    job = (fut, self.last_img if self.last_img is not None else img, self.last_rect or rect)
                else:
                    # escala alternada: cada escala acha textos que a outra perde; somando as leituras
                    # (as traducoes ficam enquanto a regiao nao muda) a tela converge para o que as duas acham
                    ocr_pass += 1
                    fut = pool.submit(self.read_screen, img, w, h, self.ocr_scale(w, h) * (1.2 if ocr_pass % 2 else 1.0),
                                      rect)
                    ocr_sig = sig
                    job = (fut, img, rect)
                ptr_dirty = False  # a leitura ja usa o cursor de agora
                last_ocr, urgent_since, removed = now, None, False
            except Exception:
                log_error()
                time.sleep(2)

    def read_screen(self, img, w, h, scale, rect=None):
        """Le a tela e monta as traducoes (roda fora do laco de captura)."""
        lines = tidy_lines(self.ocr.recognize(img, scale))
        self.learn_text_size(lines, w, h)
        if self.cfg["usar_cores_da_tela"]:
            lines = add_colors(img, split_by_color(img, lines))
        self.last_lines, self.last_img, self.last_rect = lines, img, rect
        boxes = self.translator.boxes(lines)
        if self.cfg["usar_cores_da_tela"]:
            restyle_spans(img, boxes)
        return boxes

    # ---------- resolucao ----------
    def ocr_scale(self, w, h):
        """Escala do OCR: fixa no config.json, ou "auto" (acompanha a altura do texto da tela)."""
        fixed = self.cfg.get("escala_ocr", "auto")
        if isinstance(fixed, (int, float)) and not isinstance(fixed, bool):
            return float(fixed)
        if self._scale_for != (w, h):  # janela mudou de tamanho: recomeca pela estimativa
            from ocr_engine import initial_scale
            self._scale, self._scale_for = initial_scale(h), (w, h)
        return self._scale

    def learn_text_size(self, lines, w, h):
        """Depois de cada leitura, ajusta a escala pela altura mediana do texto (suave, sem pular)."""
        if len(lines) < 4 or self.cfg.get("escala_ocr", "auto") != "auto":
            return
        from ocr_engine import auto_scale
        hs = sorted(l["h"] for l in lines)
        want = auto_scale(hs[len(hs) // 2], w, h)
        self._scale = round(self._scale * 0.6 + want * 0.4, 2)

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
                elif kind == "restart":
                    self.restart()
                    return
                elif kind == "ocr_failed":
                    self.ocr_failed = True
                    self.ocr_by_settings()
                    self.refresh_status()
                elif kind == "recordable":
                    # o OCR le so a janela do jogo: o overlay pode aparecer em gravacoes e transmissoes
                    self.capture_safe = True
                    if msg[1]:
                        winutil.exclude_from_capture(self.ov_hwnd, on=False)
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
                elif kind == "checked":
                    self.btn_check.set(text="Verificar atualizações", enabled=True)
                elif kind == "install":
                    self.lbl_info.config(text="Instalando a versão nova. O tradutor vai fechar e abrir de novo.")
                    self.root.update_idletasks()
                    if self.install_update(msg[1]):
                        return  # a janela ja foi fechada
                elif kind == "update_failed":
                    self.btn_update.set(text="Atualizar", enabled=True)
                    self.lbl_info.config(text="Não deu para baixar a versão nova agora. Abri a página de download: "
                                              "baixe o instalador por lá e instale por cima.")
                    self.open_download()
                elif kind == "update":
                    self.lbl_update.config(text=f"Versão {msg[1]} disponível")
                    self.update_box.pack(fill="x", padx=T.S(16), pady=(T.S(10), 0), before=self.footer)
        except queue.Empty:
            pass
        try:
            gh = getattr(self, "game_hwnd", None)
            if self.ov_shown and gh and not self.w.is_foreground(gh, (self.ov_hwnd,)):
                self.hide_overlay()  # Alt+Tab: nao espera a leitura em andamento terminar
        except Exception:
            pass
        self.root.after(40, self.pump)

    def hide_overlay(self):
        if self.ov_shown:
            self.ov.withdraw()
            self.ov_shown = False

    def font(self, px, italic=False, bold=True, family=None, weight=None):
        """Fonte do overlay. family/weight vem de style.pick_face; sem eles usa a fonte de reserva."""
        key = (px, italic, bold, family, weight)
        f = self.fonts.get(key)
        if f is None:
            f = self.fonts[key] = tkfont.Font(family=family or self.fallback_font, size=-px,
                                              weight=weight or ("bold" if bold else "normal"),
                                              slant="italic" if italic else "roman")
        return f

    def looks_bold(self, b, px):
        """(reserva, sem os arquivos de fonte) O original era negrito? Compara larguras nos dois pesos."""
        text, width = b.get("ref", (b["en"], b["w"]))
        if text.isupper():
            return True  # rotulos em MAIUSCULAS sao quase sempre negrito, e em texto curto a medida engana
        wb = self.font(px, False, True).measure(text)
        wn = self.font(px, False, False).measure(text)
        return abs(wb - width) <= abs(wn - width)

    def settle(self, img, boxes):
        """Decide o que fica na tela depois de uma leitura. Devolve as caixas a desenhar.

        Regra: cada LUGAR da tela guarda a traducao que esta nele, e ela so muda quando os pixels do jogo
        naquele lugar mudam. O OCR le a mesma tela parada de jeitos diferentes a cada passada ("1 in stock",
        depois so "in stock"; "1 of 26" / "I of 26"; a caixa um pouco mais larga ou mais estreita), e antes
        cada variacao redesenhava a traducao: texto, posicao, fonte e cor ficavam trocando sem parar.
        Agora a leitura nova so substitui a que esta no lugar se:
        - for uma leitura mais completa (contem a atual e mais texto), ou
        - for a mesma traducao numa caixa bem menor, dentro da atual (a atual tinha pegado o icone), ou
        - discordar da atual 3 leituras seguidas (a primeira e que estava errada).
        """
        slots = [sl for sl in self._slots if not region_changed(img, sl["thumb"])]
        self._note_drops([sl for sl in self._slots if sl not in slots])
        # chat: a traducao some quando o mouse sai da mensagem (a leitura nova nao a traz mais)
        slots = [sl for sl in slots if not sl["box"].get("chat")
                 or any(b.get("chat") and _overlap(b, sl["box"])
                        and abs(b["y"] - sl["box"]["y"]) < sl["box"].get("line_h", b["h"]) * 0.5 for b in boxes)]
        used = set()
        now = time.monotonic()
        for b in boxes:
            sl = next((x for x in slots if id(x) not in used and _overlap(x["box"], b)), None)
            if sl is None:
                if self._flaky.get(b["en"], (0, 0))[1] > now:
                    continue  # some e volta sem parar (texto no cenario com a camera mexendo): fica o original
                self._slot_n += 1
                nb = dict(b)
                nb["_slot"] = self._slot_n
                sl = {"box": nb, "thumb": region_thumb(img, b["x"], b["y"], b["w"], b["h"]), "cand": None, "n": 0,
                      "born": now}
                slots.append(sl)
                used.add(id(sl))
                continue
            used.add(id(sl))
            cur = sl["box"]
            replace = False
            if b["pt"] == cur["pt"]:
                sl["cand"], sl["n"] = None, 0
                replace = _inside(b, cur) and b["w"] < cur["w"] * 0.92
            elif _contains_text(b["en"], cur["en"]):
                replace = True
            elif not _contains_text(cur["en"], b["en"]):
                if sl["cand"] == b["pt"]:
                    sl["n"] += 1
                else:
                    sl["cand"], sl["n"] = b["pt"], 1
                replace = sl["n"] >= 3
            if replace:
                nb = dict(b)
                if b["pt"] != cur["pt"]:
                    self._slot_n += 1  # outro texto: fonte e cor sao escolhidas de novo
                    nb["_slot"] = self._slot_n
                else:
                    nb["_slot"] = cur["_slot"]
                sl.update(box=nb, thumb=region_thumb(img, b["x"], b["y"], b["w"], b["h"]), cand=None, n=0)
        # paragrafo e pedaco dele ao mesmo tempo (o leitor ora junta as linhas, ora nao): fica o maior. Sem isto
        # a linha solta continuava desenhada por cima do paragrafo ("... para ver se e" + "Alface em cima.")
        def area(sl):
            return sl["box"]["w"] * sl["box"]["h"]

        def swallowed(sl):
            a = sl["box"]
            for o in slots:
                b = o["box"]
                if o is sl or area(o) <= area(sl) * 1.3 or b.get("lines", 1) < 2:
                    continue
                ix = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
                iy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
                if ix > 0 and iy > 0 and ix * iy >= area(sl) * 0.7:
                    return True
            return False
        slots = [sl for sl in slots if not swallowed(sl)]
        self._slots = slots
        return [sl["box"] for sl in slots]

    def drop_changed(self, img):
        """Conferencia rapida entre leituras: tira os lugares cujo texto do jogo mudou. Devolve as caixas
        que continuam, ou None se nada mudou."""
        keep = [sl for sl in self._slots if not region_changed(img, sl["thumb"])]
        if len(keep) == len(self._slots):
            return None
        self._note_drops([sl for sl in self._slots if sl not in keep])
        if len(keep) <= len(self._slots) * 0.4:
            keep = []  # a maioria mudou de uma vez: o menu fechou ou trocou inteiro
        self._slots = keep
        return [sl["box"] for sl in keep]

    def _note_drops(self, gone):
        """Traducao que sai da tela pouco depois de aparecer, 3 vezes em 20 s, e texto em cima do cenario
        3D (estacao de refino, nome sobre a cabeca): com a camera mexendo ele piscava entre as duas linguas.
        Esse texto fica sem traducao por 30 s."""
        now = time.monotonic()
        for sl in gone:
            if now - sl.get("born", 0) > 2.5:
                continue
            en = sl["box"]["en"]
            if chat_split(en):
                continue  # chat: cada mensagem nova empurra as linhas para cima, nao e texto piscando
            times = [t for t in self._flaky.get(en, ([], 0))[0] if now - t < 20] + [now]
            self._flaky[en] = (times, now + 30 if len(times) >= 3 else 0)
        if len(self._flaky) > 500:
            self._flaky = {k: v for k, v in self._flaky.items() if v[1] > now or v[0][-1] > now - 20}

    def _memo(self, b):
        now = time.monotonic()
        memo = self._faces_memo
        if len(memo) > 3000 or now - self._faces_pruned > 30:
            for k in [k for k, v in memo.items() if now - v["seen"] > 30]:
                del memo[k]
            self._faces_pruned = now
        key = b.get("_slot") or (b["en"], round(b["x"] / 8), round(b["y"] / 8))  # por lugar da tela
        rec = memo.get(key)
        if rec is None:
            rec = memo[key] = {"votes": {}, "faces": {}, "px": {}, "colors": {}, "seen": now}
        rec["seen"] = now
        return rec

    def stable_colors(self, b):
        """Mesmas cores para o mesmo texto no mesmo lugar: a cor lida varia entre leituras (e, com contraste
        fraco, chegava a virar branco numa leitura e cinza na outra - parecia trocar de normal para negrito)."""
        rec = self._memo(b)
        pair = (b["bg"], b["fg"])
        q = tuple(c[:2] + c[3:4] + c[5:6] for c in pair)  # agrupa cores quase iguais
        votes = rec["colors"]
        if q not in votes:
            votes[q] = [0, pair]
        votes[q][0] += 1
        return max(votes.values(), key=lambda v: v[0])[1]  # empate: a primeira vista

    def stable_face(self, b, face):
        """Mesma fonte para o mesmo texto no mesmo lugar, leitura apos leitura.

        Cada leitura do OCR mede as letras um pouco diferente (as escalas se alternam), e em texto curto
        isso basta para a escolha virar entre Lexend/Inter, normal/negrito ou 11/12 px: a tela parada
        ficava piscando. Aqui cada texto guarda as escolhas ja feitas e usa a mais votada (e o tamanho
        mais votado): a decisao se firma em poucas leituras e nao oscila mais.
        """
        if face is None:
            return None
        rec = self._memo(b)
        fam = (face["family"], face["weight"])
        rec["votes"][fam] = rec["votes"].get(fam, 0) + 1
        rec["faces"][fam] = face
        rec["px"][face["px"]] = rec["px"].get(face["px"], 0) + 1
        best = max(rec["votes"].items(), key=lambda kv: kv[1])[0]  # empate: fica a primeira escolha
        chosen = dict(rec["faces"][best])
        chosen["px"] = max(rec["px"].items(), key=lambda kv: kv[1])[0]  # tamanho mais votado; empate: o primeiro
        return chosen

    def draw_tracked(self, c, ax, y, text, fnt, fill, track, align):
        """Desenha o texto letra por letra com `track` pixels a mais entre elas (o tkinter nao tem
        espacamento entre letras). Devolve (tag dos itens, caixa)."""
        total = fnt.measure(text) + track * (len(text) - 1)
        x = {"center": ax - total / 2, "right": ax - total}.get(align, ax)
        self._tag_n = getattr(self, "_tag_n", 0) + 1
        tag = f"t{self._tag_n}"
        x0 = x
        for i, ch in enumerate(text):
            if ch != " ":
                # posicao natural da letra dentro da palavra (medindo ate ela, o ajuste entre pares como
                # "PA" entra na conta; medindo so o que vem antes, abria um buraco: "ETAP AS")
                pos = fnt.measure(text[:i + 1]) - fnt.measure(ch)
                c.create_text(round(x0 + pos + track * i), y, text=ch, anchor="nw", font=fnt, fill=fill, tags=tag)
        return tag, (x, y, x + total, y + fnt.metrics("linespace"))

    def draw(self, rect, boxes):
        self.last_boxes = boxes
        if os.environ.get("RT_LOG_BOXES"):  # diagnostico: registra o que e desenhado (nao usado pelo usuario)
            try:
                import json
                with open(os.environ["RT_LOG_BOXES"], "a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": time.time(), "boxes": [
                        {k: b.get(k) for k in ("pt", "en", "x", "y", "w", "h", "align")} for b in boxes]},
                        ensure_ascii=False) + "\n")
            except Exception:
                pass
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
        auto_font = self.cfg["fonte_overlay"] == "auto"
        todo = list(boxes)
        while todo:
            b = todo.pop(0)
            auto = b["origin"] == "auto"
            if screen_colors and "bg" in b:
                # mesmas cores do texto original; traducao automatica aparece em italico
                bg, fg = self.stable_colors(b)
                italic = auto
                if bg.lower() == KEY_COLOR:
                    bg = "#ff00ff"
            else:
                bg, italic = self.cfg["opacidade_fundo"], False
                fg = self.cfg["cor_texto_auto"] if auto else self.cfg["cor_texto"]
            align = b.get("align", "left")
            single = b.get("lines", 1) == 1
            ref_text, ref_w = b.get("ref", (b["en"], b["w"]))
            ink_y, ink_h = b.get("iy", b["y"]), b.get("ih", b["line_h"])
            # mesma fonte, peso e tamanho do original (medidos com os arquivos de fonte do jogo)
            face = None
            if auto_font:
                like = None
                if b.get("line_ref"):
                    lf = pick_face(*b["line_ref"])
                    like = lf["family"].split()[0] if lf else None
                face = self.stable_face(b, pick_face(ref_text, ref_w, ink_h, b.get("ink"), like))
            if face:
                px = max(min_px, face["px"])
                fkw = {"family": face["family"], "weight": face["weight"]}
            else:
                px = max(min_px, font_px(ref_text, b["line_h"]))
                fkw = {"bold": self.looks_bold(b, px)}
            px0 = px
            avail = avail_width(b)  # o texto pode ocupar o fundo liso que existe ao lado do original
            track = face["track"] if face and single else 0
            n_gaps = max(len(b["pt"]) - 1, 0)

            def width_of(size, tr):
                return self.font(size, italic, **fkw).measure(b["pt"]) + tr * n_gaps

            wrap = 0
            if single:
                # uma linha continua uma linha: usa o espaco livre; se nao couber, primeiro tira o
                # espacamento entre letras, depois diminui a letra ate 70%. So quebra em duas se ainda
                # assim nao couber E houver espaco para quebrar (nunca no meio de uma palavra).
                if b.get("alt") and (width_of(px, 0) > avail or width_of(px, 0) < b["w"] - px * 0.25):
                    # trecho que so caberia com a letra menor que a do resto da linha ("Limpe 8" pequeno
                    # ao lado de "Medium Rubble"), ou bem mais curto que o original (sobrava um buraco:
                    # "Colete 12  Stone Rubble"): redesenha a linha inteira no tamanho certo. Se a linha
                    # tambem nao couber, volta para o trecho
                    todo.insert(0, dict(b["alt"], back=dict(b, alt=None)))
                    continue
                if width_of(px, track) > avail:
                    track = max(0, min(track, (avail - width_of(px, 0)) / n_gaps)) if n_gaps else 0
                floor = max(min_px, int(round(px * 0.8)))  # menor que 80% fica ilegivel: melhor o original
                while px > floor and width_of(px, track) > avail:
                    px -= 1
                if width_of(px, track) > avail:
                    if len(b["en"].split()) >= 5 and " " in b["pt"] and not b.get("inline"):
                        wrap, track = avail, 0  # frase: pode quebrar em duas linhas
                    elif width_of(px, track) > avail * (1.0 if b.get("inline") else 1.08):
                        if b.get("back"):
                            todo.insert(0, b["back"])
                        continue  # rotulo curto que nao cabe nem com a letra menor: fica o original
            else:
                wrap = avail
            ax, anchor = {"center": (b["x"] + b["w"] / 2, "n"), "right": (b["x"] + b["w"], "ne")}.get(
                align, (b["x"], "nw"))
            while True:
                fnt = self.font(px, italic, **fkw)
                if track >= 0.5 and not wrap:
                    item, bx = self.draw_tracked(c, ax, b["y"], b["pt"], fnt, fg, track, align)
                    break
                item = c.create_text(ax, b["y"], text=b["pt"], anchor=anchor, justify=align, width=wrap,
                                     font=fnt, fill=fg)
                bx = c.bbox(item)
                if single or bx[3] - bx[1] <= b["h"] * 1.2 + 2 or px <= min_px:
                    break
                c.delete(item)
                px -= 1
            one_line = bx[3] - bx[1] < fnt.metrics("linespace") * 1.5
            if face and single and one_line:
                # mesma linha de base do original: as letras assentam onde as originais assentavam,
                # mesmo que a traducao tenha acento ou letra que desce e o original nao
                baseline = ink_y + ink_h - face["below"]
                dy = baseline - fnt.metrics("ascent") - bx[1]
                top, bottom = baseline - px * face.get("up", 0.98), baseline + px * face.get("down", 0.27)
            else:
                # centraliza na altura do texto original (a caixa do tk inclui espaco acima/abaixo das letras)
                dy = (b["y"] + b["h"] / 2) - (bx[1] + bx[3]) / 2
                if one_line:
                    dy -= px0 * (0.15 if any(ch in DESCENDERS for ch in b["pt"]) else 0.06)
                top, bottom = bx[1] + dy, bx[3] + dy
            dx = 0
            if bx[0] < 2:
                dx = 2 - bx[0]
            elif bx[2] > w - 2:
                dx = w - 2 - bx[2]
            c.move(item, dx, dy)
            bx = (bx[0] + dx, bx[1] + dy, bx[2] + dx, bx[3] + dy)
            pad = 2
            rx0, ry0 = min(bx[0], b["x"]) - pad, min(top, b["y"]) - pad
            rx1, ry1 = max(bx[2], b["x"] + b["w"]) + pad, max(bottom, b["y"] + b["h"]) + pad
            r = c.create_rectangle(rx0, ry0, rx1, ry1, fill=bg, outline="")
            c.tag_lower(r, item)
            if screen_colors and "grad" in b:
                # fundo que nao e liso (degrade, painel translucido): repinta linha a linha com as cores
                # lidas a esquerda e a direita do texto, interpolando entre elas
                gy, rows = b["grad"]
                seg = (rx1 - rx0) / 6
                for yy in range(int(ry0), int(ry1) + 1):
                    lc, rc = rows[min(max(yy - gy, 0), len(rows) - 1)]
                    if lc == rc:
                        c.tag_lower(c.create_line(rx0, yy, rx1, yy, fill=lc), item)
                        continue
                    l3, r3 = _rgb(lc), _rgb(rc)
                    for k in range(6):
                        t = (k + 0.5) / 6
                        col = "#%02x%02x%02x" % tuple(int(l3[i] + (r3[i] - l3[i]) * t) for i in range(3))
                        c.tag_lower(c.create_line(rx0 + seg * k, yy, rx0 + seg * (k + 1), yy, fill=col), item)
                c.tag_lower(r)
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
        first = winutil.single_instance("RuneteriaTradutor.instancia")
        if not first and "--reiniciar" in sys.argv:
            for _ in range(40):  # reabrindo: espera a copia anterior fechar
                time.sleep(0.25)
                if winutil.single_instance("RuneteriaTradutor.instancia"):
                    first = True
                    break
        if not first:
            from tkinter import messagebox
            _r = tk.Tk()
            _r.withdraw()
            messagebox.showinfo(APP_NAME, "O Tradutor Runeteria já está aberto.")
            raise SystemExit(0)
        App().run()
    except Exception:
        log_error()
        raise
