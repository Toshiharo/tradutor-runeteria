"""Captura da janela do jogo pelo Windows Graphics Capture (o metodo do proprio Windows 10/11 para gravar janela).

Por que: o PrintWindow redesenha a janela inteira a cada pedido (~20 ms em 1080p, ~45 ms em telas maiores), mesmo com
a tela parada. Aqui o Windows entrega o quadro que a placa de video ja desenhou: copiar custa a metade, e com a tela
parada nao chega quadro nenhum (custo zero). Como o PrintWindow, pega so a janela do jogo - o overlay e o cursor ficam
de fora - e funciona com a janela coberta por outra.

Nao precisa de nada instalado no computador do jogador: sao funcoes do Windows, chamadas pelos pacotes `winrt` que ja
vao dentro do programa. Se o Windows for antigo demais, ou nao deixar tirar a borda amarela de gravacao, `WindowCapture`
levanta erro e o tradutor continua com o PrintWindow (e, por ultimo, a captura da tela).
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
DWMWA_EXTENDED_FRAME_BOUNDS = 9


def _client_offset(hwnd):
    """(dx, dy) do canto da area do jogo dentro do quadro capturado (o quadro inclui titulo e bordas da janela)."""
    frame = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(frame),
                                    ctypes.sizeof(frame)) != 0:
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(frame))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt))
    return pt.x - frame.left, pt.y - frame.top


class WindowCapture:
    def __init__(self, hwnd):
        from winrt.windows.graphics.capture import Direct3D11CaptureFramePool, GraphicsCaptureSession
        from winrt.windows.graphics.capture.interop import create_for_window
        from winrt.windows.graphics.directx import DirectXPixelFormat
        from winrt.windows.graphics.directx.direct3d11.interop import create_direct3d11_device
        if not GraphicsCaptureSession.is_supported():
            raise OSError("Windows Graphics Capture nao suportado")
        self.hwnd = hwnd
        self._fmt = DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED
        self._item = create_for_window(hwnd)
        self._dev = create_direct3d11_device()
        self._size = self._item.size
        self._pool = Direct3D11CaptureFramePool.create_free_threaded(self._dev, self._fmt, 1, self._size)
        self._sess = self._pool.create_capture_session(self._item)
        try:
            # sem isto o Windows desenha uma borda amarela em volta do jogo e o cursor entra na leitura.
            # Windows que nao deixa desligar (10 antigo): melhor o metodo antigo que a borda na tela do jogador
            self._sess.is_border_required = False
            self._sess.is_cursor_capture_enabled = False
        except Exception:
            self.close()
            raise
        self._sess.start_capture()
        self._loop = None
        self._off, self._off_key = (0, 0), None  # onde a area do jogo fica dentro do quadro (ver _find_offset)

    def grab(self, w, h):
        """Imagem PIL (RGB) da area do jogo, ou None se nao chegou quadro novo (tela parada, ou a janela acabou
        de mudar de tamanho e o proximo quadro ja vem certo)."""
        frame = self._pool.try_get_next_frame()
        if frame is None:
            return None
        try:
            size = frame.content_size
            if (size.width, size.height) != (self._size.width, self._size.height):
                self._size = size
                self._pool.recreate(self._dev, self._fmt, 1, size)
                return None
            import asyncio
            from PIL import Image
            from winrt.windows.graphics.imaging import SoftwareBitmap
            from winrt.windows.storage.streams import Buffer
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
            sb = self._loop.run_until_complete(SoftwareBitmap.create_copy_from_surface_async(frame.surface))
            try:
                fw, fh = sb.pixel_width, sb.pixel_height
                buf = Buffer(fw * fh * 4)
                sb.copy_to_buffer(buf)
                img = Image.frombuffer("RGB", (fw, fh), bytes(buf), "raw", "BGRX", 0, 1)
            finally:
                sb.close()
        finally:
            frame.close()
        if (fw, fh) == (w, h):
            return img  # tela cheia sem borda: o quadro ja e a area do jogo
        if fw < w or fh < h:
            return None  # a janela esta mudando de tamanho: o quadro ainda e do tamanho antigo
        key = (fw, fh, w, h, user32.IsZoomed(wintypes.HWND(self.hwnd)))
        if self._off_key != key:
            self._off, self._off_key = self._find_offset(img, w, h), key
        dx, dy = self._off
        if dx < 0 or dy < 0 or dx + w > fw or dy + h > fh:
            return None
        return img.crop((dx, dy, dx + w, dy + h))

    def _find_offset(self, frame, w, h):
        """Onde a area do jogo fica dentro do quadro. A conta pela borda da janela (`_client_offset`) erra com a
        janela maximizada: o quadro vem com as bordas escondidas, a conta nao, e a traducao saia ~8 px abaixo do
        texto (defeito da 1.1.4). Aqui o lugar e MEDIDO: compara o quadro com o PrintWindow, que devolve
        exatamente a area do jogo, e fica com a posicao em que os dois batem. Roda so quando a janela muda de
        tamanho ou de modo. Sem PrintWindow que preste, vale a conta."""
        guess = _client_offset(self.hwnd)
        try:
            from PIL import ImageChops, ImageStat
            import winutil
            ref = winutil.grab_window(self.hwnd, w, h)
            if ref is None:
                return guess
            small = ref.convert("L").reduce(4)
            lo, hi = small.getextrema()
            if hi - lo < 12:
                return guess  # veio preta
            gray = frame.convert("L")
            best = None
            for dy in range(0, min(80, frame.height - h) + 1):
                for dx in range(0, min(40, frame.width - w) + 1):
                    d = ImageStat.Stat(ImageChops.difference(gray.crop((dx, dy, dx + w, dy + h)).reduce(4), small)).mean[0]
                    if best is None or d < best[0]:
                        best = (d, dx, dy)
            # so vale se bateu de verdade (o jogo mexe um pouco entre uma captura e outra)
            return (best[1], best[2]) if best and best[0] < 12 else guess
        except Exception:
            return guess

    def close(self):
        for name in ("_sess", "_pool"):
            obj = getattr(self, name, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
            setattr(self, name, None)
