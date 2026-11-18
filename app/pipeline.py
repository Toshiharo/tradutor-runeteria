"""Transforma as linhas lidas pelo OCR em caixas traduzidas (sem depender do Windows, testavel)."""
import queue
import re
import threading
import time

from library import normalize
from style import block_align, guess_align

LETTERS_RE = re.compile(r"[A-Za-z]{2,}")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
PT_RE = re.compile(r"[ãõçáéíóúâêô]")
VOWELS = set("aeiouy")

STABLE_SECONDS = 1.5   # o texto precisa ficar parado na tela esse tempo antes de ir para a traducao automatica
FORGET_SECONDS = 6.0   # sumiu da tela por esse tempo: a contagem recomeca
MAX_QUEUE = 30         # fila cheia = tela com muito texto novo; o resto espera a proxima passada
MAX_FAILED = 4000
MAX_LEN = 400


def group_blocks(lines):
    """Junta linhas de um mesmo paragrafo (descricoes quebradas em varias linhas)."""
    lines = sorted(lines, key=lambda l: (round(l["y"]), l["x"]))
    blocks = []
    for ln in lines:
        placed = False
        for b in reversed(blocks[-6:]):
            last = b["lines"][-1]
            gap = ln["y"] - (last["y"] + last["h"])
            same_col = abs(ln["x"] - b["x"]) < max(12, last["h"] * 1.5) or (
                abs((ln["x"] + ln["w"] / 2) - (b["x"] + b["w"] / 2)) < last["h"] * 2)  # texto centralizado
            similar_h = 0.7 < (ln["h"] / max(last["h"], 1)) < 1.4
            if -2 <= gap < last["h"] * 0.9 and same_col and similar_h:
                b["lines"].append(ln)
                x2 = max(b["x"] + b["w"], ln["x"] + ln["w"])
                b["x"] = min(b["x"], ln["x"])
                b["w"] = x2 - b["x"]
                b["h"] = ln["y"] + ln["h"] - b["y"]
                placed = True
                break
        if not placed:
            blocks.append({"x": ln["x"], "y": ln["y"], "w": ln["w"], "h": ln["h"], "lines": [ln]})
    return blocks


def _wordlike(word):
    """Palavra com cara de palavra: tem vogal e caixa regular (o OCR do cenario 3D gera coisas como 'rnIlE')."""
    core = word.replace("'", "").replace("-", "")
    if len(core) < 2:
        return core in ("a", "A", "I")
    if not any(c in VOWELS for c in core.lower()):
        return False
    return core.islower() or core.isupper() or (core[0].isupper() and core[1:].islower())


def looks_translatable(text):
    """Filtro para a traducao automatica: so passa o que parece frase/rotulo em ingles de verdade."""
    t = text.strip()
    if not 3 <= len(t) <= MAX_LEN or not LETTERS_RE.search(t):
        return False
    letters = sum(c.isalpha() for c in t)
    if letters / len(t) < 0.5:
        return False
    # texto ja em portugues (acentos tipicos) nao precisa
    if PT_RE.search(t.lower()):
        return False
    words = WORD_RE.findall(t)
    good = [w for w in words if _wordlike(w)]
    if not good or len(good) / len(words) < 0.6:
        return False
    return any(len(w) >= 3 for w in good)


class Translator:
    """Biblioteca primeiro; o que nao achar vai para a fila da traducao offline (em segundo plano)."""

    def __init__(self, library, mt, cfg):
        self.lib = library
        self.mt = mt
        self.cfg = cfg
        self.q = queue.Queue()
        self._lock = threading.Lock()
        self.pending = set()   # chaves na fila
        self.failed = set()    # chaves que o modelo nao soube traduzir (nao tenta de novo nesta sessao)
        self.seen = {}         # chave -> [primeira vez, ultima vez] que apareceu na tela
        self._last_prune = 0.0
        if self._mt_ok():
            threading.Thread(target=self._worker, daemon=True).start()

    def _mt_ok(self):
        return self.mt is not None and getattr(self.mt, "ok", False)

    def _worker(self):
        while True:
            key, text = self.q.get()
            ok = False
            try:
                pt = self.mt.translate(text)
                # saida igual a entrada (nome proprio) ou absurdamente longa (modelo "viajou") nao serve
                if pt and pt.strip().lower() != text.strip().lower() and len(pt) <= len(text) * 3 + 20:
                    self.lib.add_auto(text, pt, "auto-tela")
                    ok = True
            except Exception:
                pass
            with self._lock:
                if not ok:
                    if len(self.failed) >= MAX_FAILED:
                        self.failed.clear()
                    self.failed.add(key)
                self.pending.discard(key)

    def _maybe_queue(self, text):
        """Manda para a traducao automatica so o que parece texto de verdade e esta parado na tela."""
        if not self.cfg.get("traduzir_desconhecidos", True) or not self._mt_ok():
            return
        key = normalize(text)
        if not key:
            return
        now = time.monotonic()
        with self._lock:
            if key in self.pending or key in self.failed:
                return
            if not looks_translatable(text):
                return
            rec = self.seen.get(key)
            if rec is None or now - rec[1] > FORGET_SECONDS:
                self.seen[key] = [now, now]
                return
            rec[1] = now
            if now - rec[0] < STABLE_SECONDS or self.q.qsize() >= MAX_QUEUE:
                return
            del self.seen[key]
            self.pending.add(key)
        self.q.put((key, text))

    def _prune(self):
        now = time.monotonic()
        if now - self._last_prune < 5:
            return
        self._last_prune = now
        with self._lock:
            for k in [k for k, rec in self.seen.items() if now - rec[1] > FORGET_SECONDS]:
                del self.seen[k]

    def _one(self, text, allow_mt=True):
        hit = self.lib.lookup(text, self.cfg.get("similaridade_minima", 86))
        if hit:
            return hit[0], hit[1]
        if allow_mt:
            self._maybe_queue(text)
        return None

    def boxes(self, lines):
        """Devolve [{'x','y','w','h','line_h','pt','origin','en'}]."""
        self._prune()
        out = []

        def box(geo, first, pt, origin, en, align, n_lines):
            d = {**{k: geo[k] for k in "xywh"}, "line_h": first["h"], "pt": pt, "origin": origin,
                 "en": en, "align": align, "lines": n_lines,
                 "ref": (first["text"], first["w"])}  # 1a linha original: serve para medir peso/tamanho da fonte
            for k in ("bg", "fg"):  # cores tiradas da captura (style.add_colors), se houver
                if k in first:
                    d[k] = first[k]
            if "room_r" in first:  # espaco livre dos lados (o menor entre as linhas do paragrafo)
                ls = geo.get("lines", [first])
                d["room_l"] = max(0, min(l.get("room_l", 0) - (l["x"] - geo["x"]) for l in ls))
                d["room_r"] = max(0, min(l.get("room_r", 0) - (geo["x"] + geo["w"] - l["x"] - l["w"]) for l in ls))
            return d

        for b in group_blocks(lines):
            multi = len(b["lines"]) > 1
            full = " ".join(l["text"] for l in b["lines"])
            r = self._one(full, allow_mt=False) if multi else None
            if r:
                out.append(box(b, b["lines"][0], r[0], r[1], full, block_align(b["lines"]), len(b["lines"])))
                continue
            hits = 0
            for ln in b["lines"]:
                r = self._one(ln["text"], allow_mt=not multi)
                if r:
                    hits += 1
                    out.append(box(ln, ln, r[0], r[1], ln["text"], guess_align(ln, lines), 1))
            if multi and hits == 0:
                self._one(full)  # paragrafo desconhecido: traduz inteiro em segundo plano
        return out
