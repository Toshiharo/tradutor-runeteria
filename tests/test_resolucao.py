"""Resolucoes diferentes de 1920x1080 e caixas so em cima do trecho traduzido.

Rodar:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from ocr_engine import auto_scale, initial_scale  # noqa: E402
from pipeline import Translator  # noqa: E402
from style import avail_width  # noqa: E402


class EscalaDoOcr(unittest.TestCase):
    def test_acompanha_o_tamanho_do_texto(self):
        self.assertAlmostEqual(initial_scale(1009), 15.5 / 9, places=2)  # 1080p: ~1,7x
        self.assertGreater(auto_scale(6, 1280, 673), 2.4)                 # 720p: texto de 6 px, amplia mais
        self.assertLess(auto_scale(18, 3840, 2018), 1.0)                  # 4K: texto grande, quase sem ampliar
        self.assertEqual(auto_scale(2, 1280, 673), 3.0)                   # nunca mais que 3x
        self.assertEqual(auto_scale(40, 1920, 1009), 1.0)                 # nem menos que 1x fora de 4K


class EspacoDaTraducao(unittest.TestCase):
    def test_nunca_passa_do_espaco_livre(self):
        # antes, um minimo de 40 px deixava "LIGADO" invadir o titulo do lado de "ON"
        b = {"w": 18, "room_r": 8, "room_l": 30, "align": "left", "line_h": 9}
        self.assertLessEqual(avail_width(b), 18 + 8)

    def test_cresce_proporcional_ao_texto(self):
        b = {"w": 100, "room_r": 2000, "room_l": 0, "align": "left", "line_h": 20}
        self.assertEqual(avail_width(b), 100 + 11 * 20 if 100 + 11 * 20 > 220 else 220)


def _line(tokens, h=9):
    words, x = [], 0
    for t in tokens:
        w = len(t) * 6
        words.append({"text": t, "x": x, "y": 0, "w": w, "h": h})
        x += w + 4
    return {"text": " ".join(tokens), "x": 0, "y": 0, "w": x - 4, "h": h, "words": words, "room_r": 50, "room_l": 0}


def _box(geo, first, pt, origin, en, align, n):
    return {**{k: geo[k] for k in "xywh"}, "pt": pt, "origin": origin, "en": en, "align": align}


class TrechoTraduzido(unittest.TestCase):
    def test_numeros_e_separadores_vizinhos_entram_na_caixa(self):
        ln = _line(["530", "damage", "·", "full", "signature"])
        r = ("530 dano · signature completa", "manual",
             [(1, 2, "dano", "manual"), (3, 5, "signature completa", "manual")])
        boxes = Translator._span_boxes(ln, r, _box)
        self.assertEqual([b["pt"] for b in boxes], ["530 dano · signature completa"])

    def test_valor_com_letra_fica_com_os_pixels_do_jogo(self):
        # "8.6s" pode ter sido lido como "8.65": nao entra na caixa
        ln = _line(["85", "damage", "·", "8.6s", "·", "35..."])
        r = ("85 dano · 8.6s · 35...", "manual", [(1, 2, "dano", "manual")])
        boxes = Translator._span_boxes(ln, r, _box)
        self.assertEqual([b["pt"] for b in boxes], ["85 dano"])
        self.assertEqual(boxes[0]["room_r"], ln["words"][2]["x"] - (boxes[0]["x"] + boxes[0]["w"]))

    def test_tecla_e_barra_entram_na_caixa(self):
        ln = _line(["ABILITY", "-", "E", "/", "R"])
        r = ("HABILIDADE - E / R", "manual", [(0, 1, "HABILIDADE", "manual")])
        self.assertEqual([b["pt"] for b in Translator._span_boxes(ln, r, _box)], ["HABILIDADE - E / R"])


class FonteEstavel(unittest.TestCase):
    """Tela parada: a fonte de um texto nao pode ficar trocando entre leituras."""

    def test_escolha_nao_oscila(self):
        import types
        import main
        app = types.SimpleNamespace(_faces_memo={}, _faces_pruned=0.0)
        app._memo = types.MethodType(main.App._memo, app)
        b = {"en": "SETTINGS", "x": 900, "y": 15}
        a1 = {"family": "Lexend SemiBold", "weight": "normal", "px": 12, "below": 0, "track": 0}
        a2 = {"family": "Inter SemiBold", "weight": "normal", "px": 11, "below": 0, "track": 0}
        got = [main.App.stable_face(app, b, f)["family"] for f in (a1, a2, a1, a2, a2, a1)]
        self.assertEqual(set(got[:4]), {"Lexend SemiBold"})  # leituras alternando: fica a primeira
        px = [main.App.stable_face(app, b, f)["px"] for f in (a1, a2, a1, a2)]
        self.assertEqual(len(set(px)), 1)

    def test_cor_nao_oscila(self):
        import types
        import main
        app = types.SimpleNamespace(_faces_memo={}, _faces_pruned=0.0)
        app._memo = types.MethodType(main.App._memo, app)
        seq = ["#9aa6c3", "#ffffff", "#9aa6c3", "#ffffff", "#9aa6c3"]  # "Bow" lido na pagina Classes
        got = [main.App.stable_colors(app, {"en": "Bow", "x": 540, "y": 880, "bg": "#1a2031", "fg": c})[1] for c in seq]
        self.assertEqual(set(got), {"#9aa6c3"})


if __name__ == "__main__":
    unittest.main()
