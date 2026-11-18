"""Caminhos e configuracoes do Tradutor Runeteria."""
import json
import os
import sys

APP_NAME = "Tradutor Runeteria"

# Pasta onde ficam os arquivos que vem junto com o programa (biblioteca, modelo)
if getattr(sys, "frozen", False):
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BUNDLE_DIR, "data")
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
USER_OVERRIDES = os.path.join(USER_DIR, "minhas_traducoes.json")
USER_GLOSSARY = os.path.join(USER_DIR, "glossario.json")
MEMORY_FILE = os.path.join(USER_DIR, "memoria_automatica.json")
UPDATER_STATE = os.path.join(USER_DIR, "atualizador_estado.json")
NEW_TEXTS_LOG = os.path.join(USER_DIR, "textos_novos.txt")
SCREEN_DUMP = os.path.join(USER_DIR, "ultima_tela.txt")
CONFIG_FILE = os.path.join(USER_DIR, "config.json")
ERROR_LOG = os.path.join(USER_DIR, "erros.log")

DEFAULTS = {
    "servidor": "runeteria.com",
    "intervalo_segundos": 0.8,
    "escala_ocr": 1.6,
    "similaridade_minima": 86,
    "traduzir_desconhecidos": True,
    "tamanho_fonte_min": 9,
    "fonte": "Segoe UI",
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


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
