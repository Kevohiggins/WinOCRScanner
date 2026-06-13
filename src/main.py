"""
# WinOCR Scanner (Hybrid Version)
"""

import ctypes
import logging
import os
import sys
import threading
import time
import wx
import win32gui
import win32con
import win32api
import win32process
from difflib import SequenceMatcher

from config import load_config, save_config, CONFIG_FILE, get_effective_config, VERSION, get_base_path
from tts_engine import TTSEngine
from ocr_engine import OCREngine
from screen_capture import capture_screen, capture_active_window
from navigator import ElementNavigator
from shadow_manager import ShadowManager
from translator import translator_instance
import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

MOD_MAP = {"ctrl": win32con.MOD_CONTROL, "alt": win32con.MOD_ALT, "shift": win32con.MOD_SHIFT, "win": win32con.MOD_WIN}
VK_MAP = {
    "enter": 0x0D, "esc": 0x1B, "space": 0x20, "tab": 0x09, "backspace": 0x08, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B, "apps": 0x5D, "menu": 0x5D
}

def parse_hotkey(hotkey_str):
    if not hotkey_str or hotkey_str == "Sin asignar": return 0, 0
    parts = [p.strip().lower() for p in hotkey_str.split('+')]
    mods, vk = 0, 0
    for p in parts:
        if p in MOD_MAP:
            mods |= MOD_MAP[p]
        elif p in VK_MAP:
            vk = VK_MAP[p]
        elif len(p) == 1:
            res = ctypes.windll.user32.VkKeyScanW(ord(p))
            if res != -1: vk = res & 0xFF
    return mods, vk

import wx.adv

class TrayIcon(wx.adv.TaskBarIcon):
    def __init__(self, scanner):
        super().__init__()
        self.scanner = scanner
        icon = wx.ArtProvider.GetIcon(wx.ART_INFORMATION, wx.ART_OTHER, (16, 16))
        self.SetIcon(icon, f"WinOCR Scanner v{VERSION}")
        
        self.Bind(wx.adv.EVT_TASKBAR_RIGHT_DOWN, self.on_click)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DOWN, self.on_click)

    def CreatePopupMenu(self):
        menu = wx.Menu()
        help_item = menu.Append(wx.ID_ANY, "Ayuda")
        transcriptor_item = menu.Append(wx.ID_ANY, "Transcribir/Traducir Documento...")
        config_item = menu.Append(wx.ID_ANY, "Configuración")
        update_item = menu.Append(wx.ID_ANY, "Buscar Actualizaciones")
        exit_item = menu.Append(wx.ID_ANY, "Salir")
        
        self.Bind(wx.EVT_MENU, self.on_help, help_item)
        self.Bind(wx.EVT_MENU, self.on_pdf_transcriptor, transcriptor_item)
        self.Bind(wx.EVT_MENU, self.on_config, config_item)
        self.Bind(wx.EVT_MENU, self.on_update, update_item)
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        return menu

    def on_click(self, event):
        self.PopupMenu(self.CreatePopupMenu())

    def on_help(self, event):
        self.scanner._on_open_manual()

    def on_pdf_transcriptor(self, event):
        self.scanner._on_open_pdf_transcriptor()

    def on_config(self, event):
        self.scanner._on_open_config()

    def on_update(self, event):
        from updater import check_updates_async
        check_updates_async(None)

    def on_exit(self, event):
        self.scanner._on_quit_hotkey()

class HotkeyFrame(wx.Frame):
    def __init__(self, callback_map):
        super().__init__(None, style=wx.NO_BORDER)
        self.callback_map = callback_map
        self.Bind(wx.EVT_HOTKEY, self.on_hotkey)

    def register(self, hk_id, hotkey_str):
        mods, vk = parse_hotkey(hotkey_str)
        self.UnregisterHotKey(hk_id)
        if vk == 0: return False
        return self.RegisterHotKey(hk_id, mods, vk)

    def unregister_all(self):
        for hk_id in list(self.callback_map.keys()): self.UnregisterHotKey(hk_id)

    def on_hotkey(self, event):
        hk_id = event.GetId()
        if hk_id in self.callback_map: self.callback_map[hk_id]()

