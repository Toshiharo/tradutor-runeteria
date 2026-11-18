"""Gera o icone e as imagens de marca do app a partir dos logos oficiais do Runeteria.

Uso (so quando os logos mudarem; os arquivos gerados ficam no repositorio):
    python tools\\gerar_icone.py "C:\\caminho\\Runeteria-Assets\\Logo"

Le:      Runteria_logo_R_discord.png (o "R" dourado) e "runeteria_logo_flt copy.png" (logo completo)
Escreve: app/assets/logo_r.png, app/assets/logo_runeteria.png, app/icone.ico, tools/instalador_logo.bmp
"""
import os
import sys

from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
ASSETS = os.path.join(APP, "assets")
PANEL, GOLD = "#141928", "#e0b356"   # base-bg-900 e primary-300 do design system


def trimmed(path):
    im = Image.open(path).convert("RGBA")
    return im.crop(im.getbbox())


def fit(im, w, h):
    im = im.copy()
    im.thumbnail((w, h), Image.LANCZOS)
    return im


def icon(mark, size):
    """O "R" dourado sobre um quadrado azul-marinho de cantos arredondados com filete dourado."""
    s = size * 4  # desenha grande e reduz, para as bordas ficarem suaves
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = s * 0.2
    if size >= 32:
        b = s * 0.035
        d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=GOLD)
        d.rounded_rectangle((b, b, s - 1 - b, s - 1 - b), r - b, fill=PANEL)
        m = fit(mark, int(s * 0.84), int(s * 0.84))
    else:  # em 16/24 px o filete vira borrao: so o fundo e o R maior
        d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=PANEL)
        m = fit(mark, int(s * 0.88), int(s * 0.88))
    img.alpha_composite(m, ((s - m.width) // 2, (s - m.height) // 2))
    return img.resize((size, size), Image.LANCZOS)


def main():
    if len(sys.argv) > 1:
        src = sys.argv[1]
        os.makedirs(ASSETS, exist_ok=True)
        fit(trimmed(os.path.join(src, "Runteria_logo_R_discord.png")), 512, 512).save(
            os.path.join(ASSETS, "logo_r.png"), optimize=True)
        fit(trimmed(os.path.join(src, "runeteria_logo_flt copy.png")), 900, 450).save(
            os.path.join(ASSETS, "logo_runeteria.png"), optimize=True)
    mark = Image.open(os.path.join(ASSETS, "logo_r.png")).convert("RGBA")
    sizes = [256, 128, 64, 48, 32, 24, 16]
    imgs = [icon(mark, n) for n in sizes]
    imgs[0].save(os.path.join(APP, "icone.ico"), format="ICO", sizes=[(n, n) for n in sizes],
                 append_images=imgs[1:])
    imgs[0].save(os.path.join(HERE, "icone_previa.png"))
    # imagem pequena do canto do instalador (Inno Setup aceita BMP; ele reduz conforme a tela)
    bmp = Image.new("RGB", (165, 165), PANEL)
    m = fit(mark, 125, 125)
    bmp.paste(m, ((165 - m.width) // 2, (165 - m.height) // 2), m)
    bmp.save(os.path.join(HERE, "instalador_logo.bmp"))
    print("gerados: app/icone.ico, tools/instalador_logo.bmp, app/assets/")


if __name__ == "__main__":
    main()
