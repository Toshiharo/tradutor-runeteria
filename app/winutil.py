"""Funcoes do Windows: achar a janela do Hytale, estilos do overlay e atalhos."""
import ctypes
import os
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOPMOST = 0x00000008
WDA_EXCLUDEFROMCAPTURE = 0x11
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

GA_ROOT = 2

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _sig(func, restype, *argtypes):
    """Declara os tipos: sem isso o ctypes trata handles como int de 32 bits no Windows 64."""
    func.restype = restype
    func.argtypes = list(argtypes)


_sig(user32.GetWindowLongW, ctypes.c_long, wintypes.HWND, ctypes.c_int)
_sig(user32.SetWindowLongW, ctypes.c_long, wintypes.HWND, ctypes.c_int, ctypes.c_long)
_sig(user32.GetForegroundWindow, wintypes.HWND)
_sig(user32.GetAncestor, wintypes.HWND, wintypes.HWND, wintypes.UINT)
_sig(user32.IsWindowVisible, wintypes.BOOL, wintypes.HWND)
_sig(user32.IsIconic, wintypes.BOOL, wintypes.HWND)
_sig(user32.GetWindowTextLengthW, ctypes.c_int, wintypes.HWND)
_sig(user32.GetWindowTextW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_sig(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_sig(user32.EnumWindows, wintypes.BOOL, EnumWindowsProc, wintypes.LPARAM)
_sig(user32.GetClientRect, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.RECT))
_sig(user32.ClientToScreen, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.POINT))
_sig(user32.SetWindowDisplayAffinity, wintypes.BOOL, wintypes.HWND, wintypes.DWORD)
_sig(user32.RegisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
_sig(user32.GetMessageW, ctypes.c_int, ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
_sig(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_sig(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
_sig(kernel32.QueryFullProcessImageNameW, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
     ctypes.POINTER(wintypes.DWORD))


_sig(kernel32.CreateMutexW, wintypes.HANDLE, wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_mutex = None


def single_instance(name):
    """False se ja existe outra copia do programa aberta (dois overlays brigariam pelos atalhos)."""
    global _mutex
    _mutex = kernel32.CreateMutexW(None, False, name)  # fica aberto ate o programa fechar
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def dark_titlebar(hwnd):
    """Barra de titulo escura (Windows 10 2004+ / 11), para combinar com a janela."""
    try:
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


# ---------- abrir junto com o Windows ----------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "TradutorRuneteria"


def autostart_command():
    """Comando gravado no registro; None quando rodando pelo codigo-fonte (so faz sentido no .exe)."""
    import sys
    if not getattr(sys, "frozen", False):
        return None
    return f'"{sys.executable}" --minimizado'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_NAME)[0] == autostart_command()
    except OSError:
        return False


def set_autostart(on):
    """Liga/desliga para o usuario atual (HKCU, nao precisa de administrador)."""
    import winreg
    cmd = autostart_command()
    if cmd is None:
        return False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except OSError:
                pass
    return True


def install_english_ocr(log_path=None):
    """Instala o leitor de texto em ingles do Windows. Abre o pedido de administrador (UAC) e espera
    terminar. Devolve o codigo de saida (0 = rodou ate o fim; 1223 = o usuario recusou o pedido).
    O que o Windows respondeu vai para log_path (para entender quando falha no PC de alguem)."""
    import subprocess
    inner = "Add-WindowsCapability -Online -Name 'Language.OCR~~~en-US~0.0.1.0'"
    if log_path:
        inner = f"try {{ {inner} -ErrorAction Stop *> '{log_path}' }} catch {{ `$_ *> '{log_path}'; exit 1 }}"
    outer = ("try { $p = Start-Process powershell -Verb RunAs -WindowStyle Hidden -Wait -PassThru "
             f"-ArgumentList '-NoProfile','-Command',\"{inner}\"; exit $p.ExitCode }} catch {{ exit 1223 }}")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", outer], timeout=900,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
        return r.returncode
    except Exception:
        return -1


def english_ocr_files():
    """True se os arquivos do leitor em ingles estao no Windows (pode faltar so reabrir o programa)."""
    return os.path.isdir(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "OCR", "en-us"))


def open_language_settings():
    """Abre Configuracoes > Hora e idioma > Idioma (instalar o ingles por la tambem instala o leitor)."""
    try:
        os.startfile("ms-settings:regionlanguage")
    except Exception:
        pass


def toplevel_hwnd(widget_id):
    """Janela de verdade (a que o Windows enxerga) a partir do winfo_id() de um widget tkinter."""
    return user32.GetAncestor(widget_id, GA_ROOT) or widget_id


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def _process_name(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def find_hytale_window():
    """Janela visivel cujo processo e o cliente do Hytale (ignora navegador com 'Hytale' no titulo)."""
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if "hytale" in buf.value.lower():
            proc = _process_name(hwnd)
            if "hytale" in proc:
                found.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else None


def client_rect(hwnd):
    """(x, y, largura, altura) da area do jogo na tela."""
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 50 or h < 50:
        return None
    return pt.x, pt.y, w, h


def is_foreground(hwnd, also_ok=()):
    fg = user32.GetForegroundWindow()
    return fg == hwnd or fg in also_ok


def is_minimized(hwnd):
    return bool(user32.IsIconic(hwnd))


def make_overlay(hwnd):
    """Overlay que deixa o clique passar, nao rouba foco e nao aparece em capturas (nem no OCR)."""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    return exclude_from_capture(hwnd)


class _CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hCursor", wintypes.HANDLE),
                ("ptScreenPos", wintypes.POINT)]


_sig(user32.GetCursorInfo, wintypes.BOOL, ctypes.POINTER(_CURSORINFO))


def cursor_pos():
    """(x, y) do cursor na tela, ou None se ele esta escondido (no jogo: andando pelo mundo, sem chat nem
    menu aberto)."""
    ci = _CURSORINFO()
    ci.cbSize = ctypes.sizeof(_CURSORINFO)
    if not user32.GetCursorInfo(ctypes.byref(ci)) or not ci.flags & 1:  # CURSOR_SHOWING
        return None
    return ci.ptScreenPos.x, ci.ptScreenPos.y


def exclude_from_capture(hwnd, on=True):
    """on=True: o overlay nao aparece em capturas nem gravacoes. on=False: aparece (para gravar video)."""
    try:
        return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if on else 0))
    except Exception:
        return False


class _BMI(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_sig(user32.GetDC, wintypes.HDC, wintypes.HWND)
_sig(user32.ReleaseDC, ctypes.c_int, wintypes.HWND, wintypes.HDC)
_sig(user32.PrintWindow, wintypes.BOOL, wintypes.HWND, wintypes.HDC, wintypes.UINT)
_sig(gdi32.CreateCompatibleDC, wintypes.HDC, wintypes.HDC)
_sig(gdi32.CreateCompatibleBitmap, wintypes.HBITMAP, wintypes.HDC, ctypes.c_int, ctypes.c_int)
_sig(gdi32.SelectObject, wintypes.HGDIOBJ, wintypes.HDC, wintypes.HGDIOBJ)
_sig(gdi32.DeleteObject, wintypes.BOOL, wintypes.HGDIOBJ)
_sig(gdi32.DeleteDC, wintypes.BOOL, wintypes.HDC)
_sig(gdi32.GetDIBits, ctypes.c_int, wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
     wintypes.LPVOID, ctypes.c_void_p, wintypes.UINT)


def open_capture(hwnd):
    """Captura da janela pelo Windows Graphics Capture (ver captura.py). Levanta erro se este Windows nao der."""
    from captura import WindowCapture
    return WindowCapture(hwnd)


def grab_window(hwnd, w, h):
    """So o conteudo da janela do jogo (PrintWindow), sem nada do que estiver por cima dela - nem o
    overlay. Assim o overlay pode aparecer em gravacoes (OBS, Discord) sem o OCR ler a propria traducao.
    Devolve uma imagem PIL, ou None se o Windows nao conseguir (a imagem vem preta)."""
    from PIL import Image
    hdc = user32.GetDC(hwnd)
    if not hdc:
        return None
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    try:
        old = gdi32.SelectObject(mdc, bmp)
        ok = user32.PrintWindow(hwnd, mdc, 1 | 2)  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
        gdi32.SelectObject(mdc, old)
        if not ok:
            return None
        bi = _BMI(ctypes.sizeof(_BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0) != h:
            return None
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, hdc)


VK = {f"F{i}": 0x6F + i for i in range(1, 13)}
VK.update({"PAUSE": 0x13, "INSERT": 0x2D, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22})
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


class Hotkeys(threading.Thread):
    """Atalhos globais (funcionam com o jogo em foco). callbacks: {'F8': func, ...}
    on_failed(lista) e chamado se algum atalho nao pode ser registrado (tecla invalida ou em uso)."""

    def __init__(self, callbacks, on_failed=None):
        super().__init__(daemon=True)
        self.callbacks = callbacks
        self.on_failed = on_failed
        self.failed = []

    def run(self):
        ids = {}
        for i, (key, fn) in enumerate(self.callbacks.items(), start=1):
            vk = VK.get(str(key).upper())
            if vk and user32.RegisterHotKey(None, i, MOD_NOREPEAT, vk):
                ids[i] = fn
            else:
                self.failed.append(key)
        if self.failed and self.on_failed:
            self.on_failed(list(self.failed))
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in ids:
                try:
                    ids[msg.wParam]()
                except Exception:
                    pass