class WinOCRScanner:
    def __init__(self):
        self.full_config = load_config()
        self.config = get_effective_config(self.full_config)
        self.tts = TTSEngine()
        self.ocr = OCREngine(self.config)
        self._scan_lock = threading.Lock()
        self.is_dynamic_running = False
        self.shadow = ShadowManager(CONFIG_FILE)
        self.app = wx.App(False)
        self.tray = TrayIcon(self)
        self.hotkey_frame = None
        self._last_profile = "Global"
        self._last_elements = []
        self.active_navigator = None
        self._last_hwnd = None
        self._last_app_name = "Global"
        self._last_processed_app = None

    def start(self):
        self.tts.play_startup()
        self.tts.speak(f"Iniciando WinOCR Scanner versión {VERSION}.")
        
        # Buscar actualizaciones automáticamente si está habilitado
        if self.config.get("auto_check_updates", True):
            from updater import check_updates_async
            wx.CallLater(5000, check_updates_async, None, True)
            
        try:
            self.ocr.initialize()
            
            translator_instance.set_on_ready_callback(lambda: self.tts.speak("Motor de traducción listo.") if self.config.get("translate_enabled") else None)
            
            if self.config.get("translate_type", "disabled") == "local" and self.config.get("translate_enabled"):
                self.tts.speak("Iniciando motor de traducción.")
                translator_instance.ensure_initialized()
        except Exception as e:
            logger.error(f"Error inicializando OCR: {e}")
            self.tts.speak("Error al cargar el motor de lectura.")
        
        hk_map = { 
            101: self._on_scan_screen, 102: self._on_scan_window, 103: self._on_open_config, 
            104: self._on_quit_hotkey, 105: self._toggle_dynamic_scan, 106: self._on_learn_shadow, 
            107: self._on_clear_shadow, 108: self._on_toggle_shadow, 109: self._on_open_manual,
            110: self._on_toggle_auto_rescan, 111: self._on_open_pdf_transcriptor
        }
        self.hotkey_frame = HotkeyFrame(hk_map); self._refresh_hotkeys()
        self.tts.speak("Scanner listo.")
        self.app.MainLoop()
        if hasattr(self, 'tray'): self.tray.Destroy()
        self.tts.speak("Cerrando programa.")
        self.tts.play_shutdown(); time.sleep(1.0); sys.exit(0)

    def _get_current_app_name(self):
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "Global"
            
        if hwnd == self._last_hwnd:
            return self._last_app_name
            
        self._last_hwnd = hwnd
        try: 
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == 0:
                self._last_app_name = "Global"
                return "Global"
            
            h_process = win32api.OpenProcess(0x1000, False, pid)
            if h_process:
                try:
                    path = win32process.GetModuleFileNameEx(h_process, 0)
                    name = os.path.basename(path)
                    self._last_app_name = name
                    return name
                finally:
                    win32api.CloseHandle(h_process)
        except: 
            pass
            
        self._last_app_name = "Global"
        return "Global"

    def _update_profile(self):
        app_name = self._get_current_app_name()
        if app_name == self._last_processed_app:
            return
            
        self._last_processed_app = app_name
        self.shadow.set_app(app_name)
        new_config = get_effective_config(self.full_config, app_name)
        
        needs_reinit = (
            new_config.get("ocr_language") != self.config.get("ocr_language") or 
            str(new_config.get("image_scale")) != str(self.config.get("image_scale"))
        )
        
        if needs_reinit:
            self.config = new_config; self.ocr = OCREngine(self.config); self.ocr.initialize()
        else: 
            self.config = new_config
            self.ocr.config = new_config
        
        self._last_profile = app_name if app_name in self.full_config["profiles"] else "Global"

    def _refresh_hotkeys(self):
        c = self.full_config["global"]
        self.hotkey_frame.register(101, c.get("hotkey_screen", "ctrl+alt+s"))
        self.hotkey_frame.register(102, c.get("hotkey_window", "ctrl+alt+w"))
        self.hotkey_frame.register(103, c.get("hotkey_config", "ctrl+alt+c"))
        self.hotkey_frame.register(104, c.get("hotkey_quit", "ctrl+alt+q"))
        self.hotkey_frame.register(105, c.get("hotkey_dynamic", "ctrl+alt+d"))
        self.hotkey_frame.register(106, c.get("hotkey_shadow_learn", "ctrl+alt+l"))
        self.hotkey_frame.register(107, c.get("hotkey_shadow_clear", "ctrl+alt+r"))
        self.hotkey_frame.register(108, c.get("hotkey_shadow_toggle", "ctrl+alt+u"))
        self.hotkey_frame.register(109, c.get("hotkey_manual", "ctrl+alt+f1"))
        self.hotkey_frame.register(110, c.get("hotkey_toggle_auto_rescan", "ctrl+alt+a"))
        self.hotkey_frame.register(111, c.get("hotkey_pdf", "ctrl+alt+p"))

    def _on_open_manual(self):
        self._release_modifiers()
        import webbrowser
        manual_path = os.path.join(get_base_path(), "manual.html")
        if os.path.exists(manual_path):
            webbrowser.open(f"file:///{manual_path}")
            self.tts.speak("Abriendo manual.")
        else:
            self.tts.speak("No se encontró el manual.")

    def _on_toggle_auto_rescan(self):
        self._release_modifiers()
        current = self.config.get("auto_rescan_after_click", False)
        self.config["auto_rescan_after_click"] = not current
        self.full_config["global"]["auto_rescan_after_click"] = not current
        state = "activado" if not current else "desactivado"
        self.tts.speak(f"Reescaneo automático {state}.")

    def _release_modifiers(self):
        def _do_release():
            for vk in [0x11, 0x12, 0x10, 0x5B, 0x5C]: ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)
        threading.Thread(target=_do_release, daemon=True).start()

    def _on_learn_shadow(self): threading.Thread(target=self._do_burst_learning, daemon=True).start()

    def _do_burst_learning(self):
        app_name = self._get_current_app_name(); self.shadow.set_app(app_name)
        self.tts.speak("Aprendizaje iniciado.")
        burst_results = []
        burst_count = int(self.config.get("shadow_burst_count", 4))
        for i in range(burst_count):
            try:
                img, ox, oy = capture_screen(); elements = self.ocr.scan_image(img)
                burst_results.append(elements); self.tts.play_scan_start()
            except Exception as e: logger.error(f"Error en aprendizaje: {e}")
            time.sleep(1.0)
        count = self.shadow.learn_from_burst(burst_results)
        if count > 0:
            self.tts.play_scan_success(); self.tts.speak(f"Completado. {count} sombras fijadas.")
        else: self.tts.play_error(); self.tts.speak("Sin sombras nuevas.")

    def _on_clear_shadow(self): self._release_modifiers(); self.shadow.clear(); self.tts.speak("Sombras borradas.")
    def _on_toggle_shadow(self): self._release_modifiers(); state = self.shadow.toggle(); self.tts.speak("Sombra activa." if state else "Sombra inactiva.")

    def _on_scan_screen(self): 
        img, ox, oy = capture_screen()
        if np.mean(img[::10, ::10]) < 0.1:
            self.tts.play_error()
            self.tts.speak("Es necesario desactivar la cortina de pantalla antes de escanear.")
            threading.Thread(target=self._release_modifiers, daemon=True).start()
            return
        self.tts.speak("Escaneando pantalla."); self._release_modifiers(); self._update_profile()
        self._start_scan("screen", img_data=(img, ox, oy))

    def _on_scan_window(self): 
        img, ox, oy = capture_active_window()
        if np.mean(img[::10, ::10]) < 0.1:
            self.tts.play_error()
            self.tts.speak("Es necesario desactivar la cortina de pantalla antes de escanear.")
            threading.Thread(target=self._release_modifiers, daemon=True).start()
            return
        self.tts.speak("Escaneando ventana."); self._release_modifiers(); self._update_profile()
        self._start_scan("window", img_data=(img, ox, oy))

    def _apply_crops(self, img, ox, oy):
        h, w = img.shape[:2]
        ct, cb, cl, cr = [float(self.config.get(k, 0))/100.0 for k in ["crop_top", "crop_bottom", "crop_left", "crop_right"]]
        y1, y2 = int(h * ct), int(h * (1.0 - cb)); x1, x2 = int(w * cl), int(w * (1.0 - cr))
        if y2 <= y1 + 50: y1, y2 = 0, h
        if x2 <= x1 + 50: x1, x2 = 0, w
        return img[y1:y2, x1:x2], ox + x1, oy + y1

    def _toggle_dynamic_scan(self):
        self._release_modifiers()
        if self.is_dynamic_running:
            self.is_dynamic_running = False; self.tts.play_error(); self.tts.speak("Escaneo dinámico detenido.")
        else:
            img, ox, oy = capture_active_window() if self.config.get("dynamic_target") == "window" else capture_screen()
            if np.mean(img) < 0.1:
                self.tts.play_error()
                self.tts.speak("Es necesario desactivar la cortina de pantalla antes de escanear.")
                return
            self._update_profile(); self.is_dynamic_running = True
            self.tts.play_scan_start(); self.tts.speak("Escaneo dinámico activado.")
            threading.Thread(target=self._dynamic_scan_loop, daemon=True).start()

    def _dynamic_scan_loop(self):
        prev_text = ""
        prev_elements_texts = set()
        prev_small_img = None
        while self.is_dynamic_running:
            loop_start = time.time()
            try:
                self._update_profile()
                img, ox, oy = capture_active_window() if self.config.get("dynamic_target") == "window" else capture_screen()
                
                if np.mean(img) < 0.1:
                    time.sleep(1.0)
                    continue

                img, ox, oy = self._apply_crops(img, ox, oy)

                sens_val = int(self.config.get("dynamic_sensitivity", 50))
                
                small_img = cv2.resize(img, (128, 128), interpolation=cv2.INTER_NEAREST)
                small_gray = small_img[:, :, 1]
                
                LEVELS = {
                    10:  (7, 0.10, 600), # Nivel 1 (Mínima)
                    20:  (6, 0.15, 400), # Nivel 2
                    30:  (5, 0.25, 250), # Nivel 3
                    40:  (4, 0.35, 120), # Nivel 4
                    50:  (3, 0.50, 60),  # Nivel 5 (Medio)
                    60:  (2, 0.65, 30),  # Nivel 6
                    70:  (2, 0.75, 15),  # Nivel 7
                    80:  (1, 0.85, 8),   # Nivel 8
                    90:  (1, 0.95, 4),   # Nivel 9
                    100: (1, 0.99, 2)    # Nivel 10 (Máxima)
                }
                
                level_key = min(LEVELS.keys(), key=lambda k: abs(k - sens_val))
                min_len, threshold, pixel_threshold = LEVELS[level_key]

                if prev_small_img is not None:
                    diff = cv2.absdiff(small_gray, prev_small_img)
                    changed_pixels = np.sum(diff > 15)
                    
                    if changed_pixels < pixel_threshold:
                        elapsed = time.time() - loop_start
                        remaining = max(0.1, float(self.config.get("dynamic_interval", 1.0)) - elapsed)
                        time.sleep(remaining)
                        continue
                
                prev_small_img = small_gray.copy()

                with self._scan_lock: elements = self.ocr.scan_image(img)
                self._last_elements = elements
                elements = self.shadow.filter_elements(elements)

                if self.config.get("dynamic_diff_mode", False):
                    current_texts = [e.text.strip() for e in elements if len(e.text.strip()) >= min_len]
                    new_texts = []
                    
                    for txt in current_texts:
                        is_present = False
                        for seen in prev_elements_texts:
                            if SequenceMatcher(None, txt.lower(), seen.lower()).ratio() >= threshold:
                                is_present = True; break
                        
                        if not is_present:
                            new_texts.append(txt)
                    
                    prev_elements_texts = set(current_texts)
                    
                    if new_texts:
                        new_text = " ".join(new_texts)
                        if self.config.get("translate_enabled"):
                            from_code = self.config.get("translate_from", "en")
                            to_code = self.config.get("translate_to", "es")
                            new_text = translator_instance.translate(
                                new_text, from_code, to_code, 
                                translate_type=self.config.get("translate_type", "disabled"),
                                service=self.config.get("translate_service", "google"),
                                swap=self.config.get("translate_swap", False)
                            )
                        self.tts.speak(new_text, interrupt=self.config.get("dynamic_interrupt", False))
                else:
                    prev_elements_texts.clear()
                    filtered_elements = [e for e in elements if len(e.text.strip()) >= min_len]
                    full_text = " ".join([e.text for e in filtered_elements]).strip()
                    if full_text and SequenceMatcher(None, prev_text, full_text).ratio() < threshold:
                        prev_text = full_text
                        if self.config.get("translate_enabled"):
                            from_code = self.config.get("translate_from", "en")
                            to_code = self.config.get("translate_to", "es")
                            full_text = translator_instance.translate(
                                full_text, from_code, to_code, 
                                translate_type=self.config.get("translate_type", "disabled"),
                                service=self.config.get("translate_service", "google"),
                                swap=self.config.get("translate_swap", False)
                            )
                        self.tts.speak(full_text, interrupt=self.config.get("dynamic_interrupt", False))
            except Exception as e: logger.error(f"Error dinámico: {e}")
            
            elapsed = time.time() - loop_start
            remaining = max(0, float(self.config.get("dynamic_interval", 1.0)) - elapsed)
            time.sleep(remaining)

    def _start_scan(self, mode, img_data=None):
        if self._scan_lock.locked(): return
        threading.Thread(target=self._do_scan, args=(mode, img_data), daemon=True).start()

    def _do_scan(self, mode, img_data=None):
        with self._scan_lock:
            try:
                self.tts.play_scan_start()
                if img_data:
                    img, ox, oy = img_data
                else:
                    img, ox, oy = capture_active_window() if mode == "window" else capture_screen()
                    if np.mean(img) < 0.1:
                        self.tts.play_error()
                        self.tts.speak("Es necesario desactivar la cortina de pantalla antes de escanear.")
                        return

                img, ox, oy = self._apply_crops(img, ox, oy)
                raw = self.ocr.scan_image(img); self._last_elements = raw
                elements = self.shadow.filter_elements(raw)
            except Exception as e:
                logger.error(f"Error en escaneo: {e}")
                self.tts.speak("Error en el escaneo.")
                return

        if self.active_navigator:
            try: self.active_navigator._stop()
            except: pass
            self.active_navigator = None

        if elements:
            self.tts.play_scan_success()
            self.tts.speak(f"{len(elements)} resultados.", interrupt=True)
            nav = ElementNavigator(self.tts, self.config, ox, oy, rescan_callback=lambda: self._start_scan(mode))
            self.active_navigator = nav
            try:
                nav.navigate(elements)
            finally:
                if self.active_navigator == nav:
                    self.active_navigator = None
        else: 
            self.tts.play_error(); self.tts.speak("No se detectó nada.", interrupt=True)

    def _on_open_config(self): self._release_modifiers(); wx.CallAfter(self._open_config_native)

    def _open_config_native(self):
        from gui_config import show_config_window
        app_name = self._get_current_app_name()
        res = show_config_window(self.full_config, self._last_profile, active_app=app_name)
        if res:
            old_trans = self.config.get("translate_enabled", False)
            self.full_config = res
            self.shadow.load()
            
            self._last_processed_app = None
            self._update_profile()
            new_trans = self.config.get("translate_enabled", False)
            
            msg = "Guardado."
            if old_trans != new_trans:
                msg += " Traducción " + ("activada." if new_trans else "desactivada.")
                if new_trans and self.config.get("translate_type", "disabled") == "local":
                    translator_instance.ensure_initialized()
            
            translator_instance.refresh_languages()
            self.tts.speak(msg)
        self._refresh_hotkeys()

    def _on_open_pdf_transcriptor(self):
        self._release_modifiers()
        wx.CallAfter(self._open_pdf_transcriptor_native)

    def _open_pdf_transcriptor_native(self):
        from pdf_transcriptor import TranscriptorFrame
        frame = TranscriptorFrame(self.full_config)
        frame.Show()
        frame.Raise()
        frame.SetFocus()

    def _on_quit_hotkey(self):
        self._release_modifiers()
        if self.active_navigator:
            try: self.active_navigator._stop()
            except: pass
        if self.app: wx.CallAfter(self.app.ExitMainLoop)

def check_single_instance():
    ERROR_ALREADY_EXISTS = 183
    global _app_mutex
    _app_mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\WinOCRScanner_UniqueMutex")
    if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return True
    return False

def main():
    if check_single_instance():
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{os.path.abspath(sys.argv[0])}"', None, 1)
    else: 
        try:
            WinOCRScanner().start()
        except Exception as e:
            import traceback
            with open("error.log", "w") as f:
                traceback.print_exc(file=f)

if __name__ == "__main__": main()