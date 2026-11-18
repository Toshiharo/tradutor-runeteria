"""Aparencia da traducao: descobre as cores do texto original e o alinhamento (so PIL, testavel)."""
from PIL import Image

DESCENDERS = set("gjpqy,;()[]{}|/@$")


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c[:3])


def _palette(im, colors):
    """[(quantidade, (r,g,b))] das cores principais, da mais comum para a mais rara."""
    q = im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    out = [(n, tuple(pal[i * 3:i * 3 + 3])) for n, i in q.getcolors()]
    out.sort(reverse=True)
    return out


def sample_colors(img, x, y, w, h):
    """(fundo, texto) em '#rrggbb' para a regiao de um texto na captura, ou None se nao der.

    Fundo: cor mais comum na moldura logo em volta do texto (onde nao ha letra).
    Texto: a cor de dentro da caixa que mais se afasta do fundo.
    """
    x0, y0 = max(0, int(x) - 3), max(0, int(y) - 3)
    x1, y1 = min(img.width, int(x + w) + 3), min(img.height, int(y + h) + 3)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    crop = img.crop((x0, y0, x1, y1))
    cw, ch = crop.size
    # moldura: faixa de cima + faixa de baixo
    ring = Image.new("RGB", (cw, 4))
    ring.paste(crop.crop((0, 0, cw, 2)), (0, 0))
    ring.paste(crop.crop((0, ch - 2, cw, ch)), (0, 2))
    bg = _palette(ring, 3)[0][1]
    # NEAREST para nao misturar a cor da letra com a do fundo
    small = crop.resize((min(cw, 96), min(ch, 24)), Image.NEAREST)
    total = small.width * small.height
    cands = [(n, c) for n, c in _palette(small, 6) if n >= total * 0.02]
    fg = max(cands, key=lambda nc: _dist(nc[1], bg))[1] if cands else bg
    if _dist(fg, bg) < 110:  # contraste fraco (fundo com textura, texto fino): garante leitura
        fg = (245, 240, 225) if _lum(bg) < 140 else (20, 22, 28)
    return _hex(bg), _hex(fg)


def _rgb(hexcolor):
    return int(hexcolor[1:3], 16), int(hexcolor[3:5], 16), int(hexcolor[5:7], 16)


def free_room(img, x, y, w, h, bg, limit=None):
    """(esquerda, direita): quantos pixels de fundo liso existem dos dois lados do texto.

    Anda para os lados enquanto a cor continuar igual a do fundo; para na borda do botao/painel
    ou no texto vizinho. E o espaco que a traducao (quase sempre mais longa) pode ocupar.
    """
    limit = limit or min(int(w * 1.2) + 20, 400)
    # comeca 3 px fora da caixa: a borda suavizada da ultima letra costuma vazar da caixa do OCR
    x0, x1 = max(0, int(x) - 3), min(img.width, int(x + w) + 3)
    rows = sorted({min(img.height - 1, max(0, int(y + h * f))) for f in (0.15, 0.5, 0.85)})
    left = right = limit
    for ry in rows:
        a = max(0, x0 - limit)
        px = list(img.crop((a, ry, x0, ry + 1)).getdata())
        n = 0
        for c in reversed(px):
            if _dist(c, bg) > 48:
                break
            n += 1
        left = min(left, n)
        px = list(img.crop((x1, ry, min(img.width, x1 + limit), ry + 1)).getdata())
        n = 0
        for c in px:
            if _dist(c, bg) > 48:
                break
            n += 1
        right = min(right, n)
    return left, right


def add_colors(img, lines):
    """Anota cada linha do OCR com 'bg'/'fg' (cores) e 'room_l'/'room_r' (espaco livre) tirados da captura."""
    for ln in lines:
        try:
            cols = sample_colors(img, ln["x"], ln["y"], ln["w"], ln["h"])
            if cols:
                ln["bg"], ln["fg"] = cols
                ln["room_l"], ln["room_r"] = free_room(img, ln["x"], ln["y"], ln["w"], ln["h"], _rgb(cols[0]))
        except Exception:
            pass
    return lines


def avail_width(box, margin=6):
    """Largura maxima para a traducao de uma caixa, usando o espaco livre medido na tela."""
    w = box["w"]
    if "room_r" not in box:
        return max(w * 1.35, 40)
    if box.get("align") == "center":
        extra = 2 * max(0, min(box["room_l"], box["room_r"]) - margin)
    else:
        extra = max(0, box["room_r"] - margin)
    return max(w * 1.15, min(w + extra, w * 2.2), 40)


def font_px(text, line_h):
    """Tamanho da fonte (em pixels) que reproduz a altura do texto original.

    A caixa do OCR abraca so as letras: sem letra que desce (g, p, y...) ela mede ~0,74 do
    tamanho da fonte; com elas, ~0,95. Sem essa correcao MAIUSCULAS saem pequenas demais.
    """
    has_desc = any(c in DESCENDERS for c in text)
    return max(1, round(line_h / (0.95 if has_desc else 0.74)))


def guess_align(line, all_lines, tol=None):
    """'left' ou 'center' para uma linha solta, olhando as vizinhas.

    Outras linhas comecando no mesmo x -> lista/coluna alinhada a esquerda.
    Outras linhas com o mesmo centro -> coluna centralizada (botoes, titulos).
    Sozinha: texto curto costuma ser botao/aba (centro); texto longo, descricao (esquerda).
    """
    tol = tol or max(4, line["h"] * 0.25)
    cx = line["x"] + line["w"] / 2
    left = center = 0
    for o in all_lines:
        if o is line or abs(o["y"] - line["y"]) > line["h"] * 12:
            continue
        if abs(o["x"] - line["x"]) <= tol:
            left += 1
        elif abs(o["x"] + o["w"] / 2 - cx) <= tol:
            center += 1
    if left or center:
        return "left" if left >= center else "center"
    return "center" if len(line["text"].split()) <= 3 else "left"


def block_align(lines, tol=None):
    """Alinhamento de um paragrafo de varias linhas."""
    tol = tol or max(4, lines[0]["h"] * 0.3)
    lefts = [l["x"] for l in lines]
    if max(lefts) - min(lefts) <= tol:
        return "left"
    centers = [l["x"] + l["w"] / 2 for l in lines]
    return "center" if max(centers) - min(centers) <= tol * 2 else "left"
