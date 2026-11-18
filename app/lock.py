"""Descobre, pelo log do Hytale, se voce esta DENTRO do Runeteria agora."""
import glob
import os
import re
import time

DIRECT_RE = re.compile(r"Direct connecting to multiplayer server at\s+([\w.\-]+)")
CONNECT_RE = re.compile(r"Connecting to server\s+([\w.\-:]+)")
REFERRAL_RE = re.compile(r"Referral: \S+ -> ([\w.\-:]+)")
STAGE_RE = re.compile(r"Changing from Stage (\w+) to (\w+)")


class Session:
    """Segue a sessao no log. O Runeteria manda o jogador para sub-servidores por IP
    (Referral: play.runeteria.com -> 135.x.x.x), entao a sessao continua sendo do
    servidor onde voce entrou ate voltar ao menu ou sair."""

    def __init__(self):
        self.root = None      # servidor onde a sessao comecou
        self.current = None   # servidor atual
        self.stage = None
        self._referral = None

    def feed(self, line):
        m = DIRECT_RE.search(line)
        if m:
            self.root = m.group(1).lower()
            self._referral = None
            return
        m = REFERRAL_RE.search(line)
        if m:
            self._referral = m.group(1).lower()
            return
        m = CONNECT_RE.search(line)
        if m:
            target = m.group(1).lower()
            # transferencia (Referral) ou reconexao continuam na mesma sessao;
            # a sessao so recomeca depois de voltar ao menu
            if self.root is None:
                self.root = target
            self.current = target
            self._referral = None
            return
        m = STAGE_RE.search(line)
        if m:
            self.stage = m.group(2)
            if self.stage in ("MainMenu", "Exited"):
                self.root = None
                self.current = None
                self._referral = None


def latest_client_log(logs_dir):
    logs = glob.glob(os.path.join(logs_dir, "*_client.log"))
    if not logs:
        return None
    return max(logs, key=os.path.getmtime)


class RuneteriaLock:
    """Le o log mais recente aos poucos (so o que foi acrescentado) e acompanha a sessao."""

    def __init__(self, logs_dir, host="runeteria.com"):
        self.logs_dir = logs_dir
        self.host = host.lower()
        self._log = None
        self._pos = 0
        self._partial = b""
        self._sess = Session()
        self._last_check = 0

    def refresh(self):
        now = time.time()
        if now - self._last_check < 0.5:
            return
        self._last_check = now
        log = latest_client_log(self.logs_dir)
        if log != self._log:
            self._log, self._pos, self._partial, self._sess = log, 0, b"", Session()
        if not log:
            return
        try:
            size = os.path.getsize(log)
            if size < self._pos:
                self._pos, self._partial, self._sess = 0, b"", Session()
            if size == self._pos:
                return
            with open(log, "rb") as f:
                f.seek(self._pos)
                data = f.read()
            self._pos += len(data)
        except OSError:
            return
        data = self._partial + data
        lines = data.split(b"\n")
        self._partial = lines.pop()
        for raw in lines:
            if b"asset " in raw:
                continue
            self._sess.feed(raw.decode("utf-8", "replace"))

    @property
    def server(self):
        return self._sess.root

    @property
    def stage(self):
        return self._sess.stage

    @property
    def current(self):
        return self._sess.current

    def active(self):
        self.refresh()
        return bool(self.server and self.host in self.server and self.stage == "InGame")

    def describe(self):
        self.refresh()
        if not self.server:
            return f"fora de servidor ({self.stage or '?'})"
        extra = f" -> {self.current}" if self.current and self.current.split(":")[0] != self.server.split(":")[0] else ""
        return f"{self.server}{extra} ({self.stage or '?'})"
