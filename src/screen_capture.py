import numpy as np
import mss
import win32gui
import threading
import cv2  # ¡Añadimos OpenCV acá!

_thread_local = threading.local()

def get_sct():
    if not hasattr(_thread_local, 'sct'):
        _thread_local.sct = mss.mss()
    return _thread_local.sct

def capture_screen(monitor_index: int = 1) -> tuple[np.ndarray, int, int]:
    sct = get_sct()
    monitor = sct.monitors[monitor_index]
    screenshot = sct.grab(monitor)
    
    # 1. CERO COPIAS: Leemos la memoria RAM cruda (instantáneo)
    img_bgra = np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape((monitor["height"], monitor["width"], 4))
    
    # 2. Extraemos los 3 colores (BGR) usando C++ ultra optimizado
    # ¡No lo pasamos a RGB! A OpenCV y RapidOCR les gusta el BGR.
    img = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
    
    return img, monitor["left"], monitor["top"]

def capture_active_window() -> tuple[np.ndarray, int, int]:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return capture_screen()
    try:
        rect = win32gui.GetWindowRect(hwnd)
        x, y, x2, y2 = rect
        width = x2 - x
        height = y2 - y
    except Exception:
        return capture_screen()

    if width <= 0 or height <= 0:
        return capture_screen()

    sct = get_sct()
    region = {"left": x, "top": y, "width": width, "height": height}
    screenshot = sct.grab(region)
    
    # 1. CERO COPIAS
    img_bgra = np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape((height, width, 4))
    
    # 2. Extracción a BGR
    img = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
    
    return img, x, y