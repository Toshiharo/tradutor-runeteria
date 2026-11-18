"""Aparencia da traducao: descobre as cores do texto original e o alinhamento (so PIL, testavel)."""
from PIL import Image, ImageChops

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


def ink_rows(img, x, y, w, h, bg, fg):
    """(topo, altura) exatos das letras: a caixa do OCR costuma sobrar ou faltar 1-2 px, e em texto
    de 9 px isso e mais de 10% de erro no tamanho da fonte.

    Letra = pixel mais parecido com a cor do texto do que com a do fundo. Comparar so com o fundo
    falha em fundo com degrade (abas, cabecalhos), onde o proprio fundo "vira tinta".
    """
    x0, x1 = max(0, int(x)), min(img.width, int(x + w) + 1)
    y0, y1 = max(0, int(y) - 2), min(img.height, int(y + h) + 3)
    crop = img.crop((x0, y0, x1, y1))
    far_bg = ImageChops.difference(crop, Image.new("RGB", crop.size, bg)).convert("L")
    far_fg = ImageChops.difference(crop, Image.new("RGB", crop.size, fg)).convert("L")
    # tinta = pelo menos ~35% do caminho entre fundo e letra (pega tambem a borda suavizada das letras)
    box = ImageChops.subtract(far_bg.point(lambda v: v * 0.65), far_fg.point(lambda v: v * 0.35)).point(
        lambda v: 255 if v > 2 else 0).getbbox()
    if not box:
        return None
    top, height = y0 + box[1], box[3] - box[1]
    if not 0.6 * h <= height <= 1.35 * h:  # pegou outra coisa (borda, icone): fica com a caixa do OCR
        return None
    # quantidade de tinta em "pixels cheios": distingue texto fino de negrito sem depender da largura
    contrast = max(1, _lum([abs(a - b) for a, b in zip(bg, fg)]))
    amount = sum(far_bg.crop((0, box[1], crop.width, box[3])).getdata()) / contrast
    return top, height, amount


def bg_gradient(img, x, y, w, h, bg, fg):
    """Fundo que nao e de cor unica (degrade de aba/botao, painel translucido sobre o cenario).

    Le, linha a linha, a cor logo a esquerda e logo a direita do texto. Devolve
    (y inicial, [(cor esquerda, cor direita), ...]) ou None quando o fundo e liso ou quando as colunas
    lidas nao sao fundo de verdade (pegaram um icone, outra letra, uma borda).
    """
    y0, y1 = max(0, int(y) - 4), min(img.height, int(y + h) + 5)
    xl, xr = int(x) - 5, int(x + w) + 5
    if xl < 0 or xr >= img.width or y1 - y0 < 4:
        return None
    left = list(img.crop((xl, y0, xl + 1, y1)).getdata())
    right = list(img.crop((xr, y0, xr + 1, y1)).getdata())
    for col in (left, right):
        for i, c in enumerate(col):
            # longe demais do fundo, parecido com a letra, ou salto brusco entre linhas: nao e fundo
            if _dist(c, bg) > 100 or _dist(c, fg) < _dist(c, bg) or (i and _dist(c, col[i - 1]) > 36):
                return None
    if max(_dist(c, bg) for c in left + right) < 24:
        return None  # praticamente liso: o retangulo de cor unica ja resolve
    return y0, [(_hex(a), _hex(b)) for a, b in zip(left, right)]


def touching(img, x, y, w, h, bg, fg):
    """(esquerda, direita): ha letra da mesma cor colada na ponta do texto?

    Se sim, o OCR cortou uma palavra ao meio (leu "set" de "Reset"): traduzir o pedaco sairia errado.
    """
    y0, y1 = max(0, int(y + h * 0.15)), min(img.height, int(y + h * 0.9) + 1)
    out = []
    for x0, x1 in ((int(x) - 4, int(x) - 1), (int(x + w) + 1, int(x + w) + 4)):
        x0, x1 = max(0, x0), min(img.width, x1)
        if x1 <= x0 or y1 <= y0:
            out.append(False)
            continue
        hit = sum(1 for c in img.crop((x0, y0, x1, y1)).getdata() if _dist(c, fg) * 1.5 < _dist(c, bg))
        out.append(hit >= 2)
    return tuple(out)


