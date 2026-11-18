"""Filtro da memoria compartilhada (tools/baixar_memoria.py): o servidor aceita texto de qualquer um,
entao so texto com cara de tela do jogo pode ir para o arquivo que todos os jogadores recebem."""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import _isolar  # noqa: E402,F401  (pasta de dados temporaria; antes de config)
spec = importlib.util.spec_from_file_location("baixar_memoria", os.path.join(ROOT, "tools", "baixar_memoria.py"))
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)


class Filtro(unittest.TestCase):
    def test_texto_de_tela_entra(self):
        for en, pt in [
            ("Your <k>Z0</k> is full of <k>N0</k> stones", "Sua <k>Z0</k> está cheia de <k>N0</k> pedras"),
            ("Teleport cancelled - you moved.", "Teletransporte cancelado - você se mexeu."),
            ("Hide closed &amp; sold-out shops", "Ocultar lojas fechadas e esgotadas"),
            ("SAVE CONFIG", "SALVAR CONFIGURAÇÃO"),
            ("Try again in a moment, or read it at runeteria.com/wiki.",
             "Tente de novo daqui a pouco, ou leia em runeteria.com/wiki."),
            ("Level <k>N0</k> - in <k>N1</k> levels", "Nível <k>N0</k> - em <k>N1</k> níveis"),
        ]:
            self.assertTrue(bm.good(en, pt), en)

    def test_lixo_e_propaganda_ficam_de_fora(self):
        for en, pt in [
            ("Buy cheap coins at www.example.com now", "Compre moedas baratas em www.example.com agora"),
            ("join discord.gg/abcdef for free loot", "entre em discord.gg/abcdef para loot grátis"),
            ("contact me @someone for gold", "fale comigo @someone para ouro"),
            ("Привет всем игрокам сервера", "Olá a todos os jogadores do servidor"),
            ("aaaaaaaaaaaaaaaaaaaaaaaa", "aaaaaaaaaaaaaaaaaaaaaaab"),
            # conversa de jogador e texto do proprio Hytale em portugues (casos reais da memoria da 1.1.0)
            ("[Copper] maryng: keep it i have many", "[Copper] maryng: pode ficar, eu tenho muitos"),
            ("<k>Z0</k>: Thank you soo much Cole!", "<k>Z0</k>: Muito obrigado, Cole!"),
            ("Nickelnite: sure, Cole, in a minute", "Nickelnite: claro, Cole, em um minuto"),
            ("Faize has joined", "Faize entrou"),
            ("Arrasto de voo", "Arrastamento em voo"),
            ("Inventårio", "Inventário"),
            ("12 / 40 - 3.5%", "12 / 40 - 3,5%"),
            ("x" * 700 + " word", "y" * 700 + " palavra"),
            ("Open the <k>Z0</k> bag", "Abra a bolsa"),          # perdeu o marcador
            ("Settings", "Settings"),                            # nao traduziu
            ("First line\nsecond line", "Primeira linha\nsegunda linha"),
        ]:
            self.assertFalse(bm.good(en, pt), en[:40])


if __name__ == "__main__":
    unittest.main()
