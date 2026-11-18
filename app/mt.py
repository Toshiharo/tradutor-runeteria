"""Traducao automatica 100% offline (modelo Argos en->pt rodando com CTranslate2).

So e usada para textos que NAO estao na biblioteca. Tudo que ela traduz vai para
memoria_automatica.json, entao o mesmo texto recebe sempre a mesma traducao.
"""
import os
import re
import threading

PH_FMT = "Zq{}x"
PH_RE = re.compile(r"Zq\s?(\d+)\s?x", re.I)
SPACE_RE = re.compile(r"\s+")


_TU = {"tens": "tem", "podes": "pode", "queres": "quer", "precisas": "precisa", "estás": "está", "és": "é"}

# O modelo Argos mistura portugues de Portugal. Troca o que e claramente pt-PT pelo pt-BR.
# (regex, substituicao) - a caixa do original e mantida (ALUGUER -> ALUGUEL, Aluguer -> Aluguel)
_PTBR = [(re.compile(p, re.I), r) for p, r in [
    # "esta a comprar" -> "esta comprando"
    (r"\b(est(?:á|ão|ou|ava|avam|amos|ás)|estar|continua(?:m)?|fic(?:a|am|ou)) a (\w+?)(a|e|i)r\b", r"\1 \2\3ndo"),
    # "ainda nao tens" -> "voce ainda nao tem"
    (r"\b((?:ainda |já )?(?:não |nunca )?)(tens|podes|queres|precisas|estás|és)\b",
     lambda m: "você " + m.group(1).lower() + _TU[m.group(2).lower()]),
    (r"\b(?:o |a )?teu(s?)\b", r"seu\1"), (r"\b(?:o |a )?tua(s?)\b", r"sua\1"),
    (r"\bcontigo\b", "com você"), (r"\bpara ti\b", "para você"), (r"\bde ti\b", "de você"),
    (r"\bpor si\b", "por você"), (r"\bconnosco\b", "conosco"),
    (r"\baluguer(es)?\b", lambda m: "aluguéis" if m.group(1) else "aluguel"),
    (r"\becrã(s?)\b", r"tela\1"), (r"\bficheiro(s?)\b", r"arquivo\1"), (r"\butilizador(es)?\b", r"usuário\1"),
    (r"\bstock(s?)\b", r"estoque\1"), (r"\bexistências\b", "estoque"), (r"\bantevisão\b", "prévia"),
    (r"\bregisto(s?)\b", r"registro\1"), (r"\bpalavra-passe\b", "senha"), (r"\bsítio(s?)\b", r"local\1"),
    (r"\bcontact(\w+)", r"contat\1"), (r"\bpartilh(\w+)", r"compartilh\1"), (r"\bgravar\b", "salvar"),
    (r"\bapagar\b", "excluir"), (r"\bpára\b", "para"), (r"\bcasa de banho\b", "banheiro"),
    (r"\bequipamentos? desportivos?\b", "equipamento esportivo"), (r"\bdesport(\w+)", r"esport\1"),
    # ortografia antiga: accao, actualizar, seleccionar, objecto, optimo, direccao...
    (r"\bactu(\w+)", r"atu\1"), (r"\bactiv(\w+)", r"ativ\1"),
    (r"\b(a|dire|sele|cole|corre|prote|proje|inje|obje|rea|inspe|fra|abstra)cç(ão|ões)\b", r"\1ç\2"),
    (r"\b(a|dire|sele|cole|corre|inspe|fra)ccion(\w+)", r"\1cion\2"),
    (r"\b(ob|pro|tra|in)ject(\w+)", r"\1jet\2"), (r"\b(efe|ele|dire|corre|exa|a)ct(\w+)", r"\1t\2"),
    (r"\bóptim(\w+)", r"ótim\1"), (r"\bfacto(s?)\b", r"fato\1"), (r"\bsecç(\w+)", r"seç\1"),
]]


