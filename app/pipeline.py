"""Transforma as linhas lidas pelo OCR em caixas traduzidas (sem depender do Windows, testavel)."""
import queue
import re
import threading
import time

from library import normalize
from style import block_align, guess_align
from variaveis import FUNC as FUNC_WORDS
from variaveis import SEP_RE, find_names, is_name_phrase, is_noise, is_value_token, only_values

LETTERS_RE = re.compile(r"[A-Za-z]{2,}")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
PT_RE = re.compile(r"[ãõçáéíóúâêô]")
VOWELS = set("aeiouy")

STABLE_SECONDS = 0.5   # o texto precisa ficar parado na tela esse tempo antes de ir para a traducao automatica
                       # (curto: tooltip aparece e some; o lixo do cenario ja e barrado pelos filtros)
BATCH = 16             # quantos textos a traducao automatica faz de uma vez
FORGET_SECONDS = 6.0   # sumiu da tela por esse tempo: a contagem recomeca
MAX_QUEUE = 30         # fila cheia = tela com muito texto novo; o resto espera a proxima passada
MAX_FAILED = 4000
MAX_LEN = 400


def _from_words(words):
    x = min(w["x"] for w in words)
    y = min(w["y"] for w in words)
    return {"text": " ".join(w["text"] for w in words), "x": x, "y": y,
            "w": max(w["x"] + w["w"] for w in words) - x, "h": max(w["y"] + w["h"] for w in words) - y}


