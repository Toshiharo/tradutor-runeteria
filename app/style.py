"""Aparencia da traducao: descobre as cores do texto original e o alinhamento (so PIL, testavel)."""
import re

from PIL import Image, ImageChops, ImageStat

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
    limit = limit or min(int(w * 1.2) + 20, max(400, int(h * 40)))  # 400 px em 1080p, proporcional ao texto
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


def ink_rows(img, x, y, w, h, bg, fg, caps=False):
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
    mask = ImageChops.subtract(far_bg.point(lambda v: v * 0.65), far_fg.point(lambda v: v * 0.35)).point(
        lambda v: 255 if v > 2 else 0)
    if not mask.getbbox():
        return None
    # do meio da linha para cima e para baixo, ate a primeira fileira sem tinta: a "perninha" de um g/y da
    # linha de cima entra na margem do recorte, mas fica separada do texto por fileiras vazias
    # (sem isso, texto de 11 px era medido como 14 e a traducao saia maior que o original)
    rows = [ImageStat.Stat(mask.crop((0, i, mask.width, i + 1))).sum[0] > 0 for i in range(mask.height)]
    mid = min(mask.height - 1, max(0, int(y + h / 2) - y0))
    if not rows[mid]:
        mid = next((i for i in range(mask.height) if rows[i]), mid)
    a = b = mid
    while a > 0 and rows[a - 1]:
        a -= 1
    while b < mask.height - 1 and rows[b + 1]:
        b += 1
    if caps:
        # MAIUSCULAS: a cauda do Q e a virgula descem abaixo da linha de base em fileiras quase vazias.
        # A altura que vale e a das maiusculas (em "REQUEST MODE" a cauda somava 3 px e a fonte saia 30% maior)
        counts = [ImageStat.Stat(mask.crop((0, i, mask.width, i + 1))).sum[0] / 255 for i in range(mask.height)]
        full = sorted(counts[a:b + 1])[(b - a) // 2]
        while b > a + 3 and counts[b] < full * 0.3:
            b -= 1
    box = (0, a, mask.width, b + 1)
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
    # ate onde procurar: o vao entre duas letras da mesma palavra, proporcional ao tamanho da letra
    reach = max(3, min(6, int(round(h * 0.28))))
    contrast = _dist(fg, bg) or 1.0

    def letter(box):
        # tinta DA COR DO TEXTO (a letra vizinha e da mesma cor; icone colorido do lado nao conta). Antes
        # valia qualquer coisa mais clara que o fundo, e todo texto com icone colado ficava sem traducao
        return sum(1 for c in img.crop(box).getdata() if _dist(c, fg) < contrast * 0.3)

    def ink(box):
        return sum(1 for c in img.crop(box).getdata() if _dist(c, fg) * 1.5 < _dist(c, bg))
    out = []
    for x0, x1 in ((int(x) - reach, int(x) - 1), (int(x + w) + 1, int(x + w) + reach)):
        x0, x1 = max(0, x0), min(img.width, x1)
        if x1 <= x0 or y1 <= y0:
            out.append(False)
            continue
        if letter((x0, y0, x1, y1)) < 2:
            out.append(False)
            continue
        # letra ou icone da mesma cor do texto? A letra vizinha cabe na linha (no maximo sobe ou desce um
        # pouco: "R", "g"). Icone, moldura e barra passam de cima E de baixo, ou muito de um lado so
        ya, yb = max(0, int(y - h * 0.9)), min(img.height, int(y + h * 1.9) + 1)
        # o icone e largo: olha um pouco alem do alcance (uma letra de largura), onde o canto dele ja nao e arredondado
        if x1 <= int(x):
            x0 = max(0, x0 - int(h * 0.35))
        else:
            x1 = min(img.width, x1 + int(h * 0.35))
        above = ink((x0, ya, x1, max(ya, int(y - h * 0.2)))) >= 1
        below = ink((x0, min(yb, int(y + h * 1.2) + 1), x1, yb)) >= 1
        far_up = ink((x0, ya, x1, max(ya, int(y - h * 0.6)))) >= 2
        far_dn = ink((x0, min(yb, int(y + h * 1.6) + 1), x1, yb)) >= 2
        out.append(not ((above and below) or far_up or far_dn))
    return tuple(out)


def split_by_color(img, lines):
    """Separa linhas em que o OCR juntou elementos de cores diferentes com um vao no meio
    (selo "PUBLIC Open for trade" + a mensagem do dono da loja em dourado).
    So olha vaos de mais de 0,8x a altura do texto (um espaco normal tem ~0,3x); roda antes de add_colors."""
    out = []
    for ln in lines:
        words = ln.get("words")
        if not words or len(words) < 2:
            out.append(ln)
            continue
        hs = sorted(w["h"] for w in words)
        hmed = hs[(len(hs) - 1) // 2]
        cuts = [i for i in range(1, len(words))
                if words[i]["x"] - (words[i - 1]["x"] + words[i - 1]["w"]) > hmed * 0.8]
        segs, start = [], 0
        for i in cuts:
            left, right = words[start:i], words[i:]
            cl = _seg_fg(img, left)
            cr = _seg_fg(img, right[:max(1, len(right))])
            if cl and cr and _dist(cl, cr) > 90:
                segs.append(left)
                start = i
        if not segs:
            out.append(ln)
            continue
        segs.append(words[start:])
        for seg in segs:
            x = min(w["x"] for w in seg)
            y = min(w["y"] for w in seg)
            out.append({"text": " ".join(w["text"] for w in seg), "x": x, "y": y,
                        "w": max(w["x"] + w["w"] for w in seg) - x, "h": max(w["y"] + w["h"] for w in seg) - y,
                        "words": list(seg)})
    return out


def _seg_fg(img, words):
    """Cor da letra de um grupo de palavras (as 3 mais proximas do corte bastam)."""
    ws = words[-3:] if len(words) > 3 else words
    x = min(w["x"] for w in ws)
    y = min(w["y"] for w in ws)
    try:
        cols = sample_colors(img, x, y, max(w["x"] + w["w"] for w in ws) - x, max(w["y"] + w["h"] for w in ws) - y)
    except Exception:
        return None
    return _rgb(cols[1]) if cols else None


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
                rows = ink_rows(img, ln["x"], ln["y"], ln["w"], ln["h"], bg, _rgb(cols[1]), ln["text"].isupper())
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


def restyle_spans(img, boxes):
    """Trecho traduzido no meio de uma linha mede a PROPRIA cor, altura e tinta na tela.

    A linha pode misturar estilos ("Metal Mastery" branco e grande + "+0%" cinza): herdando o estilo da
    linha, o trecho saia fino e cinza. So mexe nas caixas marcadas "inline" que nao cobrem a linha toda.
    """
    for b in boxes:
        if not b.get("inline") or b.get("_styled"):
            continue
        b["_styled"] = True
        try:
            cols = sample_colors(img, b["x"], b["y"], b["w"], b["h"])
            if not cols:
                continue
            b["bg"], b["fg"] = cols
            b.pop("grad", None)
            rows = ink_rows(img, b["x"], b["y"], b["w"], b["h"], _rgb(cols[0]), _rgb(cols[1]), b["en"].isupper())
            if rows:
                b["iy"], b["ih"], b["ink"] = rows
                b["line_h"] = rows[1]
                b["ref"] = (b["en"], b["w"])
        except Exception:
            pass
    return boxes


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
_INK_REF = 40  # tamanho em que a quantidade de tinta e medida (proporcao basta; menor = mais rapido)
_faces = []          # [(familia, peso, ImageFont para medir, ImageFont pequena para a tinta)]
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
            small = ImageFont.truetype(os.path.join(folder, fname), _INK_REF)
            try:
                small.set_variation_by_axes([wght if (a.get("name") in (b"Weight", "Weight")) else a["default"]
                                             for a in small.get_variation_axes()])
            except Exception:
                pass
            _faces.append((family, weight, f, small))
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
        f = _faces[i][3]
        box = f.getbbox(text)
        im = Image.new("L", (max(1, box[2] - box[0]), max(1, box[3] - box[1])), 0)
        ImageDraw.Draw(im).text((-box[0], -box[1]), text, font=f, fill=255)
        per_px2 = _metrics[key] = ImageStat.Stat(im).sum[0] / 255 / (_INK_REF * _INK_REF)
    return per_px2 * px * px


def pick_face(text, width, ink_h, ink=None, like=None):
    """Fonte que melhor reproduz um texto lido na tela.

    Devolve um dict com family, weight, px e below, ou None. px = tamanho em que as letras de `text`
    tem `ink_h` pixels de altura; below = quanto a tinta desce abaixo da linha de base (g, p, y,
    virgula), para alinhar a traducao pela mesma linha de base do original.

    - Peso (normal x seminegrito): pela quantidade de tinta `ink` medida na tela. A largura nao serve
      para isso: rotulos com espacamento entre letras ficam largos mesmo sendo finos.
    - Familia: MAIUSCULAS -> Lexend (botoes, abas, rotulos do kit); texto comum -> Inter; a outra so
      entra se a largura bater melhor (3%). Assim abas vizinhas nao saem cada uma numa fonte.
    - Titulo grande com letras -> Cormorant, se a largura nao fugir muito (os titulos do kit sao serifados).
    - `like` ("Lexend" ou "Inter"): familia ja medida na linha inteira. Um trecho curto ("Clear 8") nao
      tem largura suficiente para separar as duas, e saia numa fonte diferente do resto da linha.
    """
    letters = sum(c.isalpha() for c in text)
    cands = {}
    # em MAIUSCULAS a altura medida na tela e a das maiusculas (sem a cauda do Q, ver ink_rows)
    tall = text.replace("Q", "O").replace(",", "") if text.isupper() else text
    for i, (family, weight, *_) in enumerate(_faces):
        top, bottom = _measure(i, tall)[:2]
        w = _measure(i, text)[2]
        if bottom - top <= 0:
            continue
        px = ink_h / (bottom - top)
        cands[family] = (abs(w * px - width), family, weight, px, bottom * px, i)
    if not cands:
        return None
    serif = cands.get("Cormorant")
    # Titulo grande: serifado e fino (DUNGEONS, QUESTS, MINING) ou Lexend negrito (PROFESSIONS, nome de item)?
    # A largura nao separa os dois; a quantidade de tinta sim. Medido nas telas reais: no serifado a
    # Cormorant da 0,81-1,06 da tinta da tela e a Lexend negrito daria 1,4-1,8; no negrito e o contrario
    # (Lexend 0,87-0,97, Cormorant 0,44-0,58). Sem medida de tinta, nao arrisca a serifada.
    use_serif = False
    bold = cands.get("Lexend SemiBold")
    if serif and bold and ink and ink_h >= 15 and letters >= 4 and not re.search(r"\d", text) \
            and serif[0] <= width * 0.25:
        r_serif = _ink_amount(serif[5], text, serif[3]) / ink
        r_bold = _ink_amount(bold[5], text, bold[3]) / ink
        use_serif = 0.7 <= r_serif <= 1.3 and abs(r_serif - 1) < abs(r_bold - 1)
    if use_serif:
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
        if like in (first, second):
            best = with_weight(like)
        else:
            best = a1 if a1 and (not b1 or a1[0] <= b1[0] + width * 0.03) else b1
        if best is None:
            best = min(cands.values())
    # espacamento entre letras: o que falta de largura, dividido pelos vaos (rotulos do kit sao espacados)
    gaps = len(text) - 1
    track = (width - _measure(best[5], text)[2] * best[3]) / gaps if gaps > 0 else 0
    if track < 0.07 * best[3] or len(text) < 4:
        track = 0  # diferenca pequena e so imprecisao de medida
    ext = _measure(best[5], "ÁÇÃgpy")  # do topo do acento ao fim da letra que desce
    return {"family": best[1], "weight": best[2], "px": max(1, round(best[3])), "below": best[4],
            "track": min(track, best[3] * 0.35), "up": -ext[0], "down": ext[1]}


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
    grow = max(w * 2.2, w + 11 * box.get("line_h", 10))  # cresce no maximo isso (proporcional ao texto)
    # nunca passa do espaco livre medido: depois dele vem outro texto, icone ou a borda do painel
    return min(w + extra, grow)


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
        if o is line or dy > line["h"] * 30 or dy < line["h"] * 0.5:  # mesma regiao, proporcional ao texto
            continue
        if abs(o["x"] - line["x"]) <= tol:
            left += 1
        elif abs(o["x"] + o["w"] / 2 - cx) <= tol:
            center += 1
        elif abs(o["x"] + o["w"] - rx) <= tol:
            right += 1
    if len(line["text"].split()) >= 5:
        right = 0  # frase nao e alinhada a direita: terminar no mesmo x de outra linha e coincidencia
    if left or center or right:
        if left == right and left >= center and "room_r" in line:
            # textos iguais empilhados em colunas (o "1 in stock" de cada card): olha de que lado ha espaco
            return "right" if line["room_r"] < line["room_l"] else "left"
        if left >= center and left >= right:
            return "left"
        return "center" if center >= right else "right"
    if "room_r" in line:
        l, r = line["room_l"], line["room_r"]
        if abs(l - r) <= max(4, 0.2 * max(l, r)):
            # frase longa e solta (subtitulo da pagina) e lida da esquerda: centralizar faria a traducao,
            # que e mais comprida, crescer tambem para a esquerda
            return "left" if len(line["text"].split()) >= 6 else "center"
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


# ---------- deteccao rapida de mudanca ----------
def _signature(crop, size):
    """Miniatura em cinza com o contraste esticado: destaca o desenho das letras e ignora mudancas
    do fundo (brilho do painel ao passar o mouse, cenario 3D se mexendo atras de painel translucido)."""
    from PIL import ImageOps
    return ImageOps.autocontrast(crop.convert("L").resize(size, Image.BILINEAR), cutoff=2)


def region_thumb(img, x, y, w, h):
    """Miniatura em cinza da regiao de um texto, para saber depois se o jogo trocou o que estava ali."""
    box = (max(0, int(x) - 2), max(0, int(y) - 2), min(img.width, int(x + w) + 3), min(img.height, int(y + h) + 3))
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        return None
    size = (max(6, min(64, int(w) // 2)), max(4, min(14, int(h))))
    return box, _signature(img.crop(box), size)


def region_changed(img, thumb, limit=30):
    """True se a regiao mudou de verdade (outro texto, outro menu, menu fechado).

    Compara miniaturas: o cenario 3D se mexendo atras de um painel muda pouco a media; um texto
    trocado por outro (ou sumindo) muda muito.
    """
    if thumb is None:
        return False
    box, t = thumb
    if box[2] > img.width or box[3] > img.height:
        return True  # a janela mudou de tamanho
    return ImageStat.Stat(ImageChops.difference(_signature(img.crop(box), t.size), t)).mean[0] > limit


def screen_diff(a, b):
    """Diferenca media (0-255) entre duas assinaturas da tela inteira (miniaturas em cinza)."""
    if a is None or b is None or a.size != b.size:
        return 255.0
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]
