"""Transforma as linhas lidas pelo OCR em caixas traduzidas (sem depender do Windows, testavel)."""
import queue
import re
import threading
import time

from library import normalize
from style import block_align, guess_align
from variaveis import FUNC as FUNC_WORDS
from variaveis import UI_TERMS
from variaveis import SEP_RE, find_names, is_name_phrase, is_noise, is_value_token, only_values

LETTERS_RE = re.compile(r"[A-Za-z]{2,}")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
PT_RE = re.compile(r"[ãõçáéíóúâêô]")
VOWELS = set("aeiouy")

STABLE_SECONDS = 0.5   # o texto precisa ficar parado na tela esse tempo antes de ir para a traducao automatica
STABLE_ONLINE = 1.0    # com a traducao online: espera mais (tooltip que pisca na tela nao gasta a cota)
SHORT_CHAT = 3         # mensagem de chat com ate essas palavras vai para a traducao offline (gratis)
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
            "w": max(w["x"] + w["w"] for w in words) - x, "h": max(w["y"] + w["h"] for w in words) - y,
            "words": list(words)}


_TALL = re.compile(r"[A-Z0-9bdfhklt]")


def _join_split_capital(words):
    """Em algumas fontes o OCR separa a maiuscula do resto da palavra ("T wo" em vez de "Two"): o T e
    o w quase se encostam. Junta letra maiuscula sozinha (menos A e I, que sao palavras) com a palavra
    em minusculas logo depois, se o vao for bem menor que um espaco."""
    out = [dict(words[0])]
    for w in words[1:]:
        p = out[-1]
        gap = w["x"] - (p["x"] + p["w"])
        if (len(p["text"]) == 1 and p["text"].isupper() and p["text"] not in "AI"
                and w["text"][:1].islower() and w["text"][:1].isalpha() and gap < max(p["h"], w["h"]) * 0.18):
            top = min(p["y"], w["y"])
            p.update(text=p["text"] + w["text"], w=w["x"] + w["w"] - p["x"], y=top,
                     h=max(p["y"] + p["h"], w["y"] + w["h"]) - top)
        else:
            out.append(dict(w))
    return out


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
        if words and len(words) > 1:
            joined = _join_split_capital(words)
            if len(joined) != len(words):
                words = joined
                ln = dict(ln, words=words, text=" ".join(w["text"] for w in words))
        if not words or len(words) == 1:
            out.append(ln)
            continue
        hs = sorted(w["h"] for w in words)
        hmed = hs[(len(hs) - 1) // 2]  # mediana "para baixo": um icone alto nao puxa a referencia
        segs, cur = [], [words[0]]
        tall = words[0]["h"] if _TALL.search(words[0]["text"]) else None
        for prev, w in zip(words, words[1:]):
            cut = w["x"] - (prev["x"] + prev["w"]) > hmed * 3.2
            if _TALL.search(w["text"]):
                # titulo grande + legenda pequena na mesma linha ("Ore Mastery +1%" + "Current bonus"):
                # so compara palavras com letra alta/maiuscula/numero, cuja altura e a da fonte
                if tall and not 0.68 < w["h"] / tall < 1.47:
                    cut = True
                tall = w["h"]
            if cut:
                segs.append(cur)
                cur = []
            cur.append(w)
        segs.append(cur)
        for seg in segs:
            for end in (0, -1):  # ponta esquerda, depois a direita
                # borda de icone lida como "_1", "|1": pedaco curto sem letra, colado no texto
                while (len(seg) > 1 and len(seg[end]["text"]) == 2 and not re.search(r"[A-Za-z]", seg[end]["text"])
                       and re.search(r"[_|\/\[\]()]", seg[end]["text"])):
                    seg.pop(end)
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
            if a.get("words") and b.get("words"):
                m["words"] = a["words"] + b["words"]
            else:
                m.pop("words", None)
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
            similar_h = 0.8 < (ln["h"] / max(last["h"], 1)) < 1.25
            # cor diferente = outro elemento (titulo do card branco, detalhe cinza embaixo)
            same_color = _near(ln.get("fg"), last.get("fg"), 60) if ln.get("fg") and last.get("fg") else True
            if -2 <= gap < last["h"] * 0.9 and same_col and similar_h and same_color:
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
    # texto ja em portugues nao precisa. Qualquer letra fora do ASCII conta: o texto do Runeteria e ingles
    # sem acento, e o leitor (en-US) le os acentos do cliente em portugues errado ("Inventårio", "colisäo")
    if PT_RE.search(t.lower()) or any(c.isalpha() and ord(c) > 127 for c in t):
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


_CHANNEL = re.compile(r"^[\[(]?[A-Z]{2,4}(-[A-Z0-9]{2,6})?[\])]?$")  # (NA-DRV), [EU], G
_PT_WORDS = {"que", "não", "nao", "é", "eu", "vc", "você", "voce", "pra", "pro", "tá", "ta", "mano", "sim",
             "tbm", "também", "tambem", "alguém", "alguem", "com", "isso", "aqui", "como", "uma", "um", "meu",
             "minha", "vai", "vou", "tem", "ele", "ela", "mas", "porque", "pq", "quem", "onde", "obrigado",
             "valeu", "kkk", "kkkk", "kkkkk", "oi", "olá", "ola", "bom", "boa", "muito", "mto", "já", "ja",
             "da", "na", "os", "por", "esse", "essa", "nós", "nos", "vamos", "galera", "aí",
             "quer", "fazer", "comigo", "contigo", "pode", "posso", "vem", "tô", "kd", "cadê", "cade",
             "mais", "ainda", "agora", "hoje", "sei", "sou", "foi", "então", "entao", "ninguém", "ninguem",
             "alguma", "algum", "fala", "falou", "beleza", "blz", "slk", "mds", "nada", "tudo", "ajuda", "preciso",
             "onde", "fica", "achei", "acho", "estou", "aqui", "lá", "dele", "dela", "gente", "bora"}


CHAT_ZONE_KEEP = 1800.0  # segundos que a posicao do chat fica lembrada sem ver uma mensagem "canal nome:"
# comeco de mensagem que chat_split nao reconhece (nome todo minusculo, etiqueta de rank na frente)
_OTHER_SPEAKER = re.compile(r"^(?:\[[^\]]+\]\s+)?[^\s:]{2,}:\s+\S")


def chat_split(text):
    """Linha de chat ("G (NA-DRV) RazeNBlaze420: and then says all carts...") -> (indice da primeira palavra
    da mensagem, mensagem), ou None. So a mensagem e traduzida: canal e nome ficam com os pixels do jogo."""
    toks = text.split()
    for k, t in enumerate(toks[:6]):
        if len(t) > 1 and t.endswith(":") and len(toks) - (k + 1) >= 1:
            name, prefix = t[:-1], toks[:k]
            nameish = bool(re.search(r"[\d_]", name)) or (name[:1].isupper() and not name.isupper() and
                                                           any(c.isupper() for c in name[1:]))
            if any(_CHANNEL.match(p) for p in prefix) or (prefix and nameish) or (nameish and k == 0):
                return k + 1, " ".join(toks[k + 1:])
            return None
    return None


def looks_portuguese(text):
    """Mensagem de chat que ja esta em portugues (o Runeteria tem muito jogador brasileiro): nao traduz."""
    if re.search(r"[ãõçâêôáéíóú]", text.lower()):
        return True
    words = re.findall(r"[a-zà-ú]+", text.lower())
    return bool(words) and sum(w in _PT_WORDS for w in words) >= max(1, len(words) * 0.25)


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
        self.chat = {}         # mensagem de chat -> traducao (fica so na memoria do programa)
        self.pointer = None    # (x, y) do cursor na janela do jogo, ou None (chat fechado: nao traduz chat)
        self._zone = None      # onde fica a coluna do chat na tela (ver _chat_zone_lines)
        self.view = None       # (largura, altura) da janela do jogo, para saber onde fica o chat
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
            texts = [t for _, t, _ in items]
            try:
                outs = self.mt.translate_many(texts, [self.names_in(t) for t in texts], [k for _, _, k in items])
            except Exception:
                outs = [None] * len(items)
            known = self._known_words()
            for (key, text, keep_it), pt in zip(items, outs):
                ok = False
                try:
                    keep = {w.lower() for n in self.names_in(text) for w in n.split()}
                    # saida igual a entrada (nome proprio) ou absurdamente longa (modelo "viajou") nao serve
                    # numeros tem que ser os mesmos do jogo ("level 10" virou "nivel IO 10")
                    same_numbers = sorted(re.findall(r"\d+", text)) == sorted(re.findall(r"\d+", pt or ""))
                    if (pt and pt.strip().lower() != text.strip().lower() and len(pt) <= len(text) * 3 + 20
                            and same_numbers and not re.search(r"\bI[O0]\b|\bO[I1]\b", pt)
                            and not mostly_untranslated(text, pt, known | keep)):
                        if keep_it is True:
                            self.lib.add_auto(text, pt, "auto-tela")
                        else:
                            if len(self.chat) > 400:
                                self.chat.clear()
                            self.chat[key] = pt
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
        """Palavras de interface (slot, quest, shop...): quem tem uma delas e rotulo, nao nome proprio."""
        return UI_TERMS

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
        toks = text.split()
        segs, cur = [], []
        for k, t in enumerate(toks):
            if t in ("•", "·", "|"):  # separador de tooltip
                if cur:
                    segs.append(cur)
                cur = []
                continue
            cur.append(k)
        if cur:
            segs.append(cur)
        spans = []  # (primeira palavra, depois da ultima, traducao, origem)
        multi = len(segs) > 1
        # objetivo de missao: verbo + quantidade + nome do item ("Mine 15 Rock Blocks"). So o verbo e
        # traduzido (da lista de verbos de objetivo: na biblioteca "Mine" e "Meus", de "meus itens");
        # o nome do item fica como esta no jogo
        verbs = getattr(self.lib, "verbs", {})
        if (len(toks) >= 3 and toks[0][:1].isupper() and toks[0].lower() in verbs
                and re.fullmatch(r"\d+", toks[1]) and toks[2][:1].isupper()
                and not any(w.lower() in FUNC_WORDS for w in toks[2:])):
            return (" ".join([verbs[toks[0].lower()]] + toks[1:]), "manual", [(0, 1, verbs[toks[0].lower()], "manual")])
        for seg in segs:
            words = [toks[k] for k in seg]
            phrase = " ".join(words)
            if all(is_value_token(w) for w in words):
                continue
            if multi:
                hit = self._lookup_piece(phrase)
                if hit:
                    spans.append((seg[0], seg[-1] + 1, hit[0], hit[1]))
                    continue
            if self.is_name(phrase):
                continue
            # pedaco com valores no meio ("Armor 15 Vitality +7"): termo a termo, mas so em linha
            # de atributo (tem numero e nao tem palavra de frase), nunca em frase comum
            if not any(is_value_token(w) for w in words):
                return None
            # com palavra de frase (you, your, of...) nao se traduz palavra por palavra: cada trecho entre
            # valores tem que ser, inteiro, um texto da biblioteca ("You Buy" + preco)
            whole_only = any(w.lower() in FUNC_WORDS for w in words)
            i = 0
            while i < len(words):
                if is_value_token(words[i]):
                    i += 1
                    continue
                j = i
                while j < len(words) and not is_value_token(words[j]):
                    j += 1
                run, done = words[i:j], False
                for end in range(len(run), 0, -1):  # maior pedaco conhecido primeiro
                    if whole_only and end < len(run):
                        break
                    ph = " ".join(run[:end])
                    hit = self._lookup_piece(ph) if not whole_only or self.lib.knows(ph) else None
                    # no comeco da linha de atributo vem o nome da skill/item ("Hemorrhage 145 damage")
                    lead = i == 0 and all(w[:1].isupper() for w in run[:end]) and not ph.isupper()
                    if hit or self.is_name(ph) or (lead and end == len(run)):
                        if hit and hit[0] != ph:
                            spans.append((seg[i], seg[i + end - 1] + 1, hit[0], hit[1]))
                        i += end
                        done = True
                        break
                if not done:
                    # "BUY 1 BOOMSHROOM PLAGUE F...": depois de um trecho conhecido e de um valor, o que
                    # sobra ate o fim e o nome do item - fica como esta
                    # (o valor antes tem numero, e o resto nao e frase: "Your guild - here is what..." nao)
                    if (spans and i > 0 and is_value_token(words[i - 1]) and re.search(r"\d", words[i - 1])
                            and j == len(words) and not any(w.lower() in FUNC_WORDS for w in words[i:j])):
                        i = j
                        continue
                    return None
        if not spans:
            return None  # nada traduzido: deixa o original
        out, k = [], 0
        for i, j, pt, _ in spans:
            out.extend(toks[k:i])
            out.append(pt)
            k = j
        out.extend(toks[k:])
        origin = "auto" if any(sp[3] == "auto" for sp in spans) else "manual"
        return " ".join(out), origin, spans

    def _known_words(self):
        """Palavras que e normal sairem iguais na traducao: nomes do glossario e termos mantidos em ingles."""
        words = set()
        for t in list(getattr(self.lib, "glossary", [])) + list(getattr(self.lib, "terms", {}).values()):
            words.update(w.lower() for w in WORD_RE.findall(t))
        return words

    def _already_portuguese(self, text):
        """Texto de tela que ja esta em portugues sem acento ("Modo de voo", "Pegar metade SHIFT", "Voltar"):
        quem joga com o Hytale em portugues tem os menus do proprio jogo assim, e eles iam para a traducao
        como se fossem ingles. Portugues = a maioria das palavras so aparece nas traducoes da biblioteca,
        nunca nos textos em ingles dela."""
        vocab = getattr(self, "_pt_vocab", None)
        if vocab is None:
            pt, en = set(_PT_WORDS), set()
            for k, v in list(getattr(self.lib, "seed", {}).items()):
                if isinstance(v, dict) and isinstance(v.get("pt"), str):
                    en.update(w.lower() for w in WORD_RE.findall(k))
                    pt.update(w.lower() for w in re.findall(r"[^\W\d_]{2,}", v["pt"]))
            vocab = self._pt_vocab = pt - en - self._known_words()
        words = [w.lower() for w in WORD_RE.findall(text) if len(w) >= 2 and not w.isupper()]
        if not words:
            return False
        hits = sum(w in vocab for w in words)
        return hits >= 1 and hits / len(words) >= 0.6

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
            if not looks_translatable(text) or self._already_portuguese(text):
                return
            rec = self.seen.get(key)
            if rec is None or now - rec[1] > FORGET_SECONDS:
                self.seen[key] = [now, now]
                return
            rec[1] = now
            online = getattr(self.mt, "online", None) is not None
            if now - rec[0] < (STABLE_ONLINE if online else STABLE_SECONDS) or self.q.qsize() >= MAX_QUEUE:
                return
            del self.seen[key]
            self.pending.add(key)
        self.q.put((key, text, True))

    def _queue_chat(self, text):
        """Mensagem de chat vai para a fila na hora (sem esperar duas leituras: o chat anda rapido).
        Mensagem curta vai so para a traducao offline: nao vale gastar a cota online com "rip mine"."""
        if not self.cfg.get("traduzir_desconhecidos", True) or not self._mt_ok():
            return
        key = normalize(text)
        with self._lock:
            if not key or key in self.pending or key in self.failed or key in self.chat:
                return
            self.pending.add(key)
        self.q.put((key, text, "offline" if len(text.split()) <= SHORT_CHAT else False))

    def _slang(self, msg):
        """Mensagem feita so de girias ("ty", "lol gg", "brb") -> traducao pronta, sem fila."""
        words = re.findall(r"[a-z']+", msg.lower())
        slang = getattr(self.lib, "slang", {})
        if not words or len(words) > 4 or not all(w in slang for w in words):
            return None
        if re.sub(r"[a-z'\s!?.,:)(3<>^_-]", "", msg.lower()):
            return None  # tem numero ou outra coisa no meio
        out = " ".join(p for p in (slang[w] for w in words) if p)
        return out if out and out.lower() != " ".join(words) else None

    def _prune(self):
        now = time.monotonic()
        if now - self._last_prune < 5:
            return
        self._last_prune = now
        with self._lock:
            for k in [k for k, rec in self.seen.items() if now - rec[1] > FORGET_SECONDS]:
                del self.seen[k]

    def _name_then_phrase(self, text):
        """Nome de jogador + frase da biblioteca: "Kwaxu has joined", "[From Jm_Az (NA Hub)] started a
        conversation with you...". Traduz so a frase; o nome fica com os pixels do jogo. Sem isso, cada
        nome novo era uma frase nova para a traducao automatica (e gastava a cota online)."""
        toks = text.split()
        for k in range(1, min(5, len(toks) - 1) + 1):
            rest = " ".join(toks[k:])
            if len(toks) - k < 2 and not rest.endswith((".", "!")):
                continue
            if not self.lib.knows_reviewed(rest):
                continue
            head = toks[:k]
            nameish = any(re.search(r"[\d_\[\]()]", t) or (t[:1].isalpha() and any(c.isupper() for c in t[1:]))
                          or (self.unknown_word(t.strip(".,:")) if t[:1].isalpha() else False) for t in head)
            if not nameish:
                continue
            hit = self.lib.lookup(rest, 100)
            if not hit or hit[0] == rest:
                return None
            return " ".join(head + [hit[0]]), hit[1], [(k, len(toks), hit[0], hit[1])]
        return None

    def _garbled_name(self, text):
        """Nome do glossario lido com erro pelo OCR, sozinho ou com "(coming soon)": "EVE' RR@OT FOREST",
        "MO MO RI WILDS". Com o erro ele nao batia com o nome, e "FOREST" virava "floresta" no meio do nome."""
        key = re.sub(r"[^a-z]", "", re.sub(r"\([^)]*\)?\s*$", "", text).lower())
        if len(key) < 8 or len(key) > 40:
            return False
        names = getattr(self, "_name_keys", None)
        gl = getattr(self.lib, "glossary", [])
        if names is None or self._name_src is not gl:
            self._name_src = gl
            names = self._name_keys = {re.sub(r"[^a-z]", "", n.lower()) for n in gl if " " in n.strip()}
            names = self._name_keys = [n for n in names if len(n) >= 8]
        if not names:
            return False
        from rapidfuzz import fuzz, process
        hit = process.extractOne(key, names, scorer=fuzz.ratio, score_cutoff=86)
        return bool(hit)

    def _one(self, text, allow_mt=True, parts=True, title=False):
        if title == "name" or self._garbled_name(text):
            return None  # nome com etiqueta embaixo (guilda "DAMAGE" / "[DMG]"): nem a biblioteca traduz
        chat = chat_split(text) if allow_mt else None
        if chat:
            k, msg = chat
            pt, origin = self._slang(msg), "manual"  # "ty", "lol gg": pronto, sem fila e sem cota
            if not pt and (looks_portuguese(msg) or not looks_translatable(msg)):
                return None
            if not pt:
                hit = self.lib.lookup(msg, 92)
                pt, origin = (hit[0], hit[1]) if hit else (self.chat.get(normalize(msg)), "auto")
            if not pt:
                self._queue_chat(msg)
                return None
            toks = text.split()
            return " ".join(toks[:k] + [pt]), origin, [(k, len(toks), pt, origin)]
        named = self._name_then_phrase(text)
        if named:
            return named
        exact = self.lib.knows_reviewed(text)  # a memoria automatica nao passa na frente do "por partes"
        hit = self.lib.lookup(text, self.cfg.get("similaridade_minima", 86)) if exact else None
        if hit:
            return hit[0], hit[1]
        if title:
            return None  # titulo de card de skill/item: nome proprio, fica em ingles
        # por partes ANTES do "parecido": em "You Buy 12s" so "You Buy" e coberto; o preco e a moeda
        # ficam com os pixels do jogo (o parecido cobria a linha toda e redesenhava "12S")
        r = self.compose(text) if parts else None
        if r:
            return r  # (traducao, origem, trechos)
        hit = self.lib.lookup(text, self.cfg.get("similaridade_minima", 86))
        if hit:
            return hit[0], hit[1]
        if not allow_mt:
            return None
        if self.is_name(text) or is_noise(text, self.unknown_word):
            return None  # nome proprio ou nome de jogador: fica em ingles, sem caixa por cima
        self._maybe_queue(text)
        return None

    def _chat_pt(self, msg):
        """Traducao de uma mensagem de chat: (texto, origem), ou None (ja e portugues, ou foi para a fila)."""
        pt, origin = self._slang(msg), "manual"  # "ty", "lol gg": pronto, sem fila e sem cota
        if pt:
            return pt, origin
        if looks_portuguese(msg) or not looks_translatable(msg):
            return None
        hit = self.lib.lookup(msg, 92)
        if hit:
            return hit[0], hit[1]
        pt = self.chat.get(normalize(msg))
        if pt:
            return pt, "auto"
        self._queue_chat(msg)
        return None

    @staticmethod
    def _chat_blocks(lines):
        """Mensagens do chat: a linha com "canal nome:" e as linhas logo abaixo em que a mensagem continua.
        Separadas antes de montar paragrafos: com a mesma cor e altura, o chat inteiro virava um paragrafo
        so, que ia junto para a traducao automatica ("Minnie420: ... G (NA-HUB) Skyzzl: ...")."""
        rows = sorted(lines, key=lambda l: (l["y"], l["x"]))
        blocks, used = [], set()
        for i, ln in enumerate(rows):
            if id(ln) in used or not chat_split(ln["text"]):
                continue
            blk = [ln]
            used.add(id(ln))
            for nx in rows[i + 1:]:
                last = blk[-1]
                gap = nx["y"] - (last["y"] + last["h"])
                if gap > last["h"] * 0.9:
                    break
                if (id(nx) in used or gap < -last["h"] * 0.3 or chat_split(nx["text"])
                        or abs(nx["x"] - ln["x"]) > ln["h"] * 3 or not 0.75 < nx["h"] / ln["h"] < 1.33):
                    continue
                if _OTHER_SPEAKER.match(nx["text"]):
                    break  # "jenin: ...", "[Copper] Semedar: ...": outra pessoa falando, nao e continuacao
                blk.append(nx)
                used.add(id(nx))
            blocks.append(blk)
        return blocks, used

    def _chat_zone_lines(self, lines, blocks, used):
        """Linhas que estao na coluna do chat mas nao tem cara de mensagem ("Kwaxu has joined", "jenin: rip",
        "[Copper] Semedar: ...", um pedaco de mensagem que o OCR separou). Sem isto elas eram tratadas como
        texto de tela: traduzidas sem o mouse em cima, andando pelo mundo, e ainda iam para a memoria
        compartilhada. A coluna e achada pelas mensagens reconhecidas (mesma margem esquerda, mesma altura
        de letra, uma linha colada na outra) e fica lembrada: andando pelo mundo (sem cursor) ela vale mesmo
        quando nenhuma linha da leitura tem "canal nome:". Com o cursor visivel pode haver um menu aberto,
        entao so entram as linhas do meio/fim da pilha de mensagens reconhecidas."""
        heads = [b[0] for b in blocks]
        now = time.monotonic()
        zone = self._zone
        # o chat do Runeteria fica sempre no mesmo lugar: lado esquerdo, do meio da tela para baixo (medido
        # numa captura 1920x1015: x 45-515, y 295-775). Em fracoes da ALTURA da janela, com folga, para
        # valer em qualquer resolucao e proporcao (a interface do jogo acompanha a altura)
        region = None
        if self.view:
            vh = self.view[1]

            def region(l):
                return l["x"] < vh * 0.53 and vh * 0.27 < l["y"] + l["h"] / 2 < vh * 0.79
        if region and self.pointer is None:
            # andando pelo mundo nao ha menu aberto: tudo que esta nesse lugar e chat, sem excecao
            return [l for l in lines if id(l) not in used and region(l)]
        if heads:
            h = sorted(l["h"] for l in heads)[len(heads) // 2]
            x = min(l["x"] for l in heads)
            members = [l for b in blocks for l in b]
        elif zone and self.pointer is None and now - zone["t"] < CHAT_ZONE_KEEP:
            h, x, members = zone["h"], zone["x"], []
        else:
            return []
        cand = [l for l in lines if id(l) not in used and (region is None or region(l))
                and x - h <= l["x"] <= x + 3 * h and 0.75 < l["h"] / h < 1.33]
        out = []
        if not heads:  # sem mensagem reconhecida: parte do lugar onde o chat estava
            out = [l for l in cand if zone["y0"] - 2 * h <= l["y"] <= zone["y1"] + 2 * h]
            members = list(out)
            cand = [l for l in cand if not any(l is o for o in out)]
        # sem saber o tamanho da janela, com o cursor visivel so vale da primeira mensagem para baixo
        top = min(l["y"] for l in heads) - h * 0.5 if heads and self.pointer is not None and not region else None
        grew = bool(members)
        while grew and cand:
            grew = False
            for l in list(cand):
                if top is not None and l["y"] < top:
                    continue
                if any(max(l["y"] - (m["y"] + m["h"]), m["y"] - (l["y"] + l["h"])) <= h * 1.6 for m in members):
                    members.append(l)
                    out.append(l)
                    cand.remove(l)
                    grew = True
        if heads:
            self._zone = {"x": x, "h": h, "t": now, "y0": min(l["y"] for l in members),
                          "y1": max(l["y"] + l["h"] for l in members)}
        return out

    def _hovered(self, blk):
        if not self.pointer:
            return False
        px, py = self.pointer
        x0 = min(l["x"] for l in blk) - blk[0]["h"]
        x1 = max(l["x"] + l["w"] for l in blk) + blk[0]["h"] * 2
        y0 = blk[0]["y"] - blk[0]["h"] * 0.4
        y1 = max(l["y"] + l["h"] for l in blk) + blk[0]["h"] * 0.4
        return x0 <= px <= x1 and y0 <= py <= y1

    def boxes(self, lines):
        """Devolve [{'x','y','w','h','line_h','pt','origin','en'}]."""
        self._prune()
        lines = join_known(lines, self.lib.knows)
        out = []
        chat_blocks, chat_ids = self._chat_blocks(lines)
        chat_loose = self._chat_zone_lines(lines, chat_blocks, chat_ids)  # na coluna do chat, sem "canal nome:"
        chat_ids = chat_ids | {id(l) for l in chat_loose}
        if chat_ids:
            lines = [l for l in lines if id(l) not in chat_ids]

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
                # centralizado com um lado bloqueado (icone colado, borda): cresce so para o lado livre
                if d["align"] == "center" and d["room_l"] < first["h"] and d["room_l"] * 4 < d["room_r"]:
                    d["align"] = "left"
                elif d["align"] == "center" and d["room_r"] < first["h"] and d["room_r"] * 4 < d["room_l"]:
                    d["align"] = "right"
            return d

        # chat: so a mensagem sob o cursor, e so com o cursor visivel (chat aberto). Andando pelo mundo o
        # chat fica em ingles e nao gasta nada; quem quer ler passa o mouse em cima
        for blk in chat_blocks:
            if not self._hovered(blk):
                continue
            k, first_msg = chat_split(blk[0]["text"])
            msg = " ".join([first_msg] + [l["text"] for l in blk[1:]])
            r = self._chat_pt(msg)
            if not r:
                continue
            pt, origin = r
            first = blk[0]
            if len(blk) == 1:
                toks = first["text"].split()
                pieces = self._span_boxes(first, (" ".join(toks[:k] + [pt]), origin, [(k, len(toks), pt, origin)]),
                                          box, "left")
                if pieces:
                    for p in pieces:
                        p["chat"] = True
                    out.extend(pieces)
                    continue
            geo = {"x": min(l["x"] for l in blk), "y": first["y"],
                   "w": max(l["x"] + l["w"] for l in blk) - min(l["x"] for l in blk),
                   "h": blk[-1]["y"] + blk[-1]["h"] - first["y"], "lines": blk}
            prefix = " ".join(first["text"].split()[:k])
            d = box(geo, first, prefix + " " + pt, origin, " ".join(l["text"] for l in blk), "left", len(blk))
            d["chat"] = True
            out.append(d)
        for ln in chat_loose:  # aviso ou pedaco de mensagem na coluna do chat: mesma regra, so sob o mouse
            if not self._hovered([ln]):
                continue
            r = self._name_then_phrase(ln["text"])  # "Kwaxu has joined": so a frase, o nome fica
            pieces = self._span_boxes(ln, r, box, "left") if r else None
            if not pieces:
                r = self._chat_pt(ln["text"])  # vai como chat: nunca para a memoria compartilhada
                pieces = [box(ln, ln, r[0], r[1], ln["text"], "left", 1)] if r else []
            for p in pieces:
                p["chat"] = True
            out.extend(pieces)

        titles = self._card_titles(lines)
        for b in group_blocks(lines):
            multi = len(b["lines"]) > 1
            full = " ".join(l["text"] for l in b["lines"])
            r = self._one(full, allow_mt=False, parts=False) if multi else None  # paragrafo inteiro: so biblioteca
            if r:
                out.append(box(b, b["lines"][0], r[0], r[1], full, block_align(b["lines"]), len(b["lines"])))
                continue
            hits = 0
            for ln in b["lines"]:
                if ln.get("cut"):
                    continue  # o OCR pegou so um pedaco da palavra: melhor nao traduzir
                row = [] if self.lib.knows(ln["text"]) else self._label_row(ln, box, lines)
                if row:  # abas lidas juntas: cada rotulo no seu lugar, sem traducao automatica
                    hits += 1
                    out.extend(row)
                    continue
                r = self._one(ln["text"], allow_mt=not multi, title=titles.get(id(ln), False))
                if not r:
                    continue
                hits += 1
                pieces = self._span_boxes(ln, r, box, guess_align(ln, lines)) if len(r) > 2 else None
                if pieces is not None:
                    out.extend(pieces)
                else:
                    out.append(box(ln, ln, r[0], r[1], ln["text"], guess_align(ln, lines), 1))
            if multi and hits == 0:
                self._one(full)  # paragrafo desconhecido: traduz inteiro em segundo plano
        # traducao igual ao original nao precisa de caixa por cima
        return [o for o in out if o["pt"].strip() != o["en"].strip()]

    @staticmethod
    def _card_titles(lines):
        """Linhas que sao titulo de card de skill/item: logo acima vem uma linha de atributo que comeca
        com numero ("Hemorrhage" em cima de "145 damage · 7.7s"). O titulo e nome proprio, mesmo quando
        e uma palavra inglesa comum - entao fica em ingles."""
        out = {}  # id da linha -> True (titulo de card) ou "name" (nome com etiqueta)
        for t in lines:
            words = t["text"].split()
            if words and any(m is not t and m["text"].startswith("[")
                             and 0 <= m["y"] - (t["y"] + t["h"]) < t["h"] * 1.6
                             and abs((m["x"] + m["w"] / 2) - (t["x"] + t["w"] / 2)) < t["h"] * 6
                             for m in lines):
                out[id(t)] = "name"  # nome com a etiqueta embaixo ("DAMAGE" sobre "[DMG] - PVP & PVE")
                continue
            if not words or t["text"].isupper() or not all(w[:1].isupper() for w in words if w[:1].isalpha()):
                continue
            for m in lines:
                toks = m["text"].split()
                if m is t or not toks or not (re.match(r"[+\-]?\d", toks[0]) and is_value_token(toks[0])):
                    continue
                if 0 <= m["y"] - (t["y"] + t["h"]) < t["h"] * 1.6 and abs(m["x"] - t["x"]) < t["h"] * 2.5:
                    out[id(t)] = True
                    break
        return out

    def _label_row(self, ln, box, lines):
        """Fileira de rotulos que o OCR leu como uma linha so ("PROFESSIONS CLASSES PARTY", as abas do
        topo): se cada palavra e um rotulo conhecido, cada uma ganha sua caixa. Sem isso, a frase inteira
        ia para a traducao automatica e saia "CLASSES DE PROFISSOES GRUPO"."""
        words = ln.get("words")
        if not words or len(words) < 2 or [w["text"] for w in words] != ln["text"].split():
            return []
        # rotulos separados tem vao grande entre eles; numa frase ("Max level") o vao e de um espaco
        gaps = [b["x"] - (a["x"] + a["w"]) for a, b in zip(words, words[1:])]
        if min(gaps) < ln["h"] * 1.2:
            return []
        hits = [self.lib.lookup(w["text"], 100) if not is_value_token(w["text"]) else None for w in words]
        if sum(1 for h in hits if h) < 2 or any(h is None and not is_value_token(w["text"])
                                                 for h, w in zip(hits, words)):
            return []
        out = []
        for i, (w, hit) in enumerate(zip(words, hits)):
            if not hit or hit[0] == w["text"]:
                continue
            d = box(w, ln, hit[0], hit[1], w["text"], "center", 1)
            d["ref"] = (w["text"], w["w"])
            d["room_l"] = w["x"] - (words[i - 1]["x"] + words[i - 1]["w"]) if i > 0 else ln.get("room_l", 0)
            d["room_r"] = (words[i + 1]["x"] - (w["x"] + w["w"])) if i + 1 < len(words) else ln.get("room_r", 0)
            out.append(d)
        return out

    @staticmethod
    def _span_boxes(ln, r, box, line_align="left"):
        """Linha montada por partes: caixas so em cima dos trechos traduzidos.

        Cada trecho absorve os vizinhos que podem ser redesenhados sem risco - separador (· • - /),
        tecla (Q, E, R) e numero inteiro - e trechos separados so por eles viram uma caixa so:
        "530 damage · full signature" -> uma caixa "530 dano · signature completa".
        Valores como "8.6s" e nomes ficam com os pixels do jogo (o OCR pode ter lido "8.65").
        None se nao der para saber onde fica cada palavra.
        """
        words = ln.get("words")
        toks = ln["text"].split()
        if not words or [w["text"] for w in words] != toks:
            return None

        hs = sorted(w["h"] for w in words)
        hmed = hs[(len(hs) - 1) // 2]

        def safe(k):
            """Vizinho que pode ser redesenhado: separador, tecla, numero inteiro. Com altura de letra:
            icone de moeda lido como "0" ou seta lida como "-5" sao mais altos/baixos e ficam de fora."""
            t = toks[k]
            if t in ("•", "·", "|", "-", "/"):
                return True
            if not 0.6 * hmed <= words[k]["h"] <= 1.3 * hmed:
                return False
            # "O" e "I" sozinhos podem ser 0 e 1 mal lidos ("3 dungeons 0 available"): nao redesenha
            return (len(t) == 1 and t.isupper() and t not in "OI") or bool(re.fullmatch(r"\d+%?", t))

        repl = {}  # primeira palavra do trecho -> (fim, traducao, origem)
        for i, j, pt, origin in r[2]:
            repl[i] = (j, pt, origin)
        groups, k = [], 0
        starts = sorted(repl)
        used = set()
        for st in starts:
            if st in used:
                continue
            gi = st
            while gi > 0 and safe(gi - 1) and not any(gi - 1 in range(a, repl[a][0]) for a in repl):
                gi -= 1
            gj, origins = repl[st][0], {repl[st][2]}
            used.add(st)
            while gj < len(toks):
                if gj in repl:
                    origins.add(repl[gj][2])
                    used.add(gj)
                    gj = repl[gj][0]
                elif safe(gj):
                    gj += 1
                else:
                    break
            # separador solto na ponta nao precisa ser coberto
            while gj > gi and toks[gj - 1] in ("•", "·", "|", "-", "/") and gj - 1 not in repl:
                gj -= 1
            groups.append((gi, gj, "auto" if "auto" in origins else "manual"))
        out = []
        for gi, gj, origin in groups:
            pieces, t = [], gi
            while t < gj:
                if t in repl:
                    pieces.append(repl[t][1])
                    t = repl[t][0]
                else:
                    pieces.append(toks[t])
                    t += 1
            ws = words[gi:gj]
            x = ws[0]["x"]
            geo = {"x": x, "y": ln["y"], "w": ws[-1]["x"] + ws[-1]["w"] - x, "h": ln["h"]}
            whole = gi == 0 and gj == len(toks)  # cobre a linha toda: cresce para o lado certo
            d = box(geo, ln, " ".join(pieces), origin, " ".join(toks[gi:gj]), line_align if whole else "left", 1)
            d["ref"] = (ln["text"], ln["w"])  # a fonte e medida na linha inteira (mesma fonte)
            if not whole:
                # a altura vem so das palavras do trecho: a linha pode ter icone mais alto que as letras
                # (moeda) ou outro texto de outro tamanho, e a traducao sairia desse tamanho
                top = min(w["y"] for w in ws)
                d["iy"], d["ih"] = top, max(w["y"] + w["h"] for w in ws) - top
                d["line_h"] = d["ih"]
                d["ref"] = (" ".join(w["text"] for w in ws), geo["w"])
                # a familia da fonte e a da linha inteira (um trecho curto nao tem largura para decidir)
                d["line_ref"] = (ln["text"], ln["w"], ln.get("ih", ln["h"]), ln.get("ink"))
                d.pop("ink", None)
            # espaco ate a proxima palavra (que continua aparecendo); no fim, o espaco livre da linha
            d["room_r"] = (words[gj]["x"] - (geo["x"] + geo["w"]) if gj < len(words) else ln.get("room_r", 0))
            d["room_l"] = (x - (words[gi - 1]["x"] + words[gi - 1]["w"]) if gi > 0 else ln.get("room_l", 0))
            d["inline"] = True
            out.append(d)
        rest = [t for k, t in enumerate(toks) if not any(gi <= k < gj for gi, gj, _ in groups)]
        if len(groups) == 1 and rest and not any(re.search(r"\d", t) for t in rest):
            # "BUY 1 BOOMSHROOM PLAGUE F...": o resto e so nome (sem numeros para o OCR errar)
            alt = box(ln, ln, r[0], r[1], ln["text"], line_align, 1)
            out[0]["alt"] = alt
        return out
