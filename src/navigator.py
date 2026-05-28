import ctypes
import ctypes.wintypes
import logging
import time
import win32api
import win32con

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_longlong
if ctypes.sizeof(ctypes.c_void_p) == 4: LRESULT = ctypes.c_long

# --- ESTRUCTURAS DE BAJO NIVEL PARA EL TECLADO ---
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))

# --- ESTRUCTURAS DE BAJO NIVEL PARA EL MOUSE (SENDINPUT) ---
PUL = ctypes.POINTER(ctypes.c_ulong)
class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]
class Input_I(ctypes.Union):
    _fields_ = [("mi", MouseInput)]
class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]

# Constantes de hardware para Mouse
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

SPECIAL_VK = {
    "enter": 0x0D, "esc": 0x1B, "space": 0x20, "tab": 0x09, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "page up": 0x21, "page down": 0x22,
    "insert": 0x2D, "delete": 0x2E, "capslock": 0x14,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "apps": 0x5D, "menu": 0x5D, "shift": 0x10, "ctrl": 0x11, "alt": 0x12
}

# Constantes de máscara para modificadores
MOD_SHIFT = 1 << 0
MOD_CTRL  = 1 << 1
MOD_ALT   = 1 << 2

def string_to_hotkey(s, default_s=""):
    s = s.lower().strip()
    if not s: s = default_s.lower()
    parts = [p.strip() for p in s.split('+')]
    vk = SPECIAL_VK.get(parts[-1], user32.VkKeyScanW(ord(parts[-1][0])) & 0xFF if len(parts[-1])==1 else 0)
    mask = 0
    if "shift" in parts: mask |= MOD_SHIFT
    if "ctrl" in parts or "control" in parts: mask |= MOD_CTRL
    if "alt" in parts or "menu" in parts: mask |= MOD_ALT
    return vk, mask