def _keep_case(src, new):
    if src.isupper() and len(src) > 1:
        return new.upper()
    if src[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


def to_ptbr(text):
    for pat, rep in _PTBR:
        text = pat.sub(lambda m, rep=rep: _keep_case(m.group(0), rep(m) if callable(rep) else m.expand(rep)), text)
    return text


class OfflineTranslator:
    def __init__(self, model_dir, glossary):
        self.ok = False
        self.error = None
        self.glossary = glossary  # lista ordenada (maiores primeiro)
        self._lock = threading.Lock()
        try:
            import ctranslate2
            import sentencepiece as spm
            ct_dir, sp_path = self._find_model(model_dir)
            self.translator = ctranslate2.Translator(ct_dir, device="cpu", compute_type="int8",
                                                     inter_threads=1, intra_threads=2)
            self.sp = spm.SentencePieceProcessor(model_file=sp_path)
            self.ok = True
        except Exception as e:  # sem modelo: o app continua so com a biblioteca
            self.error = str(e)

    @staticmethod
    def _find_model(root):
        ct_dir = sp_path = None
        for dirpath, _, files in os.walk(root):
            if "model.bin" in files and ct_dir is None:
                ct_dir = dirpath
            if "sentencepiece.model" in files and sp_path is None:
                sp_path = os.path.join(dirpath, "sentencepiece.model")
        if not ct_dir or not sp_path:
            raise FileNotFoundError(f"Modelo de traducao nao encontrado em {root}")
        return ct_dir, sp_path

    # ---------- protecao do glossario ----------
    def _protect(self, text):
        found = []
        out = text
        for term in self.glossary:
            pat = re.compile(r"(?<![\w])" + re.escape(term) + r"(?![\w])", re.I)

            def rep(m):
                found.append(m.group(0))
                return PH_FMT.format(len(found) - 1)
            out = pat.sub(rep, out)
        return out, found

    @staticmethod
    def _restore(text, found):
        used = set()

        def rep(m):
            i = int(m.group(1))
            if i < len(found):
                used.add(i)
                return found[i]
            return m.group(0)
        out = PH_RE.sub(rep, text)
        return out, len(used) == len(found)

    def _raw(self, texts):
        toks = [self.sp.encode(t, out_type=str) for t in texts]
        with self._lock:
            res = self.translator.translate_batch(toks, beam_size=3, max_decoding_length=256,
                                                  replace_unknowns=True)
        # junta as pecas na mao (como o Argos faz): o sp.decode deixa "▁" sobrando em pecas que ele nao conhece
        return [SPACE_RE.sub(" ", "".join(r.hypotheses[0]).replace("▁", " ")).strip() for r in res]

    def translate(self, text):
        if not self.ok:
            return None
        text = text.strip()
        if not text:
            return text
        original = text
        if text.isupper() and len(text) > 3:
            # o modelo erra muito com TUDO EM MAIUSCULAS ("SETTINGS" -> "CONSTITUICOES"):
            # traduz em caixa normal e devolve em maiusculas no fim
            text = text.capitalize()
        prot, found = self._protect(text)
        if found and not re.search(r"[A-Za-z]{2}", PH_RE.sub("", prot)):
            return original  # so termos do glossario: fica igual
        out = self._raw([prot])[0]
        out, complete = self._restore(out, found)
        if not complete:
            # o modelo "comeu" um termo protegido: traduz os pedacos entre os termos
            parts = re.split("(" + "|".join(re.escape(f) for f in found) + ")", text)
            pieces = []
            for p in parts:
                if p in found or not re.search(r"[A-Za-z]{2}", p):
                    pieces.append(p)
                else:
                    pieces.append(self._raw([p.strip()])[0])
            out = " ".join(s.strip() for s in pieces if s.strip())
        out = to_ptbr(out)
        # o modelo gosta de por ponto final em rotulo curto ("Look" -> "Olha.")
        if out.endswith(".") and not out.endswith("..") and original[-1] not in ".!?:;":
            out = out[:-1]
        if original.isupper():
            out = out.upper()
        return out
