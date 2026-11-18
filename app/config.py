"""Caminhos e configuracoes do Tradutor Runeteria."""
import json
import os
import sys

APP_NAME = "Tradutor Runeteria"
APP_VERSION = "1.1.2"   # mude aqui e em instalador.iss ao publicar uma versao nova (tag v1.0.0 no GitHub)
# servidor de traducao online (servidor/worker.js no Cloudflare). Vazio = so a traducao offline
ONLINE_MT_URL = "https://tradutor-runeteria.translator-runeteria.workers.dev"
APP_STAGE = "beta"      # "beta" mostra o aviso de versao de testes na janela; "" na versao final
REPO = "Toshiharo/tradutor-runeteria"

# Pasta onde ficam os arquivos que vem junto com o programa (biblioteca, modelo)
if getattr(sys, "frozen", False):
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

FROZEN = bool(getattr(sys, "frozen", False))
DATA_DIR = os.path.join(BUNDLE_DIR, "data")
FONTS_DIR = os.path.join(BUNDLE_DIR, "fonts")
ICON_FILE = os.path.join(BUNDLE_DIR, "icone.ico")
LOGO_FILE = os.path.join(BUNDLE_DIR, "assets", "logo_runeteria.png")  # logo oficial do Runeteria
MODEL_DIR = os.path.join(BUNDLE_DIR, "modelos", "en_pt")
if not os.path.isdir(MODEL_DIR):  # rodando direto do codigo-fonte
    MODEL_DIR = os.path.join(os.path.dirname(BUNDLE_DIR), "modelos", "en_pt")

APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
HYTALE_USERDATA = os.path.join(APPDATA, "Hytale", "UserData")
HYTALE_LOGS = os.path.join(HYTALE_USERDATA, "Logs")
HYTALE_CACHE = os.path.join(HYTALE_USERDATA, "CachedAssets")

# Pasta do usuario (traducoes salvas, configuracao)
USER_DIR = os.path.join(APPDATA, "RuneteriaTradutor")
os.makedirs(USER_DIR, exist_ok=True)

SEED_LIBRARY = os.path.join(DATA_DIR, "biblioteca.json")
SEED_GLOSSARY = os.path.join(DATA_DIR, "glossario.json")
SEED_SHARED = os.path.join(DATA_DIR, "compartilhada.json")  # memoria do servidor (DeepL), copiada para o repositorio
USER_OVERRIDES = os.path.join(USER_DIR, "minhas_traducoes.json")
USER_GLOSSARY = os.path.join(USER_DIR, "glossario.json")
MEMORY_FILE = os.path.join(USER_DIR, "memoria_automatica.json")
UPDATER_STATE = os.path.join(USER_DIR, "atualizador_estado.json")
NEW_TEXTS_LOG = os.path.join(USER_DIR, "textos_novos.txt")
SCREEN_DUMP = os.path.join(USER_DIR, "ultima_tela.txt")
CONFIG_FILE = os.path.join(USER_DIR, "config.json")
ERROR_LOG = os.path.join(USER_DIR, "erros.log")
# copias mais novas da biblioteca/glossario baixadas do repositorio (ver online.py)
ONLINE_DIR = os.path.join(USER_DIR, "online")
ONLINE_LIBRARY = os.path.join(ONLINE_DIR, "biblioteca.json")
ONLINE_GLOSSARY = os.path.join(ONLINE_DIR, "glossario.json")
ONLINE_SHARED = os.path.join(ONLINE_DIR, "compartilhada.json")

DEFAULTS = {
    "servidor": "runeteria.com",
    "intervalo_segundos": 0.8,
    "escala_ocr": "auto",   # "auto" = acompanha o tamanho do texto (qualquer resolucao); ou um numero, ex. 1.6
    "similaridade_minima": 86,
    "traduzir_desconhecidos": True,
    "atualizar_pela_internet": True,   # baixa traducoes novas e avisa de versao nova (so leitura, nada e enviado)
    "tamanho_fonte_min": 6,   # em pixels; o overlay nunca fica menor que isso nem que 60% do original
    "permitir_gravar": True,
    "traducao_online": True,
    "chat_ao_passar_o_mouse": True,  # chat so e traduzido com o chat aberto, na mensagem sob o mouse   # texto que nao esta na biblioteca: traduz no servidor (melhor e mais rapido)   # a traducao aparece em gravacoes/transmissoes (OBS, Discord, Xbox Game Bar)
    "fonte_overlay": "auto",   # auto = mesma fonte do jogo (Lexend/Inter/Cormorant); ou um nome, ex. "Segoe UI"
    "usar_cores_da_tela": True,   # traducao com as cores do texto original; False = cores fixas abaixo
    "opacidade_fundo": "#141821",
    "cor_texto": "#f2e6c9",
    "cor_texto_auto": "#bcd7ff",
    "atalho_liga_desliga": "F8",
    "atalho_esconder": "F9",
    "atalho_salvar_tela": "F10",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        save_config(cfg)
    except Exception:
        pass
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default


def newer(path, than):
    """True se `path` existe e foi gravado depois de `than`."""
    if not FROZEN:
        return False  # rodando pelo codigo-fonte: vale sempre o arquivo do projeto (o que se esta editando)
    try:
        return os.path.getmtime(path) > os.path.getmtime(than)
    except OSError:
        return False


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
