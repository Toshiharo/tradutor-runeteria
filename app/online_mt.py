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
_TAG = re.compile(r"<k>\s*(Zq\s?\d+\s?x)\s*</k>", re.I)


class OnlineMT:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self._down_until = 0.0
        self.last_error = None

    def available(self):
        return bool(self.url) and time.monotonic() >= self._down_until

    @staticmethod
    def _wrap(text):
        # o servidor manda para o DeepL como XML: o marcador vai dentro de <k>, que ele nao traduz
        return _MARK.sub(lambda m: "<k>Zq%sx</k>" % m.group(1), html.escape(text, quote=False))

    @staticmethod
    def _unwrap(text):
        return html.unescape(_TAG.sub(lambda m: m.group(1), text))

    def raw(self, texts, keep_flags=None):
        """Traduz textos ja protegidos. Devolve uma lista (None onde falhou) ou levanta erro se o
        servidor nao respondeu (aí quem chamou usa a traducao offline)."""
        if not self.available():
            raise OSError("servidor de traducao indisponivel")
        body = {"textos": [self._wrap(t) for t in texts]}
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
        return [self._unwrap(o) if isinstance(o, str) else None for o in outs]
