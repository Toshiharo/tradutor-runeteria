"""Gera app/icone.ico: um "R" em Cormorant dourado sobre azul-marinho, com filete dourado.

O design system nao tem logotipo (o nome e sempre escrito em tipo), entao o icone e tipografico.
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
PANEL, CARD, GOLD, GOLD_HI = "#141928", "#1a2031", "#e0b356", "#e9c97a"


def render(size):
    s = size * 4  # desenha grande e reduz, para as bordas ficarem suaves
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = s * 0.19
    d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=GOLD)
    b = max(4, s * 0.045)
    d.rounded_rectangle((b, b, s - 1 - b, s - 1 - b), r - b, fill=PANEL)
    font = ImageFont.truetype(os.path.join(APP, "fonts", "Cormorant.ttf"), int(s * 0.86))
    try:
        font.set_variation_by_axes([700])  # Bold
    except Exception:
        pass
    box = d.textbbox((0, 0), "R", font=font)
    d.text(((s - (box[2] - box[0])) / 2 - box[0], (s - (box[3] - box[1])) / 2 - box[1] - s * 0.01), "R",
           font=font, fill=GOLD_HI)
    return img.resize((size, size), Image.LANCZOS)


def main():
    sizes = [256, 128, 64, 48, 32, 24, 16]
    imgs = [render(n) for n in sizes]
    out = os.path.join(APP, "icone.ico")
    imgs[0].save(out, format="ICO", sizes=[(n, n) for n in sizes], append_images=imgs[1:])
    imgs[0].save(os.path.join(HERE, "icone_previa.png"))
    print("gerado", out)


if __name__ == "__main__":
    main()
