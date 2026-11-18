"""Extrai os textos visiveis de arquivos .ui e .lang do Hytale."""
import re

TEXT_RE = re.compile(r'\b(Text|TooltipText|PlaceholderText)\s*:\s*"((?:[^"\\]|\\.)*)"')
LANG_RE = re.compile(r'^\s*[\w.\-]+\s*=\s*(.+?)\s*$', re.M)


def unescape(s):
    return s.replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')


def is_translatable(s):
    t = s.strip()
    if len(t) < 2:
        return False
    if not re.search(r'[A-Za-z]{2}', t):  # precisa de pelo menos uma palavra
        return False
    if re.fullmatch(r'[\w\-]+\.(png|ui|ogg)', t):
        return False
    if re.fullmatch(r'#[0-9a-fA-F]{3,8}', t):
        return False
    return True


def extract_text(content, is_lang=False):
    out = []
    if is_lang:
        for v in LANG_RE.findall(content):
            v = unescape(v)
            if is_translatable(v):
                out.append(v)
        return out
    for _, v in TEXT_RE.findall(content):
        v = unescape(v)
        if is_translatable(v):
            out.append(v)
    return out
