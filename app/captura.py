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
        dx, dy = _client_offset(self.hwnd)
        if dx < 0 or dy < 0 or dx + w > fw or dy + h > fh:
            return None  # a janela esta mudando de tamanho: o quadro ainda e do tamanho antigo
        return img if (dx, dy, fw, fh) == (0, 0, w, h) else img.crop((dx, dy, dx + w, dy + h))

    def close(self):
        for name in ("_sess", "_pool"):
            obj = getattr(self, name, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
            setattr(self, name, None)
