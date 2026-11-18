"""Chat e traducao online (sem internet: o servidor e simulado)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

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


class Online(unittest.TestCase):
    def test_marcador_vai_protegido_e_volta(self):
        w = OnlineMT._wrap("Open your Zq0x & check <stats>")
        self.assertEqual(w, "Open your <k>Zq0x</k> &amp; check &lt;stats&gt;")
        self.assertEqual(OnlineMT._unwrap("Abra sua <k>Zq0x</k> &amp; veja &lt;stats&gt;"), "Abra sua Zq0x & veja <stats>")

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
