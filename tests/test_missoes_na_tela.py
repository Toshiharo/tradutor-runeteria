"""Lista de missoes na tela (captura real: "First Farm", "Rubble Rouser", "Soil Search" e um titulo que a traducao
automatica virou "Algodao Ligado"). Titulo de missao e nome: fica em ingles. No objetivo "0 / 12 - Gather Stone
Rubble" so o verbo e traduzido. A descricao em tres linhas e um paragrafo so, da biblioteca."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import _isolar  # noqa: E402,F401  (pasta de dados temporaria; antes de config)
import config  # noqa: E402
from library import Library  # noqa: E402
from pipeline import Translator  # noqa: E402


def ln(text, y, x=1634, h=13, fg="#ffffff"):
    words, cx = [], x
    for t in text.split():
        words.append({"text": t, "x": cx, "y": y, "w": len(t) * 7, "h": h})
        cx += len(t) * 7 + 4
    return {"text": text, "x": x, "y": y, "w": cx - 4 - x, "h": h, "words": words, "fg": fg, "bg": "#3a2a20"}


class FakeMT:
    ok, online, glossary, terms = True, None, [], {}
    calls = []

    def translate_many(self, texts, keeps=None, keep_flags=None):
        FakeMT.calls.extend(texts)
        return ["traducao automatica qualquer" for _ in texts]

    def pieces(self, w):
        return 1


class Missoes(unittest.TestCase):
    def setUp(self):
        FakeMT.calls = []
        self.tr = Translator(Library(), FakeMT(), dict(config.DEFAULTS))
        self.tr.view, self.tr.pointer = (1919, 1010), None

    def boxes(self, linhas):
        import time
        out = []
        for _ in range(4):
            out = self.tr.boxes(linhas)
            time.sleep(0.5)
        return {b["en"]: b["pt"] for b in out}

    def test_titulo_fica_em_ingles_e_so_o_verbo_do_objetivo_muda(self):
        for caixinha in ("", "O ", "a ", "□ "):  # a caixinha de marcar e lida de varios jeitos
            got = self.boxes([ln("Rubble Rouser", 486), ln(caixinha + "0 / 12 - Gather Stone Rubble", 507, x=1640),
                              ln("Cotton On", 542), ln(caixinha + "0 / 8 - Gather Cotton", 563, x=1640),
                              ln("Soil Search", 598), ln(caixinha + "0 / 25 - Clear Soil Blocks", 619, x=1640)])
            self.assertEqual(sorted(v.split()[-1] for v in got.values()), ["Colete", "Colete", "Limpe"], caixinha)
            self.assertTrue(all("Gather" in k or "Clear" in k for k in got), got)  # so os objetivos; titulos nao
        self.assertEqual(FakeMT.calls, [])  # nenhum titulo foi para a traducao automatica

    def test_descricao_em_tres_linhas_vem_da_biblioteca(self):
        got = self.boxes([ln("First Farm", 294), ln("Tame a male cow", 315, x=1653),
                          ln("Hold your flute and look at a wild cow in", 336, x=1653, fg="#a8acb8"),  # cinza
                          ln("the plains to see if it's male, then use", 354, x=1653, fg="#a8acb8"),
                          ln("lettuce on it.", 372, x=1653, fg="#a8acb8")])
        self.assertIn("Dome um boi", got.values())
        self.assertIn("Segure sua flauta e olhe para uma vaca selvagem nas planícies para ver se é macho, "
                      "depois use alface nela.", got.values())
        self.assertEqual(len(got), 2)
        self.assertEqual(FakeMT.calls, [])


class Provisoria(unittest.TestCase):
    """Servidor recusou (limite do dia): sai a traducao offline, mas ela NAO vai para a memoria permanente.
    Gravada, ficava para sempre na frente da traducao boa ("Milk a cow" = "Leite por vaca")."""

    def _rodar(self, caiu):
        import time

        class MT(FakeMT):
            fell_back = caiu
        lib = Library()
        tr = Translator(lib, MT(), dict(config.DEFAULTS))
        for _ in range(8):
            r = tr._one("Bring the lantern to the watchtower tonight")
            if r:
                break
            time.sleep(0.4)
        return lib, r

    def test_offline_de_reserva_nao_e_gravada(self):
        lib, r = self._rodar(True)
        self.assertEqual(r, ("traducao automatica qualquer", "auto"))  # aparece na tela agora
        self.assertFalse(lib.knows("Bring the lantern to the watchtower tonight"))  # mas nao fica gravada

    def test_traducao_do_servidor_e_gravada(self):
        lib, r = self._rodar(False)
        self.assertTrue(lib.knows("Bring the lantern to the watchtower tonight"))


if __name__ == "__main__":
    unittest.main()
