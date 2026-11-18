"""Atualizacoes pela internet (opcional, liga/desliga em "atualizar_pela_internet").

So LE arquivos publicos do repositorio no GitHub: a biblioteca e o glossario mais novos e o numero
da ultima versao. Nada do computador ou do jogo e enviado. Sem internet, o app segue igual.
"""
import json
import os
import urllib.error
import urllib.request

from config import (APP_VERSION, ONLINE_DIR, ONLINE_GLOSSARY, ONLINE_LIBRARY, ONLINE_SHARED, REPO, SEED_GLOSSARY,
                    SEED_LIBRARY, SEED_SHARED, newer, read_json, write_json)

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


def _valid_shared(data):
    return (isinstance(data, dict) and isinstance(data.get("itens"), dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in data["itens"].items()))


def sync_translations():
    """Baixa biblioteca.json, glossario.json e compartilhada.json se mudaram. True se algo novo foi gravado."""
    os.makedirs(ONLINE_DIR, exist_ok=True)
    etags = read_json(ETAGS, {})
    changed = False
    for name, dest, bundled, valid in (("biblioteca.json", ONLINE_LIBRARY, SEED_LIBRARY, _valid_library),
                                       ("glossario.json", ONLINE_GLOSSARY, SEED_GLOSSARY, _valid_glossary),
                                       ("compartilhada.json", ONLINE_SHARED, SEED_SHARED, _valid_shared)):
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


def reachable():
    """Consegue falar com o GitHub agora?"""
    try:
        _get(f"https://api.github.com/repos/{REPO}", timeout=8)
        return True
    except Exception:
        return False


def _parse(version):
    out = []
    for part in version.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


INSTALLER_NAME = "TradutorRuneteria-Instalar.exe"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
MAX_INSTALLER = 400 * 1024 * 1024


def latest_installer():
    """Instalador da ultima versao publicada, se for mais nova que esta:
    {"version", "url", "size", "sha256" (ou None)}; senao None."""
    try:
        raw, _ = _get(LATEST)
        rel = json.loads(raw.decode("utf-8"))
        tag = rel.get("tag_name") or ""
        if not tag or _parse(tag) <= _parse(APP_VERSION):
            return None
        for a in rel.get("assets") or []:
            url, size = a.get("browser_download_url") or "", a.get("size") or 0
            # so o instalador do proprio repositorio, pelo endereco oficial de download do GitHub
            if a.get("name") == INSTALLER_NAME and url.startswith(DOWNLOAD_PREFIX) and 0 < size <= MAX_INSTALLER:
                digest = a.get("digest") or ""
                return {"version": tag.lstrip("vV"), "url": url, "size": size,
                        "sha256": digest[7:].lower() if digest.startswith("sha256:") else None}
    except Exception:
        pass
    return None


def download_installer(info, progress=None):
    """Baixa o instalador para a pasta temporaria e confere (tamanho, e o sha256 quando o GitHub informa).
    Devolve o caminho do arquivo. Levanta erro se algo nao bater - ai nada e executado."""
    import hashlib
    import tempfile
    dest = os.path.join(tempfile.gettempdir(), f"TradutorRuneteria-Atualizar-{info['version']}.exe")
    part = dest + ".part"
    h, got, last = hashlib.sha256(), 0, -1
    req = urllib.request.Request(info["url"], headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r, open(part, "wb") as f:
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            got += len(chunk)
            if got > info["size"]:
                raise OSError("instalador maior que o anunciado")
            f.write(chunk)
            h.update(chunk)
            pct = got * 100 // info["size"]
            if progress and pct != last:
                last = pct
                progress(pct)
    with open(part, "rb") as f:
        head = f.read(2)
    if got != info["size"] or head != b"MZ" or (info.get("sha256") and h.hexdigest() != info["sha256"]):
        os.remove(part)
        raise OSError("instalador baixado nao confere")
    os.replace(part, dest)
    return dest


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