def add_colors(img, lines):
    """Anota cada linha do OCR com 'bg'/'fg' (cores), 'room_l'/'room_r' (espaco livre) e
    'iy'/'ih' (topo e altura exatos das letras), tirados da captura."""
    for ln in lines:
        try:
            cols = sample_colors(img, ln["x"], ln["y"], ln["w"], ln["h"])
            if cols:
                ln["bg"], ln["fg"] = cols
                bg = _rgb(cols[0])
                ln["room_l"], ln["room_r"] = free_room(img, ln["x"], ln["y"], ln["w"], ln["h"], bg)
                rows = ink_rows(img, ln["x"], ln["y"], ln["w"], ln["h"], bg, _rgb(cols[1]))
                if rows:
                    ln["iy"], ln["ih"], ln["ink"] = rows
                fg = _rgb(cols[1])
                grad = bg_gradient(img, ln["x"], ln["y"], ln["w"], ln["h"], bg, fg)
                if grad:
                    ln["grad"] = grad
                ln["cut"] = any(touching(img, ln["x"], ln["y"], ln["w"], ln["h"], bg, fg))
        except Exception:
            pass
    return lines


# ---------- fonte: mesma familia, peso e tamanho do texto original ----------
# O Runeteria usa Lexend (rotulos, botoes), Inter (texto) e Cormorant (titulos). Com os arquivos das
# fontes da para medir de verdade: para cada texto, qual fonte/peso da a largura mais proxima da lida
# na tela, e que tamanho faz as letras terem exatamente a altura do original.
FACES = [  # (familia no tkinter, peso no tkinter, arquivo, eixo de peso)
    ("Lexend", "normal", "Lexend.ttf", 400),
    ("Lexend SemiBold", "normal", "Lexend.ttf", 600),
    ("Inter", "normal", "Inter.ttf", 400),
    ("Inter SemiBold", "normal", "Inter.ttf", 600),
    ("Cormorant", "bold", "Cormorant.ttf", 700),
]
_REF = 200  # tamanho em que as fontes sao medidas
_faces = []          # [(familia, peso, ImageFont)]
_metrics = {}        # (indice da fonte, texto) -> (topo, base, largura) por pixel de tamanho


def init_faces(folder):
    """Carrega os arquivos de fonte para medicao. Sem eles, o overlay usa as regras aproximadas."""
    import os
    from PIL import ImageFont
    _faces.clear()
    for family, weight, fname, wght in FACES:
        try:
            f = ImageFont.truetype(os.path.join(folder, fname), _REF)
            try:
                axes = f.get_variation_axes()
                f.set_variation_by_axes([wght if (a.get("name") in (b"Weight", "Weight")) else a["default"]
                                         for a in axes])
            except Exception:
                pass
            _faces.append((family, weight, f))
        except Exception:
            continue
    return bool(_faces)


def _measure(i, text):
    key = (i, text)
    m = _metrics.get(key)
    if m is None:
        if len(_metrics) > 4000:
            _metrics.clear()
        box = _faces[i][2].getbbox(text, anchor="ls")  # relativo a linha de base
        m = _metrics[key] = (box[1] / _REF, box[3] / _REF, (box[2] - box[0]) / _REF)
    return m


def _ink_amount(i, text, px):
    """Quantidade de tinta (em pixels cheios) de `text` na fonte i, no tamanho px."""
    key = (i, text, "ink")
    per_px2 = _metrics.get(key)
    if per_px2 is None:
        from PIL import ImageDraw
        f = _faces[i][2]
        box = f.getbbox(text)
        im = Image.new("L", (max(1, box[2] - box[0]), max(1, box[3] - box[1])), 0)
        ImageDraw.Draw(im).text((-box[0], -box[1]), text, font=f, fill=255)
        per_px2 = _metrics[key] = sum(im.getdata()) / 255 / (_REF * _REF)
    return per_px2 * px * px


