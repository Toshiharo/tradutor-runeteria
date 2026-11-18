"""Os testes nao podem ler nem gravar os dados de quem esta rodando (memoria automatica, correcoes):
o resultado mudava conforme o que o jogador tinha na memoria, e rodar os testes apagava/sujava a memoria real.
Importar ANTES de `config`: troca a pasta de dados por uma temporaria, vazia."""
import os
import tempfile

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="rt_testes_")
