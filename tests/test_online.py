"""Chat e traducao online (sem internet: o servidor e simulado)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import _isolar  # noqa: E402,F401  (pasta de dados temporaria; antes de config)
import config  # noqa: E402
from library import Library  # noqa: E402
from mt import OfflineTranslator  # noqa: E402
from online_mt import OnlineMT  # noqa: E402
from pipeline import Translator, chat_split, looks_portuguese  # noqa: E402

LIB = Library()


class Chat(unittest.TestCase):
    def test_separa_canal_e_nome_da_mensagem(self):
        self.assertEqual(chat_split("G (NA-DRV) RazeNBlaze420: and then says all carts are bad"),
                         (3, "and then says all carts are bad"))
        self.assertEqual(chat_split("G (EU-EVR) Khezraw: mig blaze it in the big 26"), (3, "mig blaze it in the big 26"))
        self.assertEqual(chat_split("_Toshi: anyone want to do the dungeon"), (1, "anyone want to do the dungeon"))

    def test_rotulo_com_dois_pontos_nao_e_chat(self):
        for t in ("Requires: Novice Crafting Manual", "Damage: 145 per hit", "Note: this item is bound"):
            self.assertIsNone(chat_split(t), t)

    def test_mensagem_em_portugues_nao_e_traduzida(self):
        self.assertTrue(looks_portuguese("alguem quer fazer a dungeon comigo"))
        self.assertTrue(looks_portuguese("kkkk tá bom"))
        self.assertFalse(looks_portuguese("anyone want to do the dungeon"))

    def test_mensagem_vai_para_a_fila_na_hora_e_cobre_so_a_mensagem(self):
        class FakeMT:
            ok = True
            online = None
            glossary, terms = [], {}

            def __init__(self):
                self.calls = []

            def translate_many(self, texts, keeps=None, keep_flags=None):
                self.calls.append((list(texts), list(keep_flags or [])))
                return ["alguém quer fazer a masmorra" for _ in texts]

            def pieces(self, w):
                return 1

        mt = FakeMT()
        tr = Translator(LIB, mt, dict(config.DEFAULTS))
        line = "G (NA-DRV) Bob_99: anyone want to do the dungeon"
        self.assertIsNone(tr._one(line))  # primeira vez: foi para a fila (sem esperar a segunda leitura)
        for _ in range(50):
            if mt.calls and not tr.pending:
                break
            time.sleep(0.02)
        self.assertEqual(mt.calls[0], (["anyone want to do the dungeon"], [False]))  # chat nao vai para a memoria
        pt, origin, spans = tr._one(line)
        self.assertEqual(pt, "G (NA-DRV) Bob_99: alguém quer fazer a masmorra")
        self.assertEqual([(i, j) for i, j, _, _ in spans], [(3, 9)])
        self.assertIsNone(tr._one("G (NA-DRV) Bob_99: alguem quer fazer a dungeon"))  # ja e portugues
        self.assertFalse(LIB.knows("anyone want to do the dungeon"))


class Economia(unittest.TestCase):
    def test_nome_mais_frase_conhecida_nao_vai_para_a_traducao(self):
        mt = OfflineTranslator(config.MODEL_DIR, LIB.glossary, LIB.terms)  # sabe que Kwaxu nao e palavra inglesa
        if not mt.ok:
            self.skipTest('modelo offline nao encontrado')
        tr = Translator(LIB, mt, dict(config.DEFAULTS))
        self.assertEqual(tr._one("Kwaxu has joined")[0], "Kwaxu entrou")
        self.assertEqual(tr._one("MarbleMouse743 has joined")[0], "MarbleMouse743 entrou")
        r = tr._one("[From Jm_Az (NA Hub)] started a conversation with you. Use /r or /whisper to reply.")
        self.assertEqual(r[0], "[From Jm_Az (NA Hub)] começou uma conversa com você. Use /r ou /whisper para responder.")
        self.assertIsNone(tr._one("Iron has joined", allow_mt=False))  # "Iron" nao tem cara de nome

    def test_girias_sao_traduzidas_sem_fila(self):
        tr = Translator(LIB, None, dict(config.DEFAULTS))
        self.assertEqual(tr._one("G (NA-DRV) Bob_99: ty gg")[0], "G (NA-DRV) Bob_99: valeu gg")
        self.assertEqual(tr._one("G (NA-DRV) Bob_99: lol")[0], "G (NA-DRV) Bob_99: kkkk")
        self.assertIsNone(tr._one("G (NA-DRV) Bob_99: rip", allow_mt=True))  # "rip" fica "rip": nada a desenhar

    def test_chat_curto_vai_so_para_a_offline(self):
        class FakeOnline:
            sent = []

            def available(self):
                return True

            def raw(self, texts, flags=None):
                FakeOnline.sent.append(list(texts))
                return ["[online]" for _ in texts]

        mt = OfflineTranslator(config.MODEL_DIR, LIB.glossary, LIB.terms)
        mt.online = FakeOnline()
        mt._raw = lambda texts: ["[offline]" for _ in texts]
        out = mt.translate_many(["got ore", "the server is full of people from an old regime"], None,
                                ["offline", False])
        self.assertEqual(out, ["[offline]", "[online]"])
        self.assertEqual(FakeOnline.sent, [["the server is full of people from an old regime"]])


class ChatNoMouse(unittest.TestCase):
    """Chat so e traduzido com o chat aberto (cursor visivel), na mensagem sob o mouse."""

    def _lines(self):
        def ln(text, y, x=10):
            words, cx = [], x
            for t in text.split():
                words.append({"text": t, "x": cx, "y": y, "w": len(t) * 6, "h": 10})
                cx += len(t) * 6 + 4
            return {"text": text, "x": x, "y": y, "w": cx - 4 - x, "h": 10, "words": words}
        return [ln("G (NA-DRV) Bob_99: ty gg", 100), ln("G (NA-HUB) Ann_7: lol", 114),
                ln("G (NA-HUB) Zed_1: the server is full of people", 128), ln("from an old regime", 142, x=12)]

    def test_sem_cursor_nada_do_chat(self):
        tr = Translator(LIB, None, dict(config.DEFAULTS))
        tr.pointer = None
        self.assertEqual(tr.boxes(self._lines()), [])

    def test_so_a_mensagem_sob_o_mouse(self):
        tr = Translator(LIB, None, dict(config.DEFAULTS))
        tr.pointer = (60, 104)
        out = tr.boxes(self._lines())
        self.assertEqual([b["pt"] for b in out], ["valeu gg"])
        self.assertTrue(all(b.get("chat") for b in out))
        tr.pointer = (60, 118)
        self.assertEqual([b["pt"] for b in tr.boxes(self._lines())], ["kkkk"])

    def test_mensagem_em_duas_linhas_e_uma_so(self):
        blocks, _ = Translator._chat_blocks(self._lines())
        self.assertEqual([[l["text"] for l in b] for b in blocks],
                         [["G (NA-DRV) Bob_99: ty gg"], ["G (NA-HUB) Ann_7: lol"],
                          ["G (NA-HUB) Zed_1: the server is full of people", "from an old regime"]])

        class FakeMT:
            ok, online, glossary, terms = True, None, [], {}
            sent = []

            def translate_many(self, texts, keeps=None, keep_flags=None):
                FakeMT.sent.extend(texts)
                return ["o servidor está cheio de gente de um regime antigo"]

            def pieces(self, w):
                return 1

        tr = Translator(LIB, FakeMT(), dict(config.DEFAULTS))
        tr.pointer = (40, 146)  # mouse na segunda linha da mensagem
        tr.boxes(self._lines())
        for _ in range(50):
            if FakeMT.sent and not tr.pending:
                break
            time.sleep(0.02)
        self.assertEqual(FakeMT.sent, ["the server is full of people from an old regime"])
        out = tr.boxes(self._lines())
        self.assertEqual([b["pt"] for b in out], ["G (NA-HUB) Zed_1: o servidor está cheio de gente de um regime antigo"])
        self.assertEqual(out[0]["lines"], 2)


class MemoriaCompartilhada(unittest.TestCase):
    def test_traducao_de_outro_jogador_sai_sem_internet(self):
        mt = OfflineTranslator(config.MODEL_DIR, LIB.glossary, LIB.terms)
        mt.online = None
        mt.shared = {"Your <k>Z0</k> is full of <k>N0</k> stones": "Sua <k>Z0</k> está cheia de <k>N0</k> pedras"}
        mt._raw = lambda texts: ["[offline]" for _ in texts]
        self.assertEqual(mt.translate_many(["Your bag is full of 30 stones"]), ["Sua bolsa está cheia de 30 pedras"])
        self.assertEqual(mt.translate_many(["Something else entirely here"]), ["[offline]"])

    def test_arquivo_do_programa_e_valido(self):
        from online import _valid_shared
        with open(config.SEED_SHARED, encoding="utf-8") as f:
            self.assertTrue(_valid_shared(__import__("json").load(f)))


class Online(unittest.TestCase):
    def test_marcador_vai_protegido_e_volta(self):
        w, nums = OnlineMT._wrap("Open your Zq0x & check <stats>")
        self.assertEqual(w, "Open your <k>Z0</k> &amp; check &lt;stats&gt;")
        self.assertEqual(OnlineMT._unwrap("Abra sua <k>Z0</k> &amp; veja &lt;stats&gt;", nums),
                         "Abra sua Zq0x & veja <stats>")

    def test_numeros_viram_marcador_e_voltam(self):
        a, na = OnlineMT._wrap("Reach level 10 with Zq0x in 2.5s")
        b, nb = OnlineMT._wrap("Reach level 11 with Zq0x in 3.5s")
        self.assertEqual(a, b)  # mesmo texto para a memoria compartilhada: paga uma vez so
        self.assertEqual(a, "Reach level <k>N0</k> with <k>Z0</k> in <k>N1</k>s")
        self.assertEqual(OnlineMT._unwrap("Chegue ao nível <k>N0</k> com <k>Z0</k> em <k>N1</k>s", nb),
                         "Chegue ao nível 11 com Zq0x em 3.5s")

    def test_usa_o_servidor_e_mantem_termos_e_concordancia(self):
        mt = OfflineTranslator(config.MODEL_DIR, LIB.glossary, LIB.terms)

        class FakeOnline:
            sent = []

            def available(self):
                return True

            def raw(self, texts, flags=None):
                FakeOnline.sent.append((list(texts), flags))
                return ["Sua Zq0x está cheia" if "Zq0x" in t else "ok" for t in texts]

        mt.online = FakeOnline()
        out = mt.translate_many(["Your bag is full"], [()], [True])
        self.assertEqual(out, ["Sua bolsa está cheia"])
        self.assertEqual(FakeOnline.sent[0], (["Your Zq0x is full"], [True]))

    @unittest.skipUnless(OfflineTranslator(config.MODEL_DIR, [], {}).ok, "modelo offline nao encontrado")
    def test_servidor_fora_do_ar_usa_o_offline(self):
        mt = OfflineTranslator(config.MODEL_DIR, LIB.glossary, LIB.terms)
        mt.online = OnlineMT("http://127.0.0.1:9")  # porta fechada
        t0 = time.monotonic()
        out = mt.translate_many(["The week starts again soon"])
        self.assertTrue(out[0])
        self.assertFalse(mt.online.available())  # nao tenta de novo por 60 s
        self.assertLess(time.monotonic() - t0, 6)


if __name__ == "__main__":
    unittest.main()
