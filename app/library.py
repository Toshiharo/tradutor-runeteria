"""Biblioteca de traducoes: garante que o mesmo texto sempre tem a mesma traducao.

Prioridade: minhas_traducoes.json (voce) > biblioteca.json (revisada) > memoria_automatica.json
"""
import re
import threading
import time

from rapidfuzz import fuzz, process

from config import (MEMORY_FILE, ONLINE_GLOSSARY, ONLINE_LIBRARY, SEED_GLOSSARY, SEED_LIBRARY,
                    USER_GLOSSARY, USER_OVERRIDES, read_json, write_json)

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
        online = read_json(ONLINE_LIBRARY, {})
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
        online = read_json(ONLINE_GLOSSARY, {})
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

    def _find(self, key, min_score):
        """(entrada, score) pela chave normalizada: exato primeiro, depois parecido (erros do OCR)."""
        hit = self.index.get(key)
        if hit is not None:
            return hit, 100
        if len(key) < 5:
            return None
        ck = (key, min_score)
        if ck in self._fuzzy_cache:  # a mesma tela e consultada a cada ~0,8 s
            return self._fuzzy_cache[ck]
        # texto curto: uma letra a mais/menos muda o sentido (Skill/Skills), entao exige mais
        cutoff = max(min_score, 92) if len(key) < 8 else min_score
        found = None
        res = process.extractOne(key, self.keys_long, scorer=fuzz.ratio, score_cutoff=cutoff)
        # quantidade de numeros diferente = outro texto (e os numeros da tela nao encaixariam)
        if res and res[0].count("#") == key.count("#"):
            found = (self.index[res[0]], res[1])
        if len(self._fuzzy_cache) > 5000:
            self._fuzzy_cache.clear()
        self._fuzzy_cache[ck] = found
        return found

    def lookup(self, text, min_score=86):
        """Devolve (traducao, origem, score) ou None."""
        key = normalize(text)
        if len(key) < 2 or not re.search(r"[a-z]{2}", key):
            return None
        with self.lock:
            found = self._find(key, min_score)
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
                               "data": time.strftime("%Y-%m-%d")}
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
