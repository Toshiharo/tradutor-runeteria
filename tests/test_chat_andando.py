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
CFG = dict(config.DEFAULTS, traduzir_chat=True)  # a opcao da janela ligada (vem desligada)


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
        tr = Translator(LIB, mt, dict(CFG))
        tr.pointer = None
        for _ in range(4):  # varias leituras: texto de tela desconhecido iria para a fila depois de ~1,5 s
            out = tr.boxes(chat() + HUD)
            time.sleep(0.6)
        wait(mt, tr)
        self.assertEqual([b["pt"] for b in out], ["Suas bolsas estão vazias."])
        self.assertEqual(mt.calls, [])

    def test_sem_mensagem_reconhecida_o_lugar_do_chat_fica_lembrado(self):
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(CFG))
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
        tr = Translator(LIB, mt, dict(CFG))
        tr.pointer = (60, 119)  # em cima de "jenin: vein miner on it?"
        tr.boxes(chat())
        wait(mt, tr)
        out = tr.boxes(chat())
        self.assertEqual([b["en"] for b in out], ["jenin: vein miner on it?"])
        self.assertTrue(all(b.get("chat") for b in out))
        self.assertTrue(mt.calls and all(f is not True for _, flags in mt.calls for f in flags))  # nunca "tela"

    def test_menu_aberto_em_outro_lugar_continua_traduzido(self):
        tr = Translator(LIB, None, dict(CFG))
        tr.pointer = (700, 400)
        menu = [ln("Your bags are empty.", 300, x=600, h=14), ln("Settings", 60, x=14, h=10)]
        pts = sorted(b["pt"] for b in tr.boxes(chat() + menu))
        self.assertIn("Suas bolsas estão vazias.", pts)
        self.assertIn("Ajustes", pts)  # mesma margem do chat, mas longe da pilha de mensagens

    def test_lugar_fixo_do_chat_sem_nenhuma_mensagem_reconhecida(self):
        # captura real 1920x1015: so avisos de entrada, nenhuma linha "canal nome:", primeira leitura
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(CFG))
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

    def test_cada_linha_e_uma_mensagem_e_o_mouse_pega_so_a_dele(self):
        # captura real: mensagem comprida seguida de avisos "has joined". Antes viravam um bloco so, a
        # traducao saia com as tres linhas juntas e o mouse "pegava" a mensagem errada
        tr = Translator(LIB, FakeMT(), dict(CFG))
        tr.view = (1920, 1015)
        rows = ["G (NA-DRV) Puchinin: Type /homestead to upgrade and beat up Ghoats",
                "JeffRie23 has joined [NAI NA Hub.", "Haschbiten has joined [NAI NA Hub",
                "G (NA-HUB) MateusTeles: Hello guys! new player here", "KippieLapdrap has joined [NA] NA Hub."]

        def read(i):
            tr.pointer = (300, 330 + i * 25 + 7)
            out = []
            for _ in range(3):
                out = tr.boxes([ln(t, 330 + k * 25, x=52, h=14) for k, t in enumerate(rows)])
                wait(tr.mt, tr)
            return out
        blocks, _ = tr._chat_blocks([ln(t, 330 + k * 25, x=52, h=14) for k, t in enumerate(rows)])
        self.assertTrue(all(len(b) == 1 for b in blocks))
        for i in (1, 2, 4):  # aviso de jogador entrando: nunca e traduzido, nem com o mouse em cima
            self.assertEqual(read(i), [], rows[i])
        out = read(3)  # a mensagem do MateusTeles: uma caixa so, na linha dele, so sobre a mensagem
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["y"], 330 + 3 * 25)
        self.assertGreater(out[0]["x"], 150)  # comeca depois de "G (NA-HUB) MateusTeles:"

    def test_opcao_desligada_nada_do_chat_nem_com_o_mouse_em_cima(self):
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(config.DEFAULTS))  # padrao: "traduzir_chat" desligado
        tr.view = (1920, 1015)
        rows = ["G (NA-DRV) Bob_99: ty gg", "G (NA-HUB) Zed_1: anyone selling adamantite ore for cheap",
                "zuul has joined [NA] NA Hub."]
        for i in range(len(rows)):
            tr.pointer = (300, 330 + i * 25 + 7)
            for _ in range(3):
                out = tr.boxes([ln(t, 330 + k * 25, x=52, h=14) for k, t in enumerate(rows)] + HUD)
                time.sleep(0.4)
            self.assertEqual([b["pt"] for b in out], ["Suas bolsas estão vazias."])
        wait(mt, tr)
        self.assertEqual(mt.calls, [])

    def test_aviso_de_entrada_nunca_e_traduzido(self):
        # chat aberto (cursor visivel) so com avisos, sem nenhuma mensagem "canal nome:", opcao ligada ou nao,
        # com ou sem o tamanho da janela, com o mouse em cima: nada e traduzido nem vai para a traducao
        from pipeline import login_notice
        avisos = ["zuul has joined [NA] NA Hub.", "Kwaxu has joined", "Jm_Az joined [NAI NA Hub",
                  "Welcome zuul to Runeteria!", "Deithy has joined [NAI NA Hub", "Faize has left"]
        for t in avisos:
            self.assertTrue(login_notice(t), t)
        for t in ["_Toshi joined the guild", "Ncmb was promoted", "Join a party", "Welcome, make yourself at home!"]:
            self.assertFalse(login_notice(t), t)
        for cfg in (dict(CFG), dict(config.DEFAULTS)):
            for view in ((1920, 1015), None):
                mt = FakeMT()
                tr = Translator(LIB, mt, cfg)
                tr.view = view
                for i in range(len(avisos)):
                    tr.pointer = (300, 330 + i * 25 + 7)
                    for _ in range(3):
                        out = tr.boxes([ln(t, 330 + k * 25, x=52, h=14) for k, t in enumerate(avisos)] + HUD)
                        time.sleep(0.25)
                    self.assertEqual([b["pt"] for b in out], ["Suas bolsas estão vazias."])
                wait(mt, tr)
                self.assertEqual(mt.calls, [])
                for t in avisos:
                    self.assertIsNone(tr._one(t), t)

    def test_aviso_lido_em_dois_pedacos(self):
        # captura real: "OneTimeACraft has joined" + "[NA] NA Hub." (em negrito) saem como duas linhas do leitor;
        # o segundo pedaco aparecia com uma caixa "NA Hub" por cima
        from pipeline import login_notice
        for t in ["[NA] NA Hub.", "[NAI NA Hub", "[EU] EU Hub."]:
            self.assertTrue(login_notice(t), t)
        for cfg in (dict(CFG), dict(config.DEFAULTS)):
            for view in ((1920, 1015), None):
                tr = Translator(LIB, None, cfg)
                tr.view = view
                rows = [ln("OneTimeACraft has joined", 400, x=52, h=14), ln("[NA] NA Hub.", 400, x=250, h=14),
                        ln("G (NA-DRV) Bob_99: hello there my friends", 425, x=52, h=14), ln("Hub", 425, x=420, h=14)]
                for ptr in (None, (300, 407), (270, 407)):
                    tr.pointer = ptr
                    self.assertEqual([b["pt"] for b in tr.boxes(rows + HUD)], ["Suas bolsas estão vazias."])

    def test_texto_do_jogo_em_portugues_nao_vai_para_a_traducao(self):
        mt = FakeMT()
        tr = Translator(LIB, mt, dict(CFG))
        for t in ["Modo de voo", "Velocidade de movimento", "Inventårio", "Sem colisäo", "Voltar"]:
            for _ in range(3):
                tr._one(t)
                time.sleep(0.6)
        wait(mt, tr)
        self.assertEqual(mt.calls, [])


if __name__ == "__main__":
    unittest.main()