class ElementNavigator:
    def __init__(self, tts, config, offset_x=0, offset_y=0, rescan_callback=None):
        self.tts = tts; self.config = config; self.offset_x = offset_x; self.offset_y = offset_y
        self.rescan_callback = rescan_callback
        self.elements = []; self.index = -1; self._hook = None; self._running = False
        self._hotkey_actions = {}

    def _precompute_hotkeys(self):
        # Mapa de acciones basado en configuración
        actions = {
            "key_double": ("shift+enter", self._on_double),
            "key_right":  ("apps", self._on_right),
            "key_click":  ("enter", self._on_left),
            "key_next":   ("down", self._on_next),
            "key_prev":   ("up", self._on_prev),
            "key_exit":   ("esc", self._on_exit),
            "key_copy":   ("ctrl+c", self._on_copy),
            "key_first":  ("home", self._on_first),
            "key_last":   ("end", self._on_last),
            "key_skip_next": ("right", lambda: self._on_skip(5)),
            "key_skip_prev": ("left", lambda: self._on_skip(-5)),
            "key_repeat": ("space", self._on_repeat)
        }
        
        self._hotkey_actions = {}
        for cid, (default, func) in actions.items():
            vk, mask = string_to_hotkey(self.config.get(cid, ""), default)
            if vk != 0:
                self._hotkey_actions[vk] = self._hotkey_actions.get(vk, [])
                self._hotkey_actions[vk].append((mask, func))

    def navigate(self, elements):
        if not elements: return
        self._precompute_hotkeys()
        self.elements = elements; self.index = -1; self._running = True
        self._callback = HOOKPROC(self._hook_callback)
        self._hook = user32.SetWindowsHookExW(13, self._callback, kernel32.GetModuleHandleW(None), 0)
        if not self._hook: self._hook = user32.SetWindowsHookExW(13, self._callback, None, 0)
        
        # Auto-anunciar el primer elemento para confirmar que la navegación inició
        self._on_next()

        msg = ctypes.wintypes.MSG()
        while self._running:
            # PeekMessageW permite revisar la cola sin bloquearse infinitamente
            # y sin depender exclusivamente de GetMessageW que puede tragarse WM_QUITs ajenos
            if user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1): # 1 = PM_REMOVE
                if msg.message == 0x0012: # WM_QUIT
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                # Pequeña espera para no quemar CPU en el bucle de mensajes
                time.sleep(0.01)

    def _stop(self):
        self._running = False
        if self._hook: 
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _get_current_mask(self):
        mask = 0
        if (win32api.GetKeyState(win32con.VK_SHIFT) & 0x8000): mask |= MOD_SHIFT
        if (win32api.GetKeyState(win32con.VK_CONTROL) & 0x8000): mask |= MOD_CTRL
        if (win32api.GetKeyState(win32con.VK_MENU) & 0x8000): mask |= MOD_ALT
        return mask

    def _hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam == win32con.WM_KEYDOWN:
            if self._handle_key(lParam.contents.vkCode): return 1
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _handle_key(self, vk):
        if vk not in self._hotkey_actions:
            return False
            
        current_mask = self._get_current_mask()
        for target_mask, func in self._hotkey_actions[vk]:
            if current_mask == target_mask:
                return func()
            
        return False

    def _on_next(self): self.index = (self.index+1)%len(self.elements); self._announce(); return True
    def _on_prev(self): self.index = (self.index-1)%len(self.elements); self._announce(); return True
    def _on_first(self): self.index = 0; self._announce(); return True
    def _on_last(self): self.index = len(self.elements) - 1; self._announce(); return True
    
    def _on_repeat(self):
        current_time = time.time()
        if hasattr(self, '_last_repeat_time') and (current_time - self._last_repeat_time) < 0.5:
            self._spell_current()
            self._last_repeat_time = 0
        else:
            self._last_repeat_time = current_time
            self._announce()
        return True

    def _spell_current(self):
        if hasattr(self, '_last_announced_text'):
            text = self._last_announced_text
            spelled = "; ".join([c if not c.isspace() else "espacio" for c in text])
            self.tts.speak(spelled, interrupt=True)

    def _on_skip(self, amount):
        if not self.elements: return
        self.index = (self.index + amount) % len(self.elements)
        self._announce(); return True
    def _on_left(self): self._click("left"); return True
    def _on_double(self): self._click("double"); return True
    def _on_right(self): self._click("right"); return True
    def _on_exit(self): self.tts.speak("Cerrado."); self._stop(); return True
    
    def _on_copy(self):
        if hasattr(self, '_last_announced_text'):
            import wx
            text = self._last_announced_text
            def do_copy():
                if wx.TheClipboard.Open():
                    wx.TheClipboard.SetData(wx.TextDataObject(text))
                    wx.TheClipboard.Flush()
                    wx.TheClipboard.Close()
                    self.tts.speak("Copiado.", interrupt=True)
                else:
                    self.tts.speak("Error al abrir portapapeles.", interrupt=True)
            wx.CallAfter(do_copy)
        return True

    def _announce(self):
        if 0 <= self.index < len(self.elements):
            el = self.elements[self.index]
            text = el.text
            if self.config.get("translate_enabled"):
                from translator import translator_instance
                from_code = self.config.get("translate_from", "en")
                to_code = self.config.get("translate_to", "es")
                text = translator_instance.translate(
                    text, from_code, to_code, 
                    translate_type=self.config.get("translate_type", "local"),
                    service=self.config.get("translate_service", "google"),
                    swap=self.config.get("translate_swap", False)
                )
            
            self._last_announced_text = text
            self.tts.speak(f"{text} {self.index+1} de {len(self.elements)}", interrupt=True)

    def _click(self, mode):
        if 0 <= self.index < len(self.elements):
            el = self.elements[self.index]
            
            # 1. Movemos el mouse físicamente a la coordenada
            abs_x = int(self.offset_x + el.center_x)
            abs_y = int(self.offset_y + el.center_y)
            user32.SetCursorPos(abs_x, abs_y)
            
            time.sleep(0.05) # Pausa micro para que el OS registre el movimiento
            
            # 2. Función interna para inyectar click de hardware
            def send_click(down_flag, up_flag):
                extra = ctypes.pointer(ctypes.c_ulong(0))
                
                # Presionar
                ii_down = Input_I()
                ii_down.mi = MouseInput(0, 0, 0, down_flag, 0, extra)
                cmd_down = Input(INPUT_MOUSE, ii_down)
                user32.SendInput(1, ctypes.byref(cmd_down), ctypes.sizeof(Input))
                
                time.sleep(0.02) # El humano más rápido del mundo tarda 20ms en soltar un click
                
                # Soltar
                ii_up = Input_I()
                ii_up.mi = MouseInput(0, 0, 0, up_flag, 0, extra)
                cmd_up = Input(INPUT_MOUSE, ii_up)
                user32.SendInput(1, ctypes.byref(cmd_up), ctypes.sizeof(Input))

            # 3. Ejecutar según el modo
            m_text = "izquierdo"
            if mode == "left":
                send_click(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
            elif mode == "double":
                m_text = "doble"
                send_click(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
                time.sleep(0.05)
                send_click(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
            elif mode == "right":
                m_text = "derecho"
                send_click(MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)

            self.tts.speak(f"Click {m_text}")
            self._stop()
            
            # Auto-rescan logic
            if self.config.get("auto_rescan_after_click", False) and self.rescan_callback:
                delay = self.config.get("auto_rescan_delay", 5) / 10.0
                def do_rescan():
                    time.sleep(delay)
                    self.rescan_callback()
                import threading
                threading.Thread(target=do_rescan, daemon=True).start()