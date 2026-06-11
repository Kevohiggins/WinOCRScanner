import logging
import threading
import os
import json
import sys
import traceback
import urllib.request
import zipfile
import shutil
import time

import ctranslate2
import sentencepiece as spm

logger = logging.getLogger("TranslatorMETA")
logger.setLevel(logging.INFO)

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)

if getattr(sys, 'frozen', False):
    _base_model_dir = sys._MEIPASS
else:
    _base_model_dir = get_base_path()
MODELS_DIR = os.path.join(_base_model_dir, "models", "argos_ct2")
os.makedirs(MODELS_DIR, exist_ok=True)

class Translator:
    def __init__(self):
        self._initialized = False
        self._initializing = False
        self._on_ready_callback = None
        self._lock = threading.Lock()
        
        self._master_catalog_path = get_resource_path(os.path.join("src", "assets", "languages_catalog.json"))
        
        self._available_languages = {}
        self._argos_index = []
        self._installed_pairs = set()
        self._loaded_models = {}
        
        self._load_catalogs()

    def _load_catalogs(self):
        if os.path.exists(self._master_catalog_path):
            try:
                with open(self._master_catalog_path, "r", encoding="utf-8") as f:
                    self._available_languages.update(json.load(f))
            except: pass

    def ensure_initialized(self, active_service=None):
        if self._initialized or self._initializing: return
        self._initializing = True
        
        # Determine service for pre-acceleration (dynamic)
        service_to_warm = active_service
        if not service_to_warm:
            try:
                try:
                    from config import load_config
                except ImportError:
                    from .config import load_config
                cfg = load_config()
                service_to_warm = cfg.get("global", {}).get("translate_service", "google")
            except:
                service_to_warm = "google"

        # Pre-cache session dynamically to reduce latency
        try:
            import translators as ts
            print(f"[Translator] Pre-accelerating {service_to_warm}...", flush=True)
            threading.Thread(target=ts.pre_accelerate, args=([service_to_warm],), daemon=True).start()
        except: pass

        threading.Thread(target=self._initialize, daemon=True).start()

    def _initialize(self):
        try:
            logger.info("--- INICIANDO MOTOR DE TRADUCCIÓN ARGOS-BYPASS (CTranslate2) ---")
            self.refresh_languages()
            self._initialized = True
            self._initializing = False
            logger.info(f"Motor listo. Paquetes instalados: {len(self._installed_pairs)}")
            if self._on_ready_callback: self._on_ready_callback()
            
            threading.Thread(target=self._fetch_argos_index, daemon=True).start()
        except Exception as e:
            self._initializing = False
            logger.error(f"Error init: {traceback.format_exc()}")

    def _fetch_argos_index(self):
        try:
            url = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                self._argos_index = json.loads(response.read().decode())
                
            for pkg in self._argos_index:
                self._available_languages[pkg['from_code']] = pkg['from_name']
                self._available_languages[pkg['to_code']] = pkg['to_name']
            logger.info("Catálogo online de Argos actualizado con éxito.")
        except Exception as e:
            logger.warning(f"No se pudo descargar el índice de Argos: {e}")

    def get_available_languages_dict(self):
        return self._available_languages if self._available_languages else {"en": "English", "es": "Spanish", "ja": "Japanese"}

    def refresh_languages(self):
        self._installed_pairs.clear()
        if not os.path.exists(MODELS_DIR): return
        
        for folder in os.listdir(MODELS_DIR):
            folder_path = os.path.join(MODELS_DIR, folder)
            if os.path.isdir(folder_path):
                parts = folder.split('_')
                if len(parts) == 2:
                    self._installed_pairs.add((parts[0], parts[1]))

    def is_model_installed(self, from_code, to_code):
        if not self._initialized: return False
        if (from_code, to_code) in self._installed_pairs: return True
        if (from_code, "en") in self._installed_pairs and ("en", to_code) in self._installed_pairs: return True
        return False

    def _get_model(self, from_code, to_code):
        pair_key = f"{from_code}_{to_code}"
        if pair_key in self._loaded_models:
            return self._loaded_models[pair_key]
            
        model_dir = os.path.join(MODELS_DIR, pair_key)
        ct2_dir = None
        sp_path = None
        
        for root, dirs, files in os.walk(model_dir):
            if "model.bin" in files:
                ct2_dir = root
            if "sentencepiece.model" in files:
                sp_path = os.path.join(root, "sentencepiece.model")
                
        if not ct2_dir or not sp_path:
            return None, None
            
        try:
            translator = ctranslate2.Translator(ct2_dir, device="cpu", compute_type="int8")
            sp_processor = spm.SentencePieceProcessor(model_file=sp_path)
            self._loaded_models[pair_key] = (translator, sp_processor)
            return translator, sp_processor
        except Exception as e:
            logger.error(f"Error cargando modelo en memoria ({pair_key}): {e}")
            return None, None

    def _translate_direct(self, text, from_code, to_code):
        translator, sp_processor = self._get_model(from_code, to_code)
        if not translator or not sp_processor:
            logger.error(f"No se pudo obtener el modelo para {from_code}->{to_code}")
            return text
        
        try:
            lines = text.split('\n')
            translated_lines = []
            
            for line in lines:
                if not line.strip(): 
                    translated_lines.append(line)
                    continue
                normalized_line = line.replace('。', '.')
                raw_sentences = [s.strip() for s in normalized_line.split('.') if s.strip()]
                sentences = []
                for s in raw_sentences:
                    if s[-1] in ('.', '?', '!', '。', '！', '？', '…'):
                        sentences.append(s)
                    else:
                        sentences.append(s + '.')
                
                trans_sentences = []
                for sentence in sentences:
                    source_tokens = sp_processor.encode(sentence, out_type=str)
                    results = translator.translate_batch([source_tokens])
                    trans_text = sp_processor.decode(results[0].hypotheses[0])
                    trans_sentences.append(trans_text)
                    
                translated_lines.append(" ".join(trans_sentences).replace(' .', '.').strip())
                
            return "\n".join(translated_lines)
        except Exception as e:
            logger.error(f"Error en _translate_direct: {e}")
            return text

    def translate(self, text, from_code, to_code, translate_type="local", service="google", swap=False):
        if not text: return text
        
        if translate_type == "online":
            try:
                import translators as ts
                if swap:
                    result = ts.translate_text(text, translator=service, from_language='auto', to_language=to_code)
                    if result.strip().lower() == text.strip().lower():
                        result = ts.translate_text(text, translator=service, from_language='auto', to_language=from_code)
                else:
                    result = ts.translate_text(text, translator=service, from_language='auto', to_language=to_code)
                return result
            except Exception as e:
                logger.error(f"Error en traducción Online: {e}")
                return text
                
        if not self._initialized: return text
        with self._lock:
            if (from_code, to_code) in self._installed_pairs:
                return self._translate_direct(text, from_code, to_code)
            
            if (from_code, "en") in self._installed_pairs and ("en", to_code) in self._installed_pairs:
                text_en = self._translate_direct(text, from_code, "en")
                return self._translate_direct(text_en, "en", to_code)
                
            return text

    def download_model(self, from_code, to_code, progress_callback=None):
        try:
            if progress_callback: progress_callback("Buscando en catálogo...", 5)
            
            if not self._argos_index:
                self._fetch_argos_index()
                
            if not self._argos_index:
                if progress_callback: progress_callback("Error de conexión", 0)
                return False
                
            needed = []
            direct = next((p for p in self._argos_index if p['from_code'] == from_code and p['to_code'] == to_code), None)
            if direct:
                needed = [direct]
            else:
                p1 = next((p for p in self._argos_index if p['from_code'] == from_code and p['to_code'] == "en"), None)
                p2 = next((p for p in self._argos_index if p['from_code'] == "en" and p['to_code'] == to_code), None)
                if p1 and p2: needed = [p1, p2]
                
            if not needed:
                if progress_callback: progress_callback("No existe modelo", 0)
                return False

            import tempfile
            for i, pkg in enumerate(needed):
                fc, tc = pkg['from_code'], pkg['to_code']
                if (fc, tc) in self._installed_pairs: continue
                
                url = pkg['links'][0]
                dl_path = os.path.join(tempfile.gettempdir(), f"{fc}_{tc}.argosmodel")
                extract_path = os.path.join(MODELS_DIR, f"{fc}_{tc}")
                
                def reporthook(b, bs, ts):
                    if ts > 0 and progress_callback:
                        p = (b * bs / ts); overall = int(((i + p) / len(needed)) * 100)
                        progress_callback(f"Descargando {i+1}/{len(needed)}...", min(99, overall))
                
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)
                
                urllib.request.urlretrieve(url, dl_path, reporthook)
                
                if progress_callback: progress_callback(f"Descomprimiendo {i+1}/{len(needed)}...", 99)
                
                if os.path.exists(extract_path): shutil.rmtree(extract_path)
                with zipfile.ZipFile(dl_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                    
                os.remove(dl_path)
                
            self.refresh_languages()
            if progress_callback: progress_callback("¡Hecho!", 100)
            return True
        except Exception as e:
            logger.error(f"Fallo en descarga: {traceback.format_exc()}")
            if progress_callback: progress_callback("Error", 0)
            return False

    def delete_model(self, from_code, to_code):
        try:
            paths_to_delete = []
            dir_direct = os.path.join(MODELS_DIR, f"{from_code}_{to_code}")
            if os.path.exists(dir_direct): paths_to_delete.append(dir_direct)
            
            for path in paths_to_delete:
                shutil.rmtree(path)
                
            self._loaded_models.pop(f"{from_code}_{to_code}", None)
            self.refresh_languages()
            return True
        except: return False

    def set_on_ready_callback(self, cb):
        self._on_ready_callback = cb
        if self._initialized: cb()

translator_instance = Translator()