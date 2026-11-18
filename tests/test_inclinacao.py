"""Leitor de tela achando texto inclinado numa tela reta (captura real da tela Overview, 1920x1009, maximizada).
Nesta imagem, na escala 1,6 o Windows devolve "text_angle" de 1,2 graus e as caixas na imagem girada; na escala
1,92 le reto. Antes da correcao as traducoes saiam deslocadas ate ~20 px e ficavam la (defeito da 1.1.4)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

from PIL import Image  # noqa: E402

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_tela_inclinada.png")


class Inclinacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from ocr_engine import WindowsOcr
            cls.ocr = WindowsOcr()
        except Exception as e:
            raise unittest.SkipTest(f"sem leitor de tela: {e}")
        cls.img = Image.open(IMG).convert("RGB")

    def pos(self, scale):
        out = {}
        for l in self.ocr.recognize(self.img, scale):
            for wd in l["words"]:
                out.setdefault(wd["text"], []).append((wd["x"] + wd["w"] / 2, wd["y"] + wd["h"] / 2))
        return out

    def test_as_duas_escalas_dao_a_mesma_posicao(self):
        a, b = self.pos(1.6), self.pos(1.92)
        for palavra in ("OVERVIEW", "PROFESSIONS", "DUNGEONS", "INVENTORY", "HEALTH"):
            self.assertIn(palavra, a)
            self.assertIn(palavra, b)
            for pa in a[palavra]:
                d = min(max(abs(pa[0] - pb[0]), abs(pa[1] - pb[1])) for pb in b[palavra])
                self.assertLess(d, 2.5, (palavra, pa))


if __name__ == "__main__":
    unittest.main()
