"""Atualizador: procura telas novas/alteradas do Runeteria no cache do Hytale.

Quando o servidor manda uma interface nova (update), o Hytale grava o arquivo no
CachedAssets e escreve no log "asset <hash>: <n>, <caminho>". Este modulo le isso,
extrai os textos novos e traduz offline antes mesmo de voce abrir a tela.
"""
import glob
import os
import re
import threading
import time

from config import HYTALE_CACHE, HYTALE_LOGS, NEW_TEXTS_LOG, UPDATER_STATE, read_json, write_json
from extract_ui import extract_text
from lock import Session

ASSET_RE = re.compile(r"asset ([0-9a-f]{64}): \d+, (.+?)\s*$")
ADMIN_RE = re.compile(r"(^(Admin|MS_|DbStatus|Database|Telemetry|TameworkConfigEditor|AuthorsTable|CreditsPage|"
                      r"RuneTools|TebexGenerated|RevIdle|BlightBlackout|Mod(?![a-z])|ChunkClean|RuneNpcLooks)|Admin|Ed\.ui$|Editor)")

_SCAN_LOCK = threading.Lock()  # so uma passada por vez (inicio, entrada no servidor e botao podem coincidir)


def read_shared(path):
    """Le um arquivo mesmo que o Hytale esteja com ele aberto (Windows)."""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        GENERIC_READ, SHARE_ALL, OPEN_EXISTING = 0x80000000, 0x7, 3
        h = k32.CreateFileW(path, GENERIC_READ, SHARE_ALL, None, OPEN_EXISTING, 0x80, None)
        if h in (None, wintypes.HANDLE(-1).value):
            raise OSError(ctypes.get_last_error(), "nao consegui abrir", path)
        fd = msvcrt.open_osfhandle(h, os.O_RDONLY)
        with os.fdopen(fd, "rb") as f:
            return f.read()
    with open(path, "rb") as f:
        return f.read()


def runeteria_assets_from_log(path, host):
    """Devolve {caminho: hash} dos assets recebidos enquanto conectado ao Runeteria."""
    out = {}
    sess = Session()
    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("utf-8", "replace")
            if "asset " not in line:
                sess.feed(line)
                continue
            if sess.root and host in sess.root:
                m = ASSET_RE.search(line)
                if m:
                    out[m.group(2).replace("\\", "/")] = m.group(1)
    return out


class Updater:
    def __init__(self, library, translator, host="runeteria.com", logs_dir=HYTALE_LOGS, cache_dir=HYTALE_CACHE,
                 status_cb=None):
        self.lib = library
        self.mt = translator
        self.host = host
        self.logs_dir = logs_dir
        self.cache_dir = cache_dir
        self.status = status_cb or (lambda s: None)
        self.state = read_json(UPDATER_STATE, {"logs": {}, "hashes": []})
        self.done_hashes = set(self.state.get("hashes", []))

    def _save_state(self):
        self.state["hashes"] = sorted(self.done_hashes)
        write_json(UPDATER_STATE, self.state)

    def scan(self):
        """Uma passada completa. Devolve quantos textos novos foram traduzidos
        (None se ja havia outra passada rodando)."""
        if not _SCAN_LOCK.acquire(blocking=False):
            return None
        try:
            return self._scan()
        finally:
            _SCAN_LOCK.release()

    def _scan(self):
        # o estado pode ter sido gravado por outra passada desde que este objeto foi criado
        self.state = read_json(UPDATER_STATE, {"logs": {}, "hashes": []})
        self.state.setdefault("logs", {})
        self.done_hashes = set(self.state.get("hashes", []))

        assets, origin = {}, {}   # caminho -> hash ; caminho -> log de onde veio
        logs = sorted(glob.glob(os.path.join(self.logs_dir, "*_client.log")), key=os.path.getmtime)
        for log in logs:
            name = os.path.basename(log)
            try:
                sig = f"{os.path.getsize(log)}:{int(os.path.getmtime(log))}"
                if self.state["logs"].get(name) == sig and log != logs[-1]:
                    continue
                found = runeteria_assets_from_log(log, self.host)
            except OSError:
                continue
            assets.update(found)
            origin.update(dict.fromkeys(found, name))
            self.state["logs"][name] = sig
        # esquece logs que o jogo ja apagou
        alive = {os.path.basename(l) for l in logs}
        self.state["logs"] = {n: s for n, s in self.state["logs"].items() if n in alive}

        todo = []
        for path, h in assets.items():
            low = path.lower()
            if not (low.endswith(".ui") or low.endswith(".lang")):
                continue
            if h in self.done_hashes:
                continue
            if ADMIN_RE.search(os.path.basename(path)):
                self.done_hashes.add(h)
                continue
            todo.append((path, h))

        new_strings, seen = [], set()
        can_translate = bool(self.mt and self.mt.ok)
        for path, h in todo:
            f = os.path.join(self.cache_dir, h[:2], h[2:])
            try:
                content = read_shared(f).decode("utf-8", "replace")
            except OSError:
                # ainda nao baixado: o log volta a ser lido na proxima passada
                self.state["logs"].pop(origin.get(path), None)
                continue
            for s in extract_text(content, is_lang=path.lower().endswith(".lang")):
                if not self.lib.knows(s) and s.lower() not in seen:
                    seen.add(s.lower())
                    new_strings.append((s, path))
            if can_translate:
                self.done_hashes.add(h)
            else:
                self.state["logs"].pop(origin.get(path), None)  # sem modelo: fica para quando houver

        count = 0
        if new_strings and can_translate:
            with open(NEW_TEXTS_LOG, "a", encoding="utf-8") as log:
                log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M')} - {len(new_strings)} textos novos ===\n")
                for i, (s, path) in enumerate(new_strings, 1):
                    try:
                        pt = self.mt.translate(s)
                    except Exception:
                        pt = None
                    if pt and pt.strip().lower() != s.strip().lower():
                        self.lib.add_auto(s, pt, "auto-atualizacao")
                        count += 1
                    log.write(f"[{os.path.basename(path)}] {s!r} => {pt!r}\n")
                    if i % 10 == 0:
                        self.status(f"Traduzindo telas novas: {i}/{len(new_strings)}")
            self.lib.save()
        self._save_state()
        return count
