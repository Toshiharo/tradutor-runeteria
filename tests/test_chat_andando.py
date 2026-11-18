"""Andando pelo mundo (sem cursor) nada do chat e traduzido - nem os avisos e pedacos de mensagem que
nao tem "canal nome:" ("Kwaxu has joined", "jenin: rip", "[Copper] Semedar: ..."). Com o chat aberto,
so o que esta sob o mouse; e essas linhas vao como chat (nunca para a memoria compartilhada)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import _isolar  # noqa: E402,F401  (pasta de dados temporaria; antes de config)
import config  # noqa: E402
from library import Library  # noqa: E402
from pipeline import Translator  # noqa: E402

LIB = Library()


def ln(text, y, x=10, h=10):
    words, cx = [], x
    for t in text.split():
        words.append({"text": t, "x": cx, "y": y, "w": len(t) * 6, "h": h})
        cx += len(t) * 6 + 4
    return {"text": text, "x": x, "y": y, "w": cx - 4 - x, "h": h, "words": words}


class FakeMT:
    ok, online, glossary, terms = True, None, [], {}

    def __init__(self):
        self.calls = []

    def translate_many(self, texts, keeps=None, keep_flags=None):
        self.calls.append((list(texts), list(keep_flags or [])))
        return ["minerador de veios nisso, sera" for _ in texts]

    def pieces(self, w):
        return 1


def chat():
    return [ln("Welcome golonkiusz to Runeteria!", 86),
            ln("G (NA-DRV) Bob_99: the server is full of people today", 100),
            ln("jenin: vein miner on it?", 114),
            ln("[Copper] Semedar: I bought out the whole market yesterday", 128),
            ln("G (NA-HUB) Zed_1: anyone selling adamantite ore for cheap", 142),
            ln("and some extra leather too", 156, x=12),
            ln("partzel: the server is full of people of an old regime", 170)]


HUD = [ln("Your bags are empty.", 300, x=600, h=14)]  # texto de tela fora do chat: continua traduzido


def wait(mt, tr):
    for _ in range(60):
        if not tr.pending and tr.q.empty():
            break
        time.sleep(0.02)
    time.sleep(0.05)


class Andando(unittest.TestCase):
    def test_sem_cursor_nada_do_chat_e_nada_vai_para_a_traducao(self):
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(config.DEFAULTS))
        tr.pointer = None
        for _ in range(4):  # varias leituras: texto de tela desconhecido iria para a fila depois de ~1,5 s
            out = tr.boxes(chat() + HUD)
            time.sleep(0.6)
        wait(mt, tr)
        self.assertEqual([b["pt"] for b in out], ["Suas bolsas estão vazias."])
        self.assertEqual(mt.calls, [])

    def test_sem_mensagem_reconhecida_o_lugar_do_chat_fica_lembrado(self):
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(config.DEFAULTS))
        tr.pointer = None
        tr.boxes(chat())  # aprende onde o chat fica
        so_avisos = [ln("Kwaxu has joined", 128), ln("jenin: rip my pickaxe again", 142),
                     ln("Welcome Dast17 to Runeteria!", 156)]
        for _ in range(4):
            out = tr.boxes(so_avisos + HUD)
            time.sleep(0.6)
        wait(mt, tr)
        self.assertEqual([b["pt"] for b in out], ["Suas bolsas estão vazias."])
        self.assertEqual(mt.calls, [])

    def test_com_o_mouse_em_cima_traduz_como_chat(self):
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(config.DEFAULTS))
        tr.pointer = (60, 119)  # em cima de "jenin: vein miner on it?"
        tr.boxes(chat())
        wait(mt, tr)
        out = tr.boxes(chat())
        self.assertEqual([b["en"] for b in out], ["jenin: vein miner on it?"])
        self.assertTrue(all(b.get("chat") for b in out))
        self.assertTrue(mt.calls and all(f is not True for _, flags in mt.calls for f in flags))  # nunca "tela"

    def test_menu_aberto_em_outro_lugar_continua_traduzido(self):
        tr = Translator(LIB, None, dict(config.DEFAULTS))
        tr.pointer = (700, 400)
        menu = [ln("Your bags are empty.", 300, x=600, h=14), ln("Settings", 60, x=14, h=10)]
        pts = sorted(b["pt"] for b in tr.boxes(chat() + menu))
        self.assertIn("Suas bolsas estão vazias.", pts)
        self.assertIn("Ajustes", pts)  # mesma margem do chat, mas longe da pilha de mensagens

    def test_lugar_fixo_do_chat_sem_nenhuma_mensagem_reconhecida(self):
        # captura real 1920x1015: so avisos de entrada, nenhuma linha "canal nome:", primeira leitura
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(config.DEFAULTS))
        tr.pointer, tr.view = None, (1920, 1015)
        avisos = [ln("Welcome zuul to Runeteria!", 325, x=52, h=14), ln("zuul has joined [NA] NA Hub.", 375, x=52, h=14),
                  ln("Kalipsto has joined [NA] NA Hub.", 525, x=52, h=14), ln("Cole789 has joined [NA] NA Hub.", 700, x=52, h=14)]
        hud = [ln("Your bags are empty.", 300, x=900, h=14), ln("Settings", 120, x=52, h=14)]
        for _ in range(4):
            out = tr.boxes(avisos + hud)
            time.sleep(0.6)
        wait(mt, tr)
        self.assertEqual(sorted(b["pt"] for b in out), ["Ajustes", "Suas bolsas estão vazias."])
        self.assertEqual(mt.calls, [])

    def test_texto_do_jogo_em_portugues_nao_vai_para_a_traducao(self):
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(config.DEFAULTS))
        for t in ["Modo de voo", "Velocidade de movimento", "Inventårio", "Sem colisäo", "Voltar"]:
            for _ in range(3):
                tr._one(t)
                time.sleep(0.6)
        wait(mt, tr)
        self.assertEqual(mt.calls, [])


if __name__ == "__main__":
    unittest.main()
