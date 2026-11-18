"""Nomes proprios, partes variaveis e linhas de tooltip. Casos tirados de telas reais do Runeteria.

Rodar:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

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
        for t in ["143", "+7", "7.7s", "1-22%", "(1-6%)", "4/4", "18:12", "32...", "Lv.20", "Q", "x3", "+0.4"]:
            self.assertTrue(is_value_token(t), t)
        for t in ["Armor", "damage", "a", "Lv"]:
            self.assertFalse(is_value_token(t), t)

    def test_atributos_por_partes(self):
        self.assertEqual(TR.compose("Armor 15 Vitality +7")[0], "Armadura 15 Vitalidade +7")

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
        self.assertIsNone(LIB.lookup("Max level"))

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


if __name__ == "__main__":
    unittest.main()
