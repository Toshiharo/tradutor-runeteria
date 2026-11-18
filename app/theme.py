"""Visual da janela do app, seguindo o Runeteria Design System (UI KIT V2).

Superficies em azul-marinho (rampa base-bg), dourado (primary) como unico destaque, cantos pequenos,
filetes dourados de 1px. Fontes: Cormorant (titulos), Lexend (botoes e rotulos), Inter (texto).
Os valores abaixo sao os tokens do design system; nao invente cores fora daqui.
"""
import ctypes
import glob
import os
import tkinter as tk
from tkinter import font as tkfont

# ---- tokens de cor (fig-tokens.css / semantic.css) ----
APP = "#0d101b"          # base-bg-950  fundo da janela
PANEL = "#141928"        # base-bg-900  paineis
CARD = "#1a2031"         # base-bg-800  cartoes
INSET = "#252c40"        # base-bg-700  areas rebaixadas, hover
RAISED = "#333c55"       # base-bg-600  bordas, botao secundario
RAISED_HI = "#4a556f"    # base-bg-500
TEXT_STRONG = "#f4f6fb"  # base-bg-50
TEXT = "#c9d0e3"         # base-bg-200
MUTED = "#9aa6c3"        # base-bg-300
DISABLED = "#6e7a98"     # base-bg-400
GOLD = "#e0b356"         # primary-300  acao principal, filetes
GOLD_HI = "#e9c97a"      # primary-200  titulos, hover
GOLD_PRESS = "#cc962c"   # primary-500
GOLD_STRONG = "#b88326"  # primary-600
ON_GOLD = "#3a2a0b"      # primary-950  texto sobre dourado
GREEN = "#54bc8a"        # green-400    status ok
YELLOW = "#ffdd33"       # yellow-400   status atencao
RED = "#da6262"          # red-400      status erro
RED_BTN, RED_BTN_HI, RED_BTN_PRESS = "#d14b4b", "#da6262", "#b13f3f"  # red-500/400/600

_SCALE = None


def scale():
    """Escala do Windows para este monitor (100% = 1.0, 150% = 1.5). RT_UI_SCALE forca um valor (teste)."""
    global _SCALE
    if _SCALE is None:
        try:
            v = float(os.environ.get("RT_UI_SCALE", "0"))
        except ValueError:
            v = 0.0
        if not v:
            try:
                v = ctypes.windll.user32.GetDpiForSystem() / 96.0
            except Exception:
                v = 1.0
        # a janela tem ~800x620 px em 100% (com um aviso no Funcionamento): nunca maior que a area util da tela
        # (notebook 1080p em 150% ou tela de 1280x720 cortariam a janela)
        work_w, work = _work_area()
        if work:
            v = min(v, work * 0.92 / 620.0)
        if work_w:
            v = min(v, work_w * 0.95 / 800.0)
        _SCALE = max(0.75, min(v, 3.0))
    return _SCALE


def _work_area():
    """(largura, altura) da area util da tela principal (sem a barra de tarefas), em pixels; 0 se nao souber."""
    try:
        from ctypes import wintypes
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0):  # SPI_GETWORKAREA
            return r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    return 0, 0


def S(v):
    """Tamanho em pixels de tela para um tamanho pensado em 100% de escala."""
    return int(round(v * scale()))


_FALLBACK = {"Cormorant": "Georgia", "Lexend": "Segoe UI", "Lexend SemiBold": "Segoe UI Semibold",
             "Inter": "Segoe UI", "Inter SemiBold": "Segoe UI Semibold"}
_fonts = {}
_families = None


def load_fonts(folder):
    """Registra as fontes da pasta so para este programa (nada e instalado no Windows)."""
    try:
        gdi = ctypes.WinDLL("gdi32")
        for f in glob.glob(os.path.join(folder, "*.ttf")):
            gdi.AddFontResourceExW(f, 0x10, 0)  # FR_PRIVATE
    except Exception:
        pass


def font(role):
    """Fonte por papel: title, heading, button, label, caption, body, strong."""
    global _families
    if role in _fonts:
        return _fonts[role]
    if _families is None:
        _families = set(tkfont.families())
    family, size, weight = {
        "title": ("Cormorant", 26, "bold"),          # titulo in-game
        "heading": ("Lexend SemiBold", 12, "normal"),  # titulo de secao (MAIUSCULAS)
        "button": ("Lexend SemiBold", 14, "normal"),
        "state": ("Inter SemiBold", 17, "normal"),     # frase de estado da janela (o que esta acontecendo)
        "label": ("Inter SemiBold", 14, "normal"),
        "body": ("Inter", 13, "normal"),
        "caption": ("Lexend", 12, "normal"),
    }[role]
    if family not in _families:
        family = _FALLBACK.get(family, "Segoe UI")
    _fonts[role] = tkfont.Font(family=family, size=-S(size), weight=weight)
    return _fonts[role]


