"""Atualizacoes pela internet (opcional, liga/desliga em "atualizar_pela_internet").

So LE arquivos publicos do repositorio no GitHub: a biblioteca e o glossario mais novos e o numero
da ultima versao. Nada do computador ou do jogo e enviado. Sem internet, o app segue igual.
"""
import json
import os
import urllib.error
import urllib.request

from config import (APP_VERSION, ONLINE_DIR, ONLINE_GLOSSARY, ONLINE_LIBRARY, REPO, SEED_GLOSSARY,
                    SEED_LIBRARY, newer, read_json, write_json)

RAW = f"https://raw.githubusercontent.com/{REPO}/main/app/data/"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
ETAGS = os.path.join(ONLINE_DIR, "etags.json")
UA = {"User-Agent": "tradutor-runeteria"}
MAX_BYTES = 20 * 1024 * 1024


def _get(url, etag=None, timeout=12):
    """(dados, etag) ou (None, etag) se nao mudou desde a ultima vez."""
    headers = dict(UA)
    if etag:
        headers["If-None-Match"] = etag
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            return r.read(MAX_BYTES + 1), r.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag
        raise


def _valid_library(data):
    return (isinstance(data, dict) and len(data) >= 1000
            and all(isinstance(v, dict) and isinstance(v.get("pt"), str) for v in data.values()))


def _valid_glossary(data):
    return (isinstance(data, dict) and isinstance(data.get("manter_em_ingles"), list)
            and all(isinstance(t, str) for t in data["manter_em_ingles"])
            and isinstance(data.get("termos_fixos", {}), dict))


def sync_translations():
    """Baixa biblioteca.json e glossario.json se mudaram. Devolve True se algo novo foi gravado."""
    os.makedirs(ONLINE_DIR, exist_ok=True)
    etags = read_json(ETAGS, {})
    changed = False
    for name, dest, bundled, valid in (("biblioteca.json", ONLINE_LIBRARY, SEED_LIBRARY, _valid_library),
                                       ("glossario.json", ONLINE_GLOSSARY, SEED_GLOSSARY, _valid_glossary)):
        try:
            # copia mais velha que a do programa nao esta em uso: baixa de novo mesmo sem mudanca
            raw, etag = _get(RAW + name, etags.get(name) if newer(dest, bundled) else None)
            if raw is None or len(raw) > MAX_BYTES:
                continue
            data = json.loads(raw.decode("utf-8"))
            if not valid(data):  # arquivo quebrado no repositorio: fica com o que ja tem
                continue
            write_json(dest, data)
            etags[name] = etag
            changed = True
        except Exception:
            continue  # sem internet, GitHub fora do ar...: tenta na proxima vez que abrir
    if changed:
        write_json(ETAGS, etags)
    return changed


def _parse(version):
    out = []
    for part in version.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def newer_version():
    """Numero da versao publicada no GitHub se for mais nova que esta; senao None."""
    try:
        raw, _ = _get(LATEST)
        tag = json.loads(raw.decode("utf-8")).get("tag_name") or ""
        if tag and _parse(tag) > _parse(APP_VERSION):
            return tag.lstrip("vV")
    except Exception:
        pass
    return None
