"""Baixa (uma unica vez) o modelo de traducao offline ingles->portugues do Argos Translate."""
import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "modelos", "en_pt")
INDEX = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
FALLBACK = "https://argos-net.com/v1/translate-en_pt-1_9.argosmodel"


def has_model():
    for _, _, files in os.walk(DEST):
        if "model.bin" in files:
            return True
    return False


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "RuneteriaTradutor/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    if has_model():
        print("Modelo ja baixado.")
        return
    links = []
    try:
        for p in json.loads(get(INDEX)):
            if p.get("from_code") == "en" and p.get("to_code") == "pt":
                links += p.get("links", [])
    except Exception as e:
        print("Nao consegui ler o indice, usando link padrao:", e)
    links.append(FALLBACK)
    for url in links:
        try:
            print("Baixando modelo de traducao:", url)
            data = get(url)
            if os.path.isdir(DEST):
                shutil.rmtree(DEST)
            os.makedirs(DEST, exist_ok=True)
            zipfile.ZipFile(io.BytesIO(data)).extractall(DEST)
            if has_model():
                print("Modelo instalado em", DEST)
                return
        except Exception as e:
            print("Falhou:", e)
    print("ERRO: nao foi possivel baixar o modelo. O programa vai funcionar so com a biblioteca.")
    sys.exit(1)


if __name__ == "__main__":
    main()