def pick_face(text, width, ink_h, ink=None):
    """Fonte que melhor reproduz um texto lido na tela.

    Devolve um dict com family, weight, px e below, ou None. px = tamanho em que as letras de `text`
    tem `ink_h` pixels de altura; below = quanto a tinta desce abaixo da linha de base (g, p, y,
    virgula), para alinhar a traducao pela mesma linha de base do original.

    - Peso (normal x seminegrito): pela quantidade de tinta `ink` medida na tela. A largura nao serve
      para isso: rotulos com espacamento entre letras ficam largos mesmo sendo finos.
    - Familia: MAIUSCULAS -> Lexend (botoes, abas, rotulos do kit); texto comum -> Inter; a outra so
      entra se a largura bater melhor (3%). Assim abas vizinhas nao saem cada uma numa fonte.
    - Titulo grande com letras -> Cormorant, se a largura nao fugir muito (os titulos do kit sao serifados).
    """
    letters = sum(c.isalpha() for c in text)
    cands = {}
    for i, (family, weight, _) in enumerate(_faces):
        top, bottom, w = _measure(i, text)
        if bottom - top <= 0:
            continue
        px = ink_h / (bottom - top)
        cands[family] = (abs(w * px - width), family, weight, px, bottom * px, i)
    if not cands:
        return None
    serif = cands.get("Cormorant")
    if serif and ink_h >= 15 and letters >= 4 and serif[0] <= width * 0.2:
        best = serif
    else:
        def with_weight(base):
            reg, semi = cands.get(base), cands.get(base + " SemiBold")
            if not reg or not semi:
                return reg or semi
            if ink:
                return min((reg, semi), key=lambda c: abs(_ink_amount(c[5], text, c[3]) - ink))
            return min(reg, semi)
        first, second = ("Lexend", "Inter") if text.isupper() else ("Inter", "Lexend")
        a1, b1 = with_weight(first), with_weight(second)
        best = a1 if a1 and (not b1 or a1[0] <= b1[0] + width * 0.03) else b1
        if best is None:
            best = min(cands.values())
    # espacamento entre letras: o que falta de largura, dividido pelos vaos (rotulos do kit sao espacados)
    gaps = len(text) - 1
    track = (width - _measure(best[5], text)[2] * best[3]) / gaps if gaps > 0 else 0
    if track < 0.07 * best[3] or len(text) < 4:
        track = 0  # diferenca pequena e so imprecisao de medida
    return {"family": best[1], "weight": best[2], "px": max(1, round(best[3])), "below": best[4],
            "track": min(track, best[3] * 0.35)}


def avail_width(box, margin=6):
    """Largura maxima para a traducao de uma caixa, usando o espaco livre medido na tela."""
    w = box["w"]
    if "room_r" not in box:
        return max(w * 1.35, 40)
    if box.get("align") == "center":
        extra = 2 * max(0, min(box["room_l"], box["room_r"]) - margin)
    elif box.get("align") == "right":
        extra = max(0, box["room_l"] - margin)
    else:
        extra = max(0, box["room_r"] - margin)
    return max(w * 1.15, min(w + extra, max(w * 2.2, w + 110)), 40)


def font_px(text, line_h):
    """(reserva, sem os arquivos de fonte) Tamanho da fonte que reproduz a altura do texto original.

    A caixa do OCR abraca so as letras: sem letra que desce (g, p, y...) ela mede ~0,74 do
    tamanho da fonte; com elas, ~0,95. Sem essa correcao MAIUSCULAS saem pequenas demais.
    """
    has_desc = any(c in DESCENDERS for c in text)
    return max(1, round(line_h / (0.95 if has_desc else 0.74)))


def guess_align(line, all_lines, tol=None):
    """'left', 'center' ou 'right' para uma linha solta.

    Vizinhas comecando no mesmo x -> coluna alinhada a esquerda (lista, titulos de secao).
    Vizinhas com o mesmo centro -> coluna centralizada. Mesmo fim -> alinhada a direita (valores).
    Sozinha: compara o fundo liso dos dois lados; igual dos dois lados = centralizada (botao, aba).
    """
    tol = tol or max(3, line["h"] * 0.25)
    cx, rx = line["x"] + line["w"] / 2, line["x"] + line["w"]
    left = center = right = 0
    for o in all_lines:
        dy = abs(o["y"] - line["y"])
        # mesma regiao da tela (titulos de secao de um painel ficam a ate ~250 px um do outro)
        if o is line or dy > max(line["h"] * 30, 250) or dy < line["h"] * 0.5:
            continue
        if abs(o["x"] - line["x"]) <= tol:
            left += 1
        elif abs(o["x"] + o["w"] / 2 - cx) <= tol:
            center += 1
        elif abs(o["x"] + o["w"] - rx) <= tol:
            right += 1
    if left or center or right:
        if left >= center and left >= right:
            return "left"
        return "center" if center >= right else "right"
    if "room_r" in line:
        l, r = line["room_l"], line["room_r"]
        if abs(l - r) <= max(4, 0.2 * max(l, r)):
            return "center"
        return "left" if l < r else "right"
    return "center" if len(line["text"].split()) <= 3 else "left"


def block_align(lines, tol=None):
    """Alinhamento de um paragrafo de varias linhas."""
    tol = tol or max(4, lines[0]["h"] * 0.3)
    lefts = [l["x"] for l in lines]
    if max(lefts) - min(lefts) <= tol:
        return "left"
    centers = [l["x"] + l["w"] / 2 for l in lines]
    return "center" if max(centers) - min(centers) <= tol * 2 else "left"