def tidy_lines(lines):
    """Arruma as linhas do OCR antes de traduzir, usando a posicao de cada palavra.

    - O OCR junta numa "linha" coisas que estao lado a lado mas sao elementos diferentes
      (dois botoes, rotulo + valor na outra ponta): um vao maior que 3,2x a altura separa
      (menos que isso pode ser so um rotulo com letras bem espacadas, como "RUNE  BACKPACK").
    - Icones ao lado do texto sao lidos como letra ou simbolo ("O MANA", "V AGILITY", "@ SERVERS").
      Um pedaco de 1 caractere na ponta, que seja simbolo ou esteja afastado do texto, e descartado:
      senao a traducao cobriria o icone e ficaria do tamanho dele.
    """
    out = []
    for ln in lines:
        words = ln.get("words")
        if not words or len(words) == 1:
            out.append(ln)
            continue
        hs = sorted(w["h"] for w in words)
        hmed = hs[(len(hs) - 1) // 2]  # mediana "para baixo": um icone alto nao puxa a referencia
        segs, cur = [], [words[0]]
        for prev, w in zip(words, words[1:]):
            if w["x"] - (prev["x"] + prev["w"]) > hmed * 3.2:
                segs.append(cur)
                cur = []
            cur.append(w)
        segs.append(cur)
        for seg in segs:
            for end in (0, -1):  # ponta esquerda, depois a direita
                while len(seg) > 1 and len(seg[end]["text"]) == 1 and not seg[end]["text"].isdigit():
                    edge, nxt = seg[end], seg[1 if end == 0 else -2]
                    gap = (nxt["x"] - (edge["x"] + edge["w"])) if end == 0 else (edge["x"] - (nxt["x"] + nxt["w"]))
                    # + - & etc. podem ser texto de verdade ("+ UPGRADE"): esses so saem se estiverem afastados
                    symbol = not edge["text"].isalnum() and edge["text"] not in "+-&/%#$()[]<>=:;.,!?\"'"
                    taller = edge["h"] > nxt["h"] * 1.3 and gap > hmed * 0.5  # icone e maior que a letra
                    if not (symbol or gap > hmed * 0.9 or taller):
                        break
                    seg.pop(end)
            if len(seg) == 1 and len(seg[0]["text"]) == 1 and not seg[0]["text"].isalnum():
                continue  # sobrou so um simbolo solto
            out.append(_from_words(seg))
    return out


def _near(c1, c2, limit=48):
    """Duas cores '#rrggbb' sao praticamente a mesma? (a cor lida de cada pedaco varia um pouco)"""
    if not c1 or not c2:
        return c1 == c2
    return sum(abs(int(c1[i:i + 2], 16) - int(c2[i:i + 2], 16)) for i in (1, 3, 5)) <= limit


def join_known(lines, knows):
    """Junta pedacos vizinhos na mesma linha quando o texto junto e conhecido da biblioteca.

    Rotulos com letras bem espacadas ("RUNE   BACKPACK") chegam do OCR em pedacos; traduzidos um a um
    viram "RUNA MOCHILA". Se o conjunto existe na biblioteca, vale o conjunto.
    """
    lines = sorted(lines, key=lambda l: (round(l["y"] / 4), l["x"]))
    out, i = [], 0
    while i < len(lines):
        a = lines[i]
        j = i + 1
        while j < len(lines):
            b = lines[j]
            gap = b["x"] - (a["x"] + a["w"])
            same_row = abs(b["y"] - a["y"]) < a["h"] * 0.35 and 0.75 < b["h"] / max(a["h"], 1) < 1.33
            if not (same_row and 0 < gap < a["h"] * 6 and _near(a.get("fg"), b.get("fg"))
                    and knows(a["text"] + " " + b["text"])):
                break
            m = dict(a)
            m["text"] = a["text"] + " " + b["text"]
            m["w"] = b["x"] + b["w"] - a["x"]
            m["h"] = max(a["y"] + a["h"], b["y"] + b["h"]) - min(a["y"], b["y"])
            m["y"] = min(a["y"], b["y"])
            if "room_r" in b:
                m["room_r"] = b["room_r"]
            m["cut"] = bool(b.get("cut"))  # o "colado" entre os dois pedacos era o proprio vizinho
            m.pop("grad", None)
            a = m
            j += 1
        out.append(a)
        i = j
    return out


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


def mostly_untranslated(src, pt, known=()):
    """True se boa parte da 'traducao' sao palavras copiadas do original.

    Acontece quando o OCR leu errado ('Incrcascs your chancc') ou quando o texto nao e ingles:
    o modelo nao reconhece as palavras e as devolve iguais. Isso nao deve ir para a memoria.
    """
    src_words = {w.lower() for w in WORD_RE.findall(src) if len(w) >= 4}
    out_words = [w.lower() for w in re.findall(r"[^\W\d_]{4,}", pt)]
    out_words = [w for w in out_words if w not in known]
    if not out_words:
        return False
    same = [w for w in out_words if w in src_words]
    return len(same) >= 2 and len(same) / len(out_words) >= 0.3


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
        self._composed = {}    # texto -> traducao montada por partes (ou None)
        self._unknown = {}     # palavra -> o modelo de traducao nao conhece (nome inventado)
        if self._mt_ok():
            threading.Thread(target=self._worker, daemon=True).start()

    def _mt_ok(self):
        return self.mt is not None and getattr(self.mt, "ok", False)

    def _worker(self):
        while True:
            items = [self.q.get()]
            while len(items) < BATCH:  # junta o que mais chegou: tela nova = varios textos de uma vez
                try:
                    items.append(self.q.get_nowait())
                except queue.Empty:
                    break
            texts = [t for _, t in items]
            try:
                outs = self.mt.translate_many(texts, [self.names_in(t) for t in texts])
            except Exception:
                outs = [None] * len(items)
            known = self._known_words()
            for (key, text), pt in zip(items, outs):
                ok = False
                try:
                    keep = {w.lower() for n in self.names_in(text) for w in n.split()}
                    # saida igual a entrada (nome proprio) ou absurdamente longa (modelo "viajou") nao serve
                    if (pt and pt.strip().lower() != text.strip().lower() and len(pt) <= len(text) * 3 + 20
                            and not mostly_untranslated(text, pt, known | keep)):
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

    # ---------- nomes e partes variaveis ----------
    def unknown_word(self, word):
        """O modelo nao conhece a palavra (quebra em 3+ pedacos): e nome inventado (Boomshroom, Velcorne)."""
        w = word.strip("'\"").lower()
        if len(w) < 5 or not self._mt_ok():
            return False
        r = self._unknown.get(w)
        if r is None:
            if len(self._unknown) > 20000:
                self._unknown.clear()
            r = self._unknown[w] = self.mt.pieces(w) >= 3 and not self.lib.knows(w)
        return r

    def _fixed_terms(self):
        """Termos de jogo que tem traducao (slot -> espaco): quem tem um deles e rotulo, nao nome."""
        return [en for en, pt in getattr(self.lib, "terms", {}).items() if pt.lower() != en.lower()]

    def is_name(self, text):
        return is_name_phrase(text, self._fixed_terms(), self.unknown_word)

    def names_in(self, text):
        """Nomes e valores da frase que a traducao automatica nao pode mexer ("7.7s" virava "7, 7 s")."""
        keep = find_names(text, self._fixed_terms(), self.unknown_word)
        for tok in text.split():
            t = tok.strip(",;()[]")
            if t and is_value_token(t) and re.search(r"\d", t) and re.search(r"[A-Za-z.,:/]", t) and t not in keep:
                keep.append(t)
        return keep

    def compose(self, text):
        """Monta a traducao de linhas de tooltip/atributos por partes, sem traducao automatica.

        "Armor 15 Vitality +7" -> "Armadura 15 Vitalidade +7"
        "Bleeding Slice 143 damage • 7.7s • 32..." -> nome fica, "damage" vem da biblioteca, valores ficam.
        Devolve (traducao, origem) ou None se alguma parte nao tiver traducao conhecida.
        """
        if text in self._composed:
            return self._composed[text]
        if len(self._composed) > 5000:
            self._composed.clear()
        r = self._compose(text)
        self._composed[text] = r
        return r

    def _lookup_piece(self, phrase):
        hit = self.lib.lookup(phrase, 92)
        if not hit:
            term = getattr(self.lib, "terms", {}).get(phrase.lower())  # "weapon damage" -> "dano de arma"
            if not term:
                return None
            hit = (term.upper() if phrase.isupper() else (term[:1].upper() + term[1:] if phrase[:1].isupper() else term),
                   "manual")
        pt, origin = hit[0], hit[1]
        if phrase.islower():
            pt = pt.lower()
        return pt, origin

    def _compose(self, text):
        parts = SEP_RE.split(text)
        out, origins = [], set()
        for k, seg in enumerate(parts):
            if k % 2 or not seg.strip() or only_values(seg):
                out.append(seg)  # separador ou so valores
                continue
            core = seg.strip()
            if len(parts) > 1:
                hit = self._lookup_piece(core)
                if hit:
                    out.append(seg.replace(core, hit[0]))
                    origins.add(hit[1])
                    continue
            if self.is_name(core):
                out.append(seg)
                continue
            # pedaco com valores no meio ("Armor 15 Vitality +7"): termo a termo, mas so em linha
            # de atributo (tem numero e nao tem palavra de frase), nunca em frase comum
            toks = core.split()
            if not any(is_value_token(t) for t in toks) or any(t.lower() in FUNC_WORDS for t in toks):
                return None
            res, i = [], 0
            while i < len(toks):
                if is_value_token(toks[i]):
                    res.append(toks[i])
                    i += 1
                    continue
                j = i
                while j < len(toks) and not is_value_token(toks[j]):
                    j += 1
                run = toks[i:j]
                done = False
                for end in range(len(run), 0, -1):  # maior pedaco conhecido primeiro
                    phrase = " ".join(run[:end])
                    hit = self._lookup_piece(phrase)
                    # no comeco da linha de atributo vem o nome da skill/item ("Hemorrhage 145 damage")
                    lead = i == 0 and all(w[:1].isupper() for w in run[:end]) and not phrase.isupper()
                    if hit or self.is_name(phrase) or (lead and end == len(run)):
                        res.append(hit[0] if hit else phrase)
                        if hit:
                            origins.add(hit[1])
                        i += end
                        done = True
                        break
                if not done:
                    return None
            out.append(seg.replace(core, " ".join(res)))
        if not origins:
            return None  # nada traduzido: deixa o original
        return "".join(out), ("auto" if "auto" in origins else "manual")

    def _known_words(self):
        """Palavras que e normal sairem iguais na traducao: nomes do glossario e termos mantidos em ingles."""
        words = set()
        for t in list(getattr(self.lib, "glossary", [])) + list(getattr(self.lib, "terms", {}).values()):
            words.update(w.lower() for w in WORD_RE.findall(t))
        return words

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
        if not allow_mt:
            return None
        r = self.compose(text)  # linha de tooltip/atributo: monta por partes
        if r:
            return r
        if self.is_name(text) or is_noise(text, self.unknown_word):
            return None  # nome proprio ou nome de jogador: fica em ingles, sem caixa por cima
        self._maybe_queue(text)
        return None

    def boxes(self, lines):
        """Devolve [{'x','y','w','h','line_h','pt','origin','en'}]."""
        self._prune()
        lines = join_known(lines, self.lib.knows)
        out = []

        def box(geo, first, pt, origin, en, align, n_lines):
            d = {**{k: geo[k] for k in "xywh"}, "line_h": first["h"], "pt": pt, "origin": origin,
                 "en": en, "align": align, "lines": n_lines,
                 "ref": (first["text"], first["w"])}  # 1a linha original: serve para medir peso/tamanho da fonte
            for k in ("bg", "fg", "iy", "ih", "ink", "grad"):  # cores e altura exata das letras (style.add_colors), se houver
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
                if ln.get("cut"):
                    continue  # o OCR pegou so um pedaco da palavra: melhor nao traduzir
                r = self._one(ln["text"], allow_mt=not multi)
                if r:
                    hits += 1
                    out.append(box(ln, ln, r[0], r[1], ln["text"], guess_align(ln, lines), 1))
            if multi and hits == 0:
                self._one(full)  # paragrafo desconhecido: traduz inteiro em segundo plano
        return out
