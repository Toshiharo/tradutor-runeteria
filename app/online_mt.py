"""Traducao online (servidor do projeto no Cloudflare, que usa o DeepL e guarda uma memoria compartilhada).

So e usada para texto que nao esta na biblioteca. Se o servidor nao responder, o app usa a traducao
offline na hora, e fica 60 s sem tentar de novo. Envia so o texto em ingles do jogo (ja com nomes e
termos fixos trocados por marcadores); nada do computador do jogador.
"""
import html
import json
import re
import time
import urllib.request

from config import APP_VERSION

TIMEOUT = 4.0
RETRY_AFTER = 60.0
_MARK = re.compile(r"Zq\s?(\d+)\s?x", re.I)
_TAG = re.compile(r"<k>\s*Z(\d+)\s*</k>")
_NUM_TAG = re.compile(r"<k>\s*N(\d+)\s*</k>")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


class OnlineMT:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self._down_until = 0.0
        self.last_error = None

    def available(self):
        return bool(self.url) and time.monotonic() >= self._down_until

    @staticmethod
    def _wrap(text):
        """Texto para o servidor (XML do DeepL): marcadores e numeros vao dentro de <k>, que ele nao traduz.
        Numeros viram N0, N1...: "Level 10" e "Level 11" sao um texto so na memoria compartilhada (paga
        uma vez). Devolve (texto, numeros)."""
        nums = []
        parts = []
        for k, piece in enumerate(re.split(r"(Zq\s?\d+\s?x)", text, flags=re.I)):
            if k % 2:
                parts.append("<k>Z%s</k>" % re.sub(r"\D", "", piece))  # curto: cada caractere conta
                continue

            def num(m):
                nums.append(m.group(0))
                return "\x00%d\x00" % (len(nums) - 1)
            piece = html.escape(_NUM.sub(num, piece), quote=False)
            parts.append(re.sub("\x00(\\d+)\x00", lambda m: "<k>N%s</k>" % m.group(1), piece))
        return "".join(parts), nums

    @staticmethod
    def _unwrap(text, nums=()):
        def num(m):
            i = int(m.group(1))
            return nums[i] if i < len(nums) else m.group(0)
        return html.unescape(_NUM_TAG.sub(num, _TAG.sub(lambda m: "Zq%sx" % m.group(1), text)))

    def raw(self, texts, keep_flags=None):
        """Traduz textos ja protegidos. Devolve uma lista (None onde falhou) ou levanta erro se o
        servidor nao respondeu (aí quem chamou usa a traducao offline)."""
        if not self.available():
            raise OSError("servidor de traducao indisponivel")
        wrapped = [self._wrap(t) for t in texts]
        body = {"textos": [w for w, _ in wrapped]}
        if keep_flags is not None:
            body["guardar"] = [bool(k) for k in keep_flags]
        req = urllib.request.Request(self.url + "/traduzir", data=json.dumps(body).encode("utf-8"), headers={
            "Content-Type": "application/json", "User-Agent": f"tradutor-runeteria/{APP_VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            self.last_error = str(e)
            self._down_until = time.monotonic() + RETRY_AFTER
            raise
        outs = data.get("traducoes")
        if not isinstance(outs, list) or len(outs) != len(texts):
            self._down_until = time.monotonic() + RETRY_AFTER
            raise OSError("resposta invalida do servidor")
        res = []
        for o, (_, nums) in zip(outs, wrapped):
            if not isinstance(o, str):
                res.append(None)
                continue
            back = self._unwrap(o, nums)
            res.append(None if "<k>" in back else back)  # sobrou marcador estragado: usa a offline
        return res
