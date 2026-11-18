"""Nomes proprios, partes variaveis e linhas de tooltip. Casos tirados de telas reais do Runeteria.

Rodar:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

import _isolar  # noqa: E402,F401  (pasta de dados temporaria; antes de config)
import config  # noqa: E402
from library import Library, adapt  # noqa: E402
from mt import OfflineTranslator  # noqa: E402
from pipeline import Translator  # noqa: E402
from variaveis import find_names, is_value_token  # noqa: E402

LIB = Library()
MT = OfflineTranslator(config.MODEL_DIR, LIB.glossary, LIB.terms)
TR = Translator(LIB, MT, dict(config.DEFAULTS))


class Nomes(unittest.TestCase):
    def test_nomes_ficam_em_ingles(self):
        for t in ["Precision Strike", "Epic Gatherer's Vest", "The Deepworks", "Boomshroom Plague",
                  "Halloween Demonic Warhorse", "Bleeding Slice", "Entangling Shot", "Boomshroom"]:
            self.assertTrue(TR.is_name(t), t)

    def test_rotulos_nao_sao_nomes(self):
        for t in ["Not Listed", "Key binding Unlocks at", "Signature Slot", "Ability Slots", "PLAYING SOLO",
                  "Max level", "Your bags are empty.", "Bow", "Settings", "Daily Quest"]:
            self.assertFalse(TR.is_name(t), t)

    def test_nome_de_jogador_no_chat_nao_e_traduzido(self):
        from variaveis import is_noise
        self.assertTrue(is_noise("honkdaddy", TR.unknown_word))
        self.assertTrue(is_noise("Ver0420", TR.unknown_word))
        self.assertFalse(is_noise("Settings", TR.unknown_word))
        self.assertFalse(is_noise("inventory", TR.unknown_word))

    def test_nomes_dentro_da_frase(self):
        names = find_names("Cast Shadow Dance on Velcorne to hit all enemies", [], TR.unknown_word)
        self.assertIn("Shadow Dance", names)
        self.assertIn("Velcorne", names)
        self.assertIn("Ver0420", find_names("Welcome Ver0420 to Runeteria!", [], TR.unknown_word))

    def test_traducao_automatica_preserva_nomes(self):
        text = "Cast Shadow Dance to hit all enemies"
        pt = MT.translate(text, TR.names_in(text))
        self.assertIn("Shadow Dance", pt)


class Tooltip(unittest.TestCase):
    def test_valores(self):
        for t in ["143", "+7", "7.7s", "1-22%", "(1-6%)", "4/4", "18:12", "32...", "Lv.20", "Q", "x3", "+0.4",
                  "32.„", "s", "g.6s", "7.75"]:  # sujeira real do OCR na pagina Classes
            self.assertTrue(is_value_token(t), t)
        for t in ["Armor", "damage", "a", "Lv", "Slot", "go"]:
            self.assertFalse(is_value_token(t), t)

    def test_atributos_por_partes(self):
        r = TR.compose("Armor 15 Vitality +7")
        self.assertEqual(r[0], "Armadura 15 Vitalidade +7")
        self.assertEqual([(i, j, pt) for i, j, pt, _ in r[2]], [(0, 1, "Armadura"), (2, 3, "Vitalidade")])

    def test_so_a_palavra_traduzida_e_coberta(self):
        r = TR.compose("ABILITY - E / R")
        self.assertEqual([(i, j, pt) for i, j, pt, _ in r[2]], [(0, 1, "HABILIDADE")])
        r = TR.compose("530 damage · full signature")
        self.assertIsNotNone(r)
        self.assertEqual(r[2][0][:3], (1, 2, "dano"))

    def test_linha_de_skill_com_separadores(self):
        r = TR.compose("Bleeding Slice 143 damage • 7.7s • 32...")
        self.assertIsNotNone(r)
        self.assertTrue(r[0].startswith("Bleeding Slice 143 "), r)
        self.assertTrue(r[0].endswith(" • 7.7s • 32..."), r)

    def test_frase_comum_nao_e_montada_palavra_por_palavra(self):
        self.assertIsNone(TR.compose("You have no keys yet for this door"))
        self.assertIsNone(TR.compose("Iron Pickaxe and 4 more Level 8 - in 5 levels"))


class Variaveis(unittest.TestCase):
    def test_troca_nome_de_loja(self):
        pt = adapt("This stand is Branch #2 of Bob's Shop.", "This stand is Branch #1 of Toshi's Forge & Armory.",
                   "Esta banca é a Filial #1 de Toshi's Forge & Armory.", True)
        self.assertEqual(pt, "Esta banca é a Filial #1 de Bob's Shop.")  # o numero e reposto depois (lookup)

    def test_troca_nome_de_jogador(self):
        self.assertEqual(adapt("Welcome Bob99 to Runeteria!", "Welcome Ver0420 to Runeteria!",
                               "Bem-vindo, Ver0420, ao Runeteria!", True), "Bem-vindo, Bob99, ao Runeteria!")

    def test_erro_de_ocr_nao_atrapalha(self):
        self.assertEqual(adapt("Your bags are cmpty.", "Your bags are empty.", "Suas bolsas estão vazias.", True),
                         "Suas bolsas estão vazias.")

    def test_palavra_diferente_que_muda_o_sentido_e_recusada(self):
        # antes, "parecido o bastante" mostrava a traducao do outro texto
        self.assertIsNone(adapt("Rent this Shop", "Rent this Stall", "Alugar esta Banca", True))
        self.assertIsNone(adapt("Sell to Guild", "Sell to Shop", "Vender para a loja", True))

    def test_lookup_completo_com_numero(self):
        r = LIB.lookup("This stand is Branch #3 of Bob's Shop.")
        self.assertIsNotNone(r)
        self.assertEqual(r[0], "Esta banca é a Filial #3 de Bob's Shop.")


class CasosDoReplay(unittest.TestCase):
    """Erros achados passando os textos reais da memoria automatica pelo fluxo novo."""

    def test_palavra_comum_copiada_nao_e_variavel(self):
        self.assertIsNone(adapt("Max level", "ITEM LEVEL", "NÍVEL DO ITEM", False))
        r = LIB.lookup("Max level")  # pode existir na memoria automatica ("Nivel maximo"), mas nunca o "ITEM" trocado
        self.assertTrue(r is None or "Max" not in r[0], r)

    def test_erro_de_ocr_so_em_texto_quase_igual(self):
        self.assertIsNone(adapt("Requires", "REQUEST", "PEDIR", False))

    def test_nome_no_comeco_da_linha_de_skill(self):
        r = TR.compose("Hemorrhage 145 damage • 7.7s • 32")
        self.assertIsNotNone(r)
        self.assertTrue(r[0].startswith("Hemorrhage 145 "), r)

    def test_valores_protegidos_na_traducao_automatica(self):
        self.assertIn("7.7s", TR.names_in("Deals damage over 7.7s to everyone"))

    def test_termo_composto(self):
        self.assertEqual(MT.translate("Ability Slots"), "Espaços de habilidade")
        self.assertEqual(TR.compose("322% weapon damage")[0], "322% dano de arma")

    def test_comando_do_chat_nao_e_traduzido(self):
        self.assertIn("/mount", MT.translate("Use /mount to summon it"))

    def test_rotulo_com_parenteses_nao_e_nome(self):
        self.assertFalse(TR.is_name("Agility (Scaling)"))

    def test_termo_fixo_nao_e_protegido_como_nome(self):
        self.assertNotIn("Pickaxe", TR.names_in("Iron Pickaxe and 4 more Level 8"))


class ObjetivoDeMissao(unittest.TestCase):
    def test_verbo_antes_da_quantidade(self):
        r = TR.compose("Mine 15 Rock Blocks")
        self.assertEqual(r[0], "Minere 15 Rock Blocks")   # nao "Meus 15 Rock Blocks"
        self.assertEqual([(i, j, pt) for i, j, pt, _ in r[2]], [(0, 1, "Minere")])
        self.assertEqual(TR.compose("Gather 12 Stone Rubble")[0], "Colete 12 Stone Rubble")

    def test_rotulo_mine_continua_valendo_fora_de_objetivo(self):
        self.assertEqual(LIB.lookup("Mine")[0], "Meus")


class FeedbackBeta(unittest.TestCase):
    """Problemas relatados por jogadores na beta."""

    def test_nome_de_servidor_lido_com_erro_fica_em_ingles(self):
        for t in ("EVE' RR@OT FOREST", "BRAVEWIND PEAKS", "MO MO RI WILDS (COMING SOON)"):
            self.assertIsNone(TR._one(t, allow_mt=False), t)
        for t in ("FOREST", "Guild Activity", "Overview"):
            self.assertFalse(TR._garbled_name(t), t)

    def test_maiuscula_separada_pelo_ocr(self):
        from pipeline import tidy_lines
        ws = [{"text": "T", "x": 0, "y": 0, "w": 6, "h": 10}, {"text": "wo", "x": 6, "y": 2, "w": 12, "h": 8},
              {"text": "skill", "x": 22, "y": 0, "w": 20, "h": 10}]
        self.assertEqual(tidy_lines([{"text": "T wo skill", "x": 0, "y": 0, "w": 42, "h": 10, "words": ws}])[0]["text"],
                         "Two skill")
        ws = [{"text": "I", "x": 0, "y": 0, "w": 3, "h": 10}, {"text": "in", "x": 5, "y": 2, "w": 9, "h": 8}]
        self.assertEqual(tidy_lines([{"text": "I in", "x": 0, "y": 0, "w": 14, "h": 10, "words": ws}])[0]["text"],
                         "I in")

    def test_requer_e_velocidade(self):
        self.assertEqual(TR._one("Requires 1 Novice Crafting Manual")[0], "Requer 1 Novice Crafting Manual")
        self.assertEqual(TR._one("Mining Speed +5%")[0], "Velocidade de mineração +5%")
        self.assertEqual(TR._one("NO DUNGEON SELECTED")[0], "NENHUMA MASMORRA SELECIONADA")

    @unittest.skipUnless(MT.ok, "modelo offline nao encontrado")
    def test_concordancia_e_stun(self):
        self.assertIn("Nenhuma masmorra selecionada", MT.translate_many(["No dungeon selected yet"])[0])
        self.assertIn("atordoa", MT.translate_many(["This attack stuns the target for 2 seconds."])[0])


class FraseComTraco(unittest.TestCase):
    def test_frase_depois_de_traco_nao_vira_meio_traduzida(self):
        r = TR.compose("Your guild - here is what happened while you were away.")
        self.assertIsNone(r)   # nao "Sua guilda - here is what happened..."


class Cards(unittest.TestCase):
    def _l(self, text, x, y, h=12):
        return {"text": text, "x": x, "y": y, "w": len(text) * 7, "h": h}

    def test_titulo_de_card_acima_de_atributo_e_nome(self):
        title = self._l("Hemorrhage", 300, 460)
        stat = self._l("145 damage • 7.7s • 32...", 284, 480, 10)
        other = self._l("Your Build", 230, 140)
        ids = TR._card_titles([title, stat, other])
        self.assertIn(id(title), ids)
        self.assertNotIn(id(other), ids)
        self.assertIsNone(TR._one("Hemorrhage", title=True))

    def _row(self, tokens, gap):
        words, x = [], 0
        for tok in tokens:
            words.append({"text": tok, "x": x, "y": 0, "w": len(tok) * 7, "h": 9})
            x += len(tok) * 7 + gap
        return {"text": " ".join(tokens), "x": 0, "y": 0, "w": x - gap, "h": 9, "words": words}

    def test_fileira_de_abas_vira_uma_caixa_por_aba(self):
        box = lambda geo, first, pt, origin, en, align, n: {"pt": pt, "en": en, **{k: geo[k] for k in "xywh"}}
        row = TR._label_row(self._row(["PROFESSIONS", "CLASSES", "PARTY"], 30), box, [])
        self.assertEqual([b["pt"] for b in row], ["PROFISSÕES", "GRUPO"])  # CLASSES fica igual

    def test_frase_comum_nao_e_fileira(self):
        box = lambda *a: {}
        self.assertEqual(TR._label_row(self._row(["Max", "level"], 3), box, []), [])


if __name__ == "__main__":
    unittest.main()
