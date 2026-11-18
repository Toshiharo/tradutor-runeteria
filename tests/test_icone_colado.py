"""Texto pequeno com icone colado. `style.touching` diz se o leitor cortou uma palavra ao meio (ai nao se traduz).
A regra antiga valia para qualquer coisa clara ate 4 px da ponta do texto: um icone do lado fazia o texto inteiro
ficar em ingles (medido: 423 de 600 textos com icone traduzidos; com esta regra, 579 de 600)."""
import os
import sys
import unittest

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

from style import _rgb, sample_colors, touching  # noqa: E402

BG, FG = (20, 26, 40), (225, 215, 190)


def fonte(nome, px):
    return ImageFont.truetype(os.path.join(ROOT, "app", "fonts", nome), px)


def cena(texto, px, icone=None, gap=4, lado="esq", nome="Inter.ttf", parte=0):
    """Desenha `texto`; devolve (imagem, caixa do pedaco texto[parte:]) como o leitor de tela devolveria."""
    img = Image.new("RGB", (700, 200), BG)
    d = ImageDraw.Draw(img)
    f = fonte(nome, px)
    d.text((200, 90), texto, font=f, fill=FG)
    l, t, r, b = d.textbbox((200, 90), texto[parte:], font=f)
    off = d.textlength(texto[:parte], font=f)
    l, r = l + off, r + off
    if icone:
        s = int((b - t) * 1.6) + 4
        fl, _, fr, _ = d.textbbox((200, 90), texto, font=f)
        x = fl - gap - s if lado == "esq" else fr + gap
        y = (t + b) // 2 - s // 2
        d.rounded_rectangle((x, y, x + s, y + s), radius=3, fill=(40, 48, 70), outline=icone)
        d.ellipse((x + s * .2, y + s * .2, x + s * .8, y + s * .8), fill=icone)
    return img, (l, t, r - l, b - t)


def cortada(img, caixa):
    cols = sample_colors(img, *caixa)
    return touching(img, *caixa, _rgb(cols[0]), _rgb(cols[1]))


class IconeColado(unittest.TestCase):
    def test_icone_colorido_do_lado_nao_e_palavra_cortada(self):
        for px in (11, 13, 15, 18, 22):
            for cor in ((90, 200, 120), (230, 120, 60), (120, 150, 255)):
                for lado in ("esq", "dir"):
                    img, caixa = cena("Your bags are empty.", px, icone=cor, gap=4, lado=lado)
                    self.assertEqual(cortada(img, caixa), (False, False), (px, cor, lado))

    def test_icone_da_cor_do_texto_tambem_nao(self):
        for px in (13, 15, 18, 22):
            img, caixa = cena("Settings", px, icone=FG, gap=4)
            self.assertEqual(cortada(img, caixa), (False, False), px)

    def test_palavra_cortada_de_verdade_continua_detectada(self):
        achou = total = 0
        for nome in ("Inter.ttf", "Lexend.ttf"):
            for px in (13, 15, 18, 24):
                for palavra, ini in (("Reset", 2), ("Settings", 3), ("Upgrade", 2), ("inventory", 2), ("close", 2)):
                    img, caixa = cena(palavra, px, nome=nome, parte=ini)
                    total += 1
                    achou += cortada(img, caixa)[0]
        self.assertGreaterEqual(achou, total - 2, f"{achou} de {total}")

    def test_texto_sozinho_nao_e_cortado(self):
        for px in (11, 15, 22):
            img, caixa = cena("Daily Quest", px)
            self.assertEqual(cortada(img, caixa), (False, False), px)


if __name__ == "__main__":
    unittest.main()
