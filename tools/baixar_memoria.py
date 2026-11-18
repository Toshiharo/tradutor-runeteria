"""Copia a memoria do servidor de traducao online para app/data/compartilhada.json.

Roda todo dia no GitHub (.github/workflows/memoria.yml) e pode rodar a mao:
    set TRADUTOR_ADMIN=<ADMIN_TOKEN do servidor>
    python tools/baixar_memoria.py

So acrescenta: o que ja esta no arquivo fica (o servidor pode zerar o cache sem perder nada).
Descarta traducao que perdeu um marcador (<k>Z0</k>, <k>N0</k>) ou que saiu igual ao ingles.
O servidor aceita texto de qualquer um (o codigo do app e publico), e este arquivo vai para todos os
jogadores: so entra o que tem cara de texto de tela do jogo (sem link, sem texto que nao e ingles), e
no maximo MAX_NEW textos novos por vez (o resto entra nos dias seguintes).
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
import config  # noqa: E402

DEST = os.path.join(ROOT, "app", "data", "compartilhada.json")
TAG = re.compile(r"<k>\s*([ZN]\d+)\s*</k>")
MAX_NEW = 500     # textos novos por execucao: uma enxurrada de lixo nao enche o arquivo de uma vez
MAX_LEN = 600     # o mesmo limite do servidor (MAX_CHARS)
LINK = re.compile(r"https?:|www\.|discord\.gg|\b[\w-]+\.(?:com|net|org|gg|io|xyz|ru|br|me|tv|ly)\b|@\w", re.I)
WORD = re.compile(r"[A-Za-z]{3,}")


def has_link(text):
    """Link ou contato de fora (o site do servidor aparece nas telas e pode)."""
    return bool(LINK.search(re.sub(r"(?i)\bruneteria\.com\b", "", text)))


def game_text(en):
    """Tem cara de texto de tela do jogo? (ingles, com palavras de verdade, sem link nem contato)"""
    plain = TAG.sub(" ", en).strip()
    plain = re.sub(r"\s+", " ", re.sub(r"&(?:amp|lt|gt);", "&", plain))
    if not 3 <= len(plain) <= MAX_LEN or len(en) > MAX_LEN * 2 or "\n" in en:
        return False
    if has_link(plain):
        return False
    letters = sum(c.isalpha() for c in plain)
    ascii_ok = sum(" " <= c <= "~" for c in plain)
    if letters / len(plain) < 0.5 or ascii_ok / len(plain) < 0.9:
        return False
    return bool(WORD.search(plain)) and not re.search(r"(.)\1{5,}", plain)


def fetch_all(url, token):
    items, cursor = [], None
    while True:
        q = "/memoria" + (f"?cursor={cursor}" if cursor else "")
        req = urllib.request.Request(url.rstrip("/") + q, headers={
            "Authorization": "Bearer " + token, "User-Agent": "tradutor-runeteria/memoria"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        items.extend(data.get("itens") or [])
        cursor = data.get("cursor")
        if not cursor:
            return items


def good(en, pt):
    if not isinstance(en, str) or not isinstance(pt, str) or not en.strip() or not pt.strip():
        return False
    if pt.strip().lower() == en.strip().lower():
        return False
    if not game_text(en) or has_link(pt) or "\n" in pt:
        return False
    return sorted(TAG.findall(en)) == sorted(TAG.findall(pt)) and len(pt) <= len(en) * 3 + 20


def main():
    url = os.environ.get("TRADUTOR_URL") or config.ONLINE_MT_URL
    token = os.environ.get("TRADUTOR_ADMIN")
    if not url or not token:
        print("faltou o endereco do servidor (config.ONLINE_MT_URL) ou TRADUTOR_ADMIN")
        return 1
    with open(DEST, encoding="utf-8") as f:
        pack = json.load(f)
    itens = pack.setdefault("itens", {})
    before = len(itens)
    refused = waiting = 0
    for it in fetch_all(url, token):
        en, pt = it.get("en"), it.get("pt")
        if en in itens:
            continue
        if not good(en, pt):
            refused += 1
        elif len(itens) - before >= MAX_NEW:
            waiting += 1
        else:
            itens[en] = pt
    pack["itens"] = dict(sorted(itens.items(), key=lambda kv: kv[0].lower()))
    with open(DEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(pack, f, ensure_ascii=False, indent=0)
        f.write("\n")
    print(f"memoria compartilhada: {before} -> {len(itens)} textos")
    if refused or waiting:
        print(f"recusados pelo filtro: {refused}; ficaram para a proxima vez: {waiting}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
