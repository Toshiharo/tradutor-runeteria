"""Copia a memoria do servidor de traducao online para app/data/compartilhada.json.

Roda todo dia no GitHub (.github/workflows/memoria.yml) e pode rodar a mao:
    set TRADUTOR_ADMIN=<ADMIN_TOKEN do servidor>
    python tools/baixar_memoria.py

So acrescenta: o que ja esta no arquivo fica (o servidor pode zerar o cache sem perder nada).
Descarta traducao que perdeu um marcador (<k>Z0</k>, <k>N0</k>) ou que saiu igual ao ingles.
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
    for it in fetch_all(url, token):
        en, pt = it.get("en"), it.get("pt")
        if en not in itens and good(en, pt):
            itens[en] = pt
    pack["itens"] = dict(sorted(itens.items(), key=lambda kv: kv[0].lower()))
    with open(DEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(pack, f, ensure_ascii=False, indent=0)
        f.write("\n")
    print(f"memoria compartilhada: {before} -> {len(itens)} textos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
