"""Troca de tela: traducao da tela antiga nao pode ser desenhada em cima da tela nova.

O laco de captura remonta as caixas da ultima leitura quando o mouse mexe (chat). Essas caixas sao da
captura daquela leitura: se a tela ja trocou, tem que ser conferidas contra ELA. Conferidas contra a
captura de agora (como era), passavam todas e a traducao antiga ficava "voando" sobre a tela nova.
"""
import os
import sys
import unittest

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

from style import region_changed, region_thumb  # noqa: E402

FONT = ImageFont.truetype(os.path.join(ROOT, "app", "fonts", "Inter.ttf"), 18)


def tela(textos, fundo=(20, 26, 40)):
    img = Image.new("RGB", (640, 360), fundo)
    d = ImageDraw.Draw(img)
    caixas = []
    for (x, y), t in textos:
        d.text((x, y), t, font=FONT, fill=(230, 220, 190))
        l, tp, r, b = d.textbbox((x, y), t, font=FONT)
        caixas.append({"x": l, "y": tp, "w": r - l, "h": b - tp, "en": t})
    return img, caixas


def continuam(agora, leitura, caixas):
    """O mesmo filtro do laco (main.worker): so fica a caixa cuja regiao nao mudou desde a leitura."""
    return [b for b in caixas if not region_changed(agora, region_thumb(leitura, b["x"], b["y"], b["w"], b["h"]))]


class TrocaDeTela(unittest.TestCase):
    def setUp(self):
        self.a, self.caixas_a = tela([((40, 40), "Inventory"), ((40, 120), "Your bags are empty."),
                                      ((360, 200), "Sort items"), ((40, 300), "Close")])
        # outra tela: textos em outros lugares, um deles no mesmo lugar ("Close" continua)
        self.b, _ = tela([((200, 60), "Guild members"), ((300, 140), "Invite a player"), ((40, 300), "Close")])

    def test_conferida_contra_a_leitura_a_tela_antiga_sai(self):
        ficam = [b["en"] for b in continuam(self.b, self.a, self.caixas_a)]
        self.assertEqual(ficam, ["Close"])  # so o que continua igual na tela nova

    def test_conferida_contra_a_captura_de_agora_passava_tudo(self):
        # o defeito: por isso o laco guarda a captura da leitura (App.last_img) junto com as linhas
        self.assertEqual(len(continuam(self.b, self.b, self.caixas_a)), len(self.caixas_a))

    def test_tela_parada_fica_tudo(self):
        self.assertEqual(len(continuam(self.a, self.a, self.caixas_a)), len(self.caixas_a))


if __name__ == "__main__":
    unittest.main()
