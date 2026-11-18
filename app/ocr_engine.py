"""OCR usando o leitor de texto que ja vem no Windows 10/11 (Windows.Media.Ocr). Offline."""
import asyncio

from PIL import Image


INSTALL_CMD = 'Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"'


class OcrUnavailable(Exception):
    pass


TARGET_TEXT_PX = 15.5  # altura do texto que o OCR do Windows le melhor (depois de ampliar)


def auto_scale(text_h, width, height):
    """Escala do OCR para a altura do texto desta tela: texto de 6 px (1280x720) e ampliado ~2,5x;
    em 4K o texto ja e grande e a imagem e lida quase sem ampliar (3x mais rapido)."""
    low = 0.75 if width * height > 4_000_000 else 1.0
    return max(low, min(3.0, TARGET_TEXT_PX / max(text_h, 1.0)))


def initial_scale(height):
    """Antes da primeira leitura: estimativa pela altura da janela (em 1080p o texto tem ~9 px)."""
    return auto_scale(9.0 * height / 1009.0, 1, 1)


class WindowsOcr:
    def __init__(self, lang="en-US"):
        try:
            from winrt.windows.globalization import Language
            from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
            from winrt.windows.media.ocr import OcrEngine
            from winrt.windows.storage.streams import DataWriter
        except Exception as e:
            raise OcrUnavailable(f"Pacotes winrt ausentes: {e}")
        self._SoftwareBitmap = SoftwareBitmap
        self._fmt = BitmapPixelFormat.RGBA8
        self._DataWriter = DataWriter
        engine = None
        self.warning = None
        for tag in (lang, "en-GB", "en"):
            try:
                engine = OcrEngine.try_create_from_language(Language(tag))
            except Exception:
                engine = None
            if engine is not None:
                break
        if engine is None:
            # sem OCR em ingles: usa o idioma do Windows (pt-BR le o mesmo alfabeto, so erra um pouco mais)
            try:
                engine = OcrEngine.try_create_from_user_profile_languages()
            except Exception:
                engine = None
            if engine is not None:
                self.warning = ("OCR em inglês não instalado; usando o do Windows (menos preciso). "
                                "Para instalar, PowerShell como administrador: " + INSTALL_CMD)
        if engine is None:
            raise OcrUnavailable("O Windows não tem nenhum OCR instalado. PowerShell como administrador: " + INSTALL_CMD)
        self.engine = engine
        try:
            self.language = engine.recognizer_language.language_tag
        except Exception:
            self.language = "?"
        try:
            self.max_dim = int(OcrEngine.max_image_dimension)
        except Exception:
            self.max_dim = 10000
        self.loop = asyncio.new_event_loop()

    def recognize(self, img: Image.Image, scale=1.0):
        """Devolve lista de linhas: {'text', 'x','y','w','h'} em pixels da imagem ORIGINAL."""
        scale = min(scale, self.max_dim / max(img.width, img.height, 1))  # o Windows recusa imagem grande demais
        if scale != 1.0:
            # LANCZOS le melhor texto pequeno ampliado que BICUBIC (testado em 1280x720: 60% -> 68-75%)
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        img = img.convert("RGBA")
        w, h = img.size
        writer = self._DataWriter()
        writer.write_bytes(img.tobytes())
        bmp = self._SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), self._fmt, w, h)
        result = self.loop.run_until_complete(self.engine.recognize_async(bmp))
        lines = []
        for line in result.lines:
            xs, ys, xe, ye, words = [], [], [], [], []
            for word in line.words:
                r = word.bounding_rect
                xs.append(r.x); ys.append(r.y); xe.append(r.x + r.width); ye.append(r.y + r.height)
                words.append({"text": word.text, "x": r.x / scale, "y": r.y / scale,
                              "w": r.width / scale, "h": r.height / scale})
            if not xs:
                continue
            lines.append({
                "text": line.text,
                "x": min(xs) / scale, "y": min(ys) / scale,
                "w": (max(xe) - min(xs)) / scale, "h": (max(ye) - min(ys)) / scale,
                "words": words,  # usado por pipeline.tidy_lines para separar colunas e tirar icones
            })
        return lines
