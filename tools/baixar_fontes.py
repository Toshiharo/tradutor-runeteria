"""Baixa as fontes do Runeteria Design System (Cormorant, Lexend, Inter - licenca OFL) para app/fonts.

So precisa rodar se a pasta app/fonts for apagada; os arquivos ficam no repositorio.
"""
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(os.path.dirname(HERE), "app", "fonts")
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FILES = {
    "Inter.ttf": "inter/Inter%5Bopsz%2Cwght%5D.ttf",
    "Lexend.ttf": "lexend/Lexend%5Bwght%5D.ttf",
    "Cormorant.ttf": "cormorant/Cormorant%5Bwght%5D.ttf",
    "OFL-Inter.txt": "inter/OFL.txt",
    "OFL-Lexend.txt": "lexend/OFL.txt",
    "OFL-Cormorant.txt": "cormorant/OFL.txt",
}


def main():
    os.makedirs(DEST, exist_ok=True)
    for name, path in FILES.items():
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "font-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(os.path.join(DEST, name), "wb") as f:
            f.write(data)
        print(name, len(data) // 1024, "KB")


if __name__ == "__main__":
    main()
