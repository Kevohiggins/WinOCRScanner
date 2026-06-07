import json
import os
import sys
import ctypes

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_system_ocr_lang():
    """Intenta detectar el idioma del sistema para el OCR."""
    try:
        # GetUserDefaultUILanguage devuelve el ID de idioma del sistema
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        primary_lang = lang_id & 0x3FF
        if primary_lang == 0x0A: return "es" # Español
        if primary_lang == 0x11: return "ja" # Japonés
        if primary_lang == 0x04: return "zh-Hans" # Chino
        if primary_lang == 0x12: return "ko" # Coreano
        if primary_lang == 0x19: return "ru" # Ruso
    except:
        pass
    return "en" # Default seguro

CONFIG_FILE = os.path.join(get_base_path(), "config.json")
VERSION = "1.1"

DEFAULT_CONFIG = {
    "global": {
        "ocr_language": get_system_ocr_lang(),
        "min_confidence": 0.3,
        "image_scale": 1.0,
        "auto_check_updates": True,
        "hotkey_screen": "ctrl+alt+s",
        "hotkey_window": "ctrl+alt+w",
        "hotkey_config": "ctrl+alt+c",
        "hotkey_quit": "ctrl+alt+q",
        "dynamic_interval": 1.0,
        "hotkey_dynamic": "ctrl+alt+d",
        "dynamic_target": "screen",
        "crop_top": 0,
        "crop_bottom": 0,
        "crop_left": 0,
        "crop_right": 0,
        "dynamic_sensitivity": 50,
        "dynamic_diff_mode": False,
        "key_next": "down",
        "key_prev": "up",
        "key_click": "enter",
        "key_double": "shift+enter",
        "key_right": "apps",
        "key_exit": "esc",
        "translate_enabled": False,
        "translate_to": "es",
        "translate_from": "en", # Inglés a Español es lo más común
        "hotkey_shadow_learn": "ctrl+alt+l",
        "hotkey_shadow_clear": "ctrl+alt+r",
        "hotkey_shadow_toggle": "ctrl+alt+u",
        "shadow_burst_count": 4,
        "key_copy": "ctrl+c",
        "key_first": "home",
        "key_last": "end",
        "key_skip_next": "right",
        "key_skip_prev": "left",
        "key_repeat": "space",
        "hotkey_manual": "ctrl+alt+f1",
        "auto_rescan_after_click": False,
        "auto_rescan_delay": 5,
        "hotkey_toggle_auto_rescan": "ctrl+alt+a",
        "translate_type": "disabled",
        "translate_service": "google",
        "translate_swap": False,
        "dynamic_interrupt": False
    },
    "profiles": {},
    "shadow_profiles": {}
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            
            if "global" not in user_config:
                new_config = {"global": {}, "profiles": user_config.get("profiles", {}), "shadow_profiles": user_config.get("shadow_profiles", {})}
                for k, v in user_config.items():
                    if k not in ["profiles", "shadow_profiles"]:
                        new_config["global"][k] = v
                user_config = new_config

            final_config = DEFAULT_CONFIG.copy()
            final_config["global"].update(user_config.get("global", {}))
            final_config["profiles"].update(user_config.get("profiles", {}))
            final_config["shadow_profiles"].update(user_config.get("shadow_profiles", {}))
            return final_config
            
        except (json.JSONDecodeError, IOError):
            pass
    
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)

def get_effective_config(full_config: dict, app_name: str = None) -> dict:
    base = full_config.get("global", {}).copy()
    if app_name and app_name in full_config.get("profiles", {}):
        base.update(full_config["profiles"][app_name])
    return base

def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)