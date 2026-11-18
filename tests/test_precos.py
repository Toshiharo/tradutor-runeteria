"""Linhas de preco (tela do Peixeiro): o leitor de tela le "50c" como "soc"/"SOC" e "1s" como "Is". A traducao
automatica redesenhava esse erro por cima do preco certo. So "per"/"each" e trocado; o valor fica com os
pixels do jogo."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import _isolar  # noqa: E402,F401  (pasta de dados temporaria; antes de config)
import config  # noqa: E402
from library import Library  # noqa: E402
from pipeline import Translator, _price_line, value_line  # noqa: E402

TR = Translator(Library(), None, dict(config.DEFAULTS))


def ln(text, y=100, x=500, h=14):
    words, cx = [], x
    for t in text.split():
        words.append({"text": t, "x": cx, "y": y, "w": len(t) * 8, "h": h})
        cx += len(t) * 8 + 5
    return {"text": text, "x": x, "y": y, "w": cx - 5 - x, "h": h, "words": words}


class Precos(unittest.TestCase):
    def test_so_per_e_each_sao_trocados(self):
        for en, caixa in [("soc per 100", "por 100"), ("Soc per 100", "por 100"), ("Is SOC per 100", "por 100"),
                          ("15c per 100", "por 100"), ("1s 50c per 100", "por 100"), ("5c each", "cada"),
                          ("50c per IOO", "por")]:  # "100" lido errado tambem nao e redesenhado
            out = TR.boxes([ln(en)])
            self.assertEqual([b["pt"] for b in out], [caixa], en)
            self.assertGreater(out[0]["x"], 500, en)  # a caixa comeca depois do preco

    def test_linha_so_de_valor_fica_com_os_pixels_do_jogo(self):
        # qualquer numero + c, s ou g, junto ou separado, lido certo ou errado; nivel com numero lido errado
        for t in ["15c", "15 c", "15 s", "10 g", "1s 50c", "soc", "SOC", "Is SOC", "IO g", "SO c", "Lv IO", "Lv. 1O"]:
            self.assertTrue(value_line(t), t)
            self.assertIsNone(TR._one(t), t)
            self.assertEqual(TR.boxes([ln(t)]), [], t)

    def test_preco_separado_tambem_so_troca_per_e_each(self):
        for en, caixa in [("15 c per 100", "por 100"), ("10 g each", "cada"), ("1 s 50 c per 100", "por 100")]:
            self.assertEqual([b["pt"] for b in TR.boxes([ln(en)])], [caixa], en)

    def test_nivel_lido_certo_continua_traduzido(self):
        self.assertFalse(value_line("Lv 10"))
        self.assertFalse(value_line("Settings"))
        self.assertFalse(value_line("Level 10"))
        self.assertEqual(TR._one("LV")[0], "NV")

    def test_frase_comum_nao_e_preco(self):
        for t in ["Is this each", "Oak log per 100", "Sell each", "0c of 3s", "Is it per day"]:
            self.assertIsNone(_price_line(t), t)



class SentidoContrario(unittest.TestCase):
    """Texto "parecido" com um da biblioteca nao vale quando diz o contrario: "Unfavourite" era lido como
    "Favourite" (90% parecido) e o botao de desfavoritar aparecia como "Favorito"."""

    def test_parecido_de_sentido_contrario_e_recusado(self):
        from library import adapt
        for tela, bib in [("Unfavourite", "Favourite"), ("Unequip item", "Equip item"), ("Disable alerts", "Enable alerts"),
                          ("Not listed here", "Listed here"), ("Show closed shops", "Hide closed shops"),
                          ("Unmute player", "Mute player")]:
            self.assertIsNone(adapt(tela, bib, "qualquer", True), tela)

    def test_favoritar_e_desfavoritar(self):
        lib = Library()
        self.assertEqual(lib.lookup("Unfavourite")[0], "Desfavoritar")
        self.assertEqual(lib.lookup("UNFAVOURITE")[0], "DESFAVORITAR")
        self.assertEqual(lib.lookup("Favourite")[0], "Favorito")

    def test_erro_de_leitura_continua_valendo(self):
        from library import _opposite
        for tela, bib in [("Your bags are ernpty.", "Your bags are empty."), ("Currentbonus", "Current bonus"),
                          ("Increases your chancc", "Increases your chance"), ("Settings", "Setting")]:
            self.assertFalse(_opposite(tela.lower().split(), bib.lower().split()), tela)


if __name__ == "__main__":
    unittest.main()