def round_rect(c, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class RButton(tk.Canvas):
    """Botao do kit: rotulo em MAIUSCULAS (Lexend SemiBold), canto de 6px, relevo 3D discreto.
    hover clareia, pressionado escurece e inverte o relevo, desligado cai para base-bg-600."""

    KINDS = {  # (fundo, hover, pressionado, texto, sombra de baixo)
        "primary": (GOLD, GOLD_HI, GOLD_PRESS, ON_GOLD, GOLD_STRONG),
        "secondary": (RAISED, RAISED_HI, INSET, TEXT_STRONG, CARD),
        "destructive": (RED_BTN, RED_BTN_HI, RED_BTN_PRESS, TEXT_STRONG, "#933434"),
    }

    def __init__(self, parent, text, command, kind="secondary", height=38, bg=PANEL, small=False):
        super().__init__(parent, height=S(height), width=10, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command, self.kind = text, command, kind
        self.enabled, self.state, self.small = True, "normal", small
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set("hover"))
        self.bind("<Leave>", lambda e: self._set("normal"))
        self.bind("<ButtonPress-1>", lambda e: self._set("pressed"))
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, text=None, kind=None, enabled=None):
        if text is not None:
            self.text = text
        if kind is not None:
            self.kind = kind
        if enabled is not None:
            self.enabled = enabled
            self.config(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _set(self, state):
        self.state = state
        self._draw()

    def _release(self, e):
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        self._set("hover" if inside else "normal")
        if inside and self.enabled and self.command:
            self.command()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 8:
            return
        fill, hover, pressed, fg, shade = self.KINDS[self.kind]
        if not self.enabled:
            fill, fg, shade, state = RAISED, DISABLED, CARD, "normal"
        else:
            state = self.state
            fill = {"hover": hover, "pressed": pressed}.get(state, fill)
        down = 1 if state == "pressed" else 0
        if not down:
            round_rect(self, 0, S(2), w, h, S(6), fill=shade, outline="")       # sombra de baixo (relevo)
        round_rect(self, 0, down * S(2), w, h - S(2) + down * S(2), S(6), fill=fill, outline="")
        f = font("caption" if self.small else "button")
        self.create_text(w / 2, (h - S(2)) / 2 + down * S(2), text=self.text.upper(), font=f, fill=fg)


class Toggle(tk.Canvas):
    """Chave liga/desliga em pilula: desligada em base-bg-600, ligada em dourado."""

    def __init__(self, parent, value=False, command=None, bg=CARD):
        super().__init__(parent, width=S(38), height=S(20), bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.value, self.command, self.enabled = value, command, True
        self.bind("<ButtonRelease-1>", self._click)
        self._draw()

    def set(self, value=None, enabled=None):
        if value is not None:
            self.value = value
        if enabled is not None:
            self.enabled = enabled
            self.config(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _click(self, _):
        if not self.enabled:
            return
        self.value = not self.value
        self._draw()
        if self.command:
            self.command(self.value)

    def _draw(self):
        self.delete("all")
        on = self.value and self.enabled
        round_rect(self, 0, 0, S(38), S(20), S(10), fill=GOLD if on else RAISED, outline="")
        x = S(28) if self.value else S(10)
        self.create_oval(x - S(7), S(3), x + S(7), S(17), fill=ON_GOLD if on else (MUTED if self.enabled else DISABLED), outline="")


def gold_divider(parent, bg=PANEL):
    """Filete dourado de 1px com um losango no meio (DecorativeDividerGold do kit)."""
    c = tk.Canvas(parent, height=S(11), bg=bg, highlightthickness=0, bd=0)

    def draw(_=None):
        c.delete("all")
        w = c.winfo_width()
        m, r = S(5), S(5)
        c.create_line(0, m, w / 2 - S(9), m, fill=GOLD_STRONG, width=max(1, S(1)))
        c.create_line(w / 2 + S(9), m, w, m, fill=GOLD_STRONG, width=max(1, S(1)))
        c.create_polygon(w / 2, m - r, w / 2 + r, m, w / 2, m + r, w / 2 - r, m, fill=GOLD, outline="")
    c.bind("<Configure>", draw)
    return c


def card(parent, title=None, bg=CARD):
    """Cartao (base-bg-800, borda de 1px base-bg-600) com titulo de secao em MAIUSCULAS dourado."""
    outer = tk.Frame(parent, bg=RAISED)
    inner = tk.Frame(outer, bg=bg)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    if title:
        tk.Label(inner, text=title.upper(), font=font("heading"), fg=GOLD, bg=bg, anchor="w").pack(
            fill="x", padx=S(12), pady=(S(10), S(4)))
    return outer, inner


class StatusRow(tk.Frame):
    """Linha de status: bolinha colorida + nome + situacao, com um botao pequeno opcional a direita."""

    COLORS = {"ok": GREEN, "warn": YELLOW, "bad": RED, "off": DISABLED}

    def __init__(self, parent, name, bg=CARD):
        super().__init__(parent, bg=bg)
        self.dot = tk.Canvas(self, width=S(10), height=S(10), bg=bg, highlightthickness=0, bd=0)
        self.dot.pack(side="left", padx=(S(12), S(8)))
        self._oval = self.dot.create_oval(S(1), S(1), S(9), S(9), fill=DISABLED, outline="")
        tk.Label(self, text=name, font=font("label"), fg=TEXT_STRONG, bg=bg).pack(side="left")
        self.value = tk.Label(self, text="", font=font("body"), fg=MUTED, bg=bg, anchor="e", justify="right")
        self.value.pack(side="right", padx=(S(8), S(12)))
        self.button = None

    def set(self, state, text):
        self.state = state
        self.dot.itemconfig(self._oval, fill=self.COLORS[state])
        self.value.config(text=text)

    def action(self, text, command):
        """Mostra (ou esconde, com text=None) um botao pequeno ao lado da situacao."""
        if self.button is not None:
            self.button.destroy()
            self.button = None
        if text:
            self.button = RButton(self, text, command, kind="primary", height=28, bg=self["bg"], small=True)
            self.button.config(width=S(96))
            self.button.pack(side="right", padx=(S(0), S(12)), before=self.value)
