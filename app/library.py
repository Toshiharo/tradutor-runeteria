"""Biblioteca de traducoes: garante que o mesmo texto sempre tem a mesma traducao.

Prioridade: minhas_traducoes.json (voce) > biblioteca.json (revisada) > memoria_automatica.json
"""
import difflib
import re
import threading
import time

from rapidfuzz import fuzz, process

from config import (MEMORY_FILE, ONLINE_GLOSSARY, ONLINE_LIBRARY, SEED_GLOSSARY, SEED_LIBRARY,
                    USER_GLOSSARY, USER_OVERRIDES, newer, read_json, write_json)

NUM_RE = re.compile(r"\d+(?:[.,]\d+)*%?")
SPACE_RE = re.compile(r"\s+")
EDGE_RE = re.compile(r"^[\s\-:•·|>*\[\](){}.,!?]+|[\s\-:•·|>*\[\](){}.,!?]+$")

# Confusoes comuns do OCR em fontes de jogo
OCR_FIX = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "|": "I"})


def normalize(text):
    t = text.translate(OCR_FIX).replace("\\n", " ").replace("\n", " ")
    t = SPACE_RE.sub(" ", t).strip()
    t = EDGE_RE.sub("", t)
    t = NUM_RE.sub("#", t)
    return t.lower()


def is_upper(text):
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 2 and sum(c.isupper() for c in letters) / len(letters) > 0.85


MEMORY_VERSION = 3  # memoria automatica gravada antes disto traduzia nomes e cards inteiros: e descartada


def _tok(t):
    return NUM_RE.sub("#", EDGE_RE.sub("", t.translate(OCR_FIX))).lower()


def _variable_like(span):
    """Pedaco com cara de valor de exemplo (nome de jogador/loja/item), nao de palavra comum.

    "Toshi's Forge & Armory", "Ver0420", "_Toshi", "Rene's Cottage" sim; "ITEM", "Max" nao: palavra comum
    que a traducao copia igual (ITEM, LOOT, PET) nao e variavel, e troca-la poria lixo na tela.
    """
    words = span.split()
    if re.search(r"[\d_'&]", span):
        return True
    return len(words) >= 2 and not span.isupper() and all(w[:1].isupper() for w in words)


