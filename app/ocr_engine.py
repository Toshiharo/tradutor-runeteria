"""OCR usando o leitor de texto que ja vem no Windows 10/11 (Windows.Media.Ocr). Offline."""
import asyncio

from PIL import Image


INSTALL_CMD = 'Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"'


class OcrUnavailable(Exception):
    pass


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
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.BICUBIC)
        img = img.convert("RGBA")
        w, h = img.size
        writer = self._DataWriter()
        writer.write_bytes(img.tobytes())
        bmp = self._SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), self._fmt, w, h)
        result = self.loop.run_until_complete(self.engine.recognize_async(bmp))
        lines = []
        for line in result.lines:
            xs, ys, xe, ye = [], [], [], []
            for word in line.words:
                r = word.bounding_rect
                xs.append(r.x); ys.append(r.y); xe.append(r.x + r.width); ye.append(r.y + r.height)
            if not xs:
                continue
            lines.append({
                "text": line.text,
                "x": min(xs) / scale, "y": min(ys) / scale,
                "w": (max(xe) - min(xs)) / scale, "h": (max(ye) - min(ys)) / scale,
            })
        return lines