def adapt(screen, en, pt, strict):
    """Ajusta a traducao de `en` (texto da biblioteca) para `screen` (o que esta na tela), ou None.

    So aceita diferencas que nao mudam o sentido:
    - erro do OCR numa palavra ("Currentbonus", "chancc") -> a traducao continua valendo;
    - parte variavel que a traducao copia igual (nome de jogador, de loja, de item): troca pelo da tela
      ("Branch #1 of Toshi's Forge" -> "... of Bob's Shop" muda tambem na traducao);
    - com `strict` (texto muito parecido), uma palavrinha a mais ou a menos.
    Qualquer outra diferenca -> None. Assim nunca aparece na tela um nome ou valor que nao e o do jogo.
    """
    from rapidfuzz import fuzz
    a, b = screen.split(), en.split()
    na, nb = [_tok(x) for x in a], [_tok(x) for x in b]
    out, changed = pt, 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, nb, na, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)
        if strict and op == "replace" and i2 - i1 == j2 - j1 and all(
                fuzz.ratio(x, y) >= 80 for x, y in zip(nb[i1:i2], na[j1:j2])):
            continue  # erro de leitura do OCR (so em texto quase identico: "Requires" nao e "REQUEST")
        core = EDGE_RE.sub("", " ".join(b[i1:i2]))
        new = EDGE_RE.sub("", " ".join(a[j1:j2]))
        if op == "replace" and _variable_like(core) and new and not NUM_RE.fullmatch(core):
            pos = out.lower().find(core.lower())
            if pos >= 0:  # a traducao copia esse pedaco igual: e variavel, troca pelo da tela
                out = out[:pos] + new + out[pos + len(core):]
                continue
        if strict and op in ("insert", "delete") and max(i2 - i1, j2 - j1) == 1 and \
                len(" ".join(b[i1:i2] or a[j1:j2])) <= 3:
            continue
        return None
    if changed > max(1, len(b) // 2):
        return None  # diferente demais para ser o mesmo texto
    return out


def refill_numbers(src_ocr, pt):
    """Coloca os numeros que apareceram na tela dentro da traducao."""
    nums = NUM_RE.findall(src_ocr)
    slots = NUM_RE.findall(pt)
    if nums and len(nums) == len(slots):
        it = iter(nums)
        return NUM_RE.sub(lambda m: next(it), pt)
    return pt


class Library:
    def __init__(self):
        self.lock = threading.RLock()
        self.seed = self._load_seed()
        self.memory = read_json(MEMORY_FILE, {})
        old = [k for k, v in self.memory.items()
               if v.get("source") == "auto-tela" and v.get("v", 1) < MEMORY_VERSION]
        for k in old:  # gravadas pela versao que ainda traduzia nomes de skill/item/jogador
            del self.memory[k]
        if old:
            write_json(MEMORY_FILE, self.memory)
        self.overrides = read_json(USER_OVERRIDES, None)
        if self.overrides is None:
            self.overrides = {"_leia": "Escreva aqui \"texto em ingles\": \"sua traducao\". Isto vence todas as outras traducoes."}
            write_json(USER_OVERRIDES, self.overrides)
        self.glossary = self._load_glossary()
        self._dirty = False
        self._last_save = time.time()
        self.rebuild()

    # ---------- carregamento ----------
    @staticmethod
    def _load_seed():
        """Biblioteca revisada: a que veio com o programa + a copia mais nova baixada do repositorio."""
        seed = read_json(SEED_LIBRARY, {})
        # a copia baixada so vale se for mais nova que a do programa (senao uma atualizacao do
        # programa, ou uma edicao local, seria desfeita por um download antigo)
        online = read_json(ONLINE_LIBRARY, {}) if newer(ONLINE_LIBRARY, SEED_LIBRARY) else {}
        if isinstance(online, dict):
            seed.update({k: v for k, v in online.items() if isinstance(v, dict) and isinstance(v.get("pt"), str)})
        return seed

    def reload_seed(self):
        """Chamado depois que online.sync_translations() baixou arquivos novos."""
        with self.lock:
            self.seed = self._load_seed()
            self.glossary = self._load_glossary()
            self.rebuild()

    def _load_glossary(self):
        seed = read_json(SEED_GLOSSARY, {})
        online = read_json(ONLINE_GLOSSARY, {}) if newer(ONLINE_GLOSSARY, SEED_GLOSSARY) else {}
        if isinstance(online, dict) and isinstance(online.get("manter_em_ingles"), list):
            seed = {"manter_em_ingles": list(seed.get("manter_em_ingles", [])) + online["manter_em_ingles"],
                    "termos_fixos": {**(seed.get("termos_fixos") or {}), **(online.get("termos_fixos") or {})}}
        g = seed.get("manter_em_ingles", [])
        user = read_json(USER_GLOSSARY, None)
        if user is None:
            write_json(USER_GLOSSARY, {
                "_leia": "manter_em_ingles: termos que nunca devem ser traduzidos. "
                         "termos_fixos: como a traducao automatica deve escrever um termo, ex. \"hotbar\": \"Hotbar\".",
                "manter_em_ingles": [], "termos_fixos": {}})
            user = {}
        # termos_fixos: {ingles: como escrever em portugues}; os do usuario vencem os do programa
        terms = {}
        for src in (seed, user):
            for en, pt in (src.get("termos_fixos") or {}).items():
                if isinstance(pt, str) and en.strip() and pt.strip():
                    terms[en.strip().lower()] = pt.strip()
        self.terms = terms
        g = list(g) + list(user.get("manter_em_ingles", []))
        return sorted({t for t in g if t.strip()}, key=len, reverse=True)

    def rebuild(self):
        with self.lock:
            index = {}
            for en, v in self.memory.items():
                index[normalize(en)] = (en, v["pt"], "auto")
            for en, v in self.seed.items():
                index[normalize(en)] = (en, v["pt"], "manual")
            for en, pt in self.overrides.items():
                if en.startswith("_") or not isinstance(pt, str):
                    continue
                index[normalize(en)] = (en, pt, "voce")
            index.pop("", None)
            self.index = index
            self.keys = list(index.keys())
            self.keys_long = [k for k in self.keys if len(k) >= 4]
            self._fuzzy_cache = {}

    def reload_user_files(self):
        with self.lock:
            self.overrides = read_json(USER_OVERRIDES, self.overrides)
            self.glossary = self._load_glossary()
            self.rebuild()

    # ---------- consulta ----------
    def knows(self, en):
        return normalize(en) in self.index

    def _candidates(self, key):
        """[(entrada, score)] parecidas com a chave, da mais parecida para a menos (guardado: a mesma
        tela e consultada varias vezes por segundo)."""
        if key in self._fuzzy_cache:
            return self._fuzzy_cache[key]
        found = []
        if len(key) >= 5:
            res = process.extract(key, self.keys_long, scorer=fuzz.ratio, limit=5, score_cutoff=70)
            # quantidade de numeros diferente = outro texto (e os numeros da tela nao encaixariam)
            found = [(self.index[k], sc) for k, sc, _ in res if k.count("#") == key.count("#")]
        if len(self._fuzzy_cache) > 5000:
            self._fuzzy_cache.clear()
        self._fuzzy_cache[key] = found
        return found

    def _find(self, text, key, min_score):
        """((en, pt, origem), score) para o texto da tela: exato, ou parecido com adapt() aprovando."""
        hit = self.index.get(key)
        if hit is not None:
            return hit, 100
        # texto curto: uma letra a mais/menos muda o sentido (Skill/Skills), entao exige mais
        strict_at = max(min_score, 92) if len(key) < 8 else min_score
        for (en, pt, origin), score in self._candidates(key):
            new = adapt(text, en, pt, score >= strict_at)
            if new is not None:
                return (en, new, origin), score
        return None

    def lookup(self, text, min_score=86):
        """Devolve (traducao, origem, score) ou None."""
        key = normalize(text)
        if len(key) < 2 or not re.search(r"[a-z]{2}", key):
            return None
        with self.lock:
            found = self._find(text, key, min_score)
        if found is None:
            return None
        (en, pt, origin), score = found
        pt = refill_numbers(text, pt)
        if is_upper(text):
            pt = pt.upper()
        elif pt.isupper() and len(pt) > 3:
            pt = pt[0] + pt[1:].lower()
        if pt.endswith(":") and not text.rstrip().endswith(":"):
            pt = pt[:-1]
        return pt, origin, score

    # ---------- memoria automatica ----------
    def add_auto(self, en, pt, source):
        en = en.strip()
        if not en or not pt:
            return
        with self.lock:
            if normalize(en) in self.index:
                return
            self.memory[en] = {"pt": pt, "source": source, "reviewed": False,
                               "data": time.strftime("%Y-%m-%d"), "v": MEMORY_VERSION}
            k = normalize(en)
            self.index[k] = (en, pt, "auto")
            self.keys.append(k)
            if len(k) >= 4:
                self.keys_long.append(k)
            self._fuzzy_cache.clear()  # um "nao achei" guardado pode ter virado acerto
            self._dirty = True
        self.save(force=False)

    def save(self, force=True):
        with self.lock:
            if not self._dirty:
                return
            if not force and time.time() - self._last_save < 10:
                return
            write_json(MEMORY_FILE, self.memory)
            self._dirty = False
            self._last_save = time.time()

    def stats(self):
        return {"revisadas": len(self.seed), "automaticas": len(self.memory),
                "suas": len([k for k in self.overrides if not k.startswith("_")])}
