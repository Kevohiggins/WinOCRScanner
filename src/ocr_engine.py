import logging
import os
from dataclasses import dataclass
import numpy as np
import cv2

logger = logging.getLogger(__name__)

@dataclass
class DetectedElement:
    text: str
    bbox: list  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    center_x: float
    center_y: float
    confidence: float
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0
    words_list: list = None

class OCREngine:
    def __init__(self, config: dict):
        self.config = config
        self._ocr_module = None
        self.available_langs = []
        self.active_lang = "en"

    def initialize(self):
        try:
            import winocr
            from winrt.windows.media.ocr import OcrEngine as WinRTOcr
            self._ocr_module = winocr
            
            # 1. Detectamos qué hay instalado de verdad en el Windows del usuario
            try:
                self.available_langs = [l.language_tag for l in WinRTOcr.available_recognizer_languages]
                logger.info(f"OCREngine: Lenguajes OCR detectados en el sistema: {self.available_langs}")
            except Exception as e:
                logger.warning(f"No se pudo listar los lenguajes OCR de WinRT: {e}")
                self.available_langs = []

            # 2. Lógica de selección inteligente (Fallback)
            requested_lang = self.config.get("ocr_language", "es")
            
            # Mapeo de nombres amigables a tags de Windows
            lang_map = {
                "latin": "en-US", "english": "en-US",
                "spanish": "es-ES", "es": "es-ES",
                "japanese": "ja-JP", "ja": "ja-JP",
                "chinese": "zh-Hans",
                "korean": "ko-KR",
                "russian": "ru-RU", "cyrillic": "ru-RU"
            }
            
            target = lang_map.get(requested_lang, requested_lang)
            
            # Si el pedido no está, buscamos alternativas
            if target not in self.available_langs:
                logger.info(f"OCREngine: El lenguaje '{target}' no está instalado.")
                
                # Intentamos buscar por prefijo (ej: si pide 'es' y hay 'es-ES')
                prefix_match = next((l for l in self.available_langs if l.startswith(target.split('-')[0])), None)
                
                if prefix_match:
                    target = prefix_match
                    logger.info(f"OCREngine: Usando coincidencia por prefijo: {target}")
                elif "es-ES" in self.available_langs:
                    target = "es-ES"
                elif "es-MX" in self.available_langs:
                    target = "es-MX"
                elif "en-US" in self.available_langs:
                    target = "en-US"
                elif self.available_langs:
                    target = self.available_langs[0]
                else:
                    logger.error("OCREngine: ¡No hay NINGÚN paquete de OCR instalado en Windows!")
                    raise RuntimeError("No se detectaron paquetes de idioma OCR. Instala uno en Configuración de Windows.")

            self.active_lang = target
            logger.info(f"OCREngine: Lenguaje activo final: {self.active_lang}")

            # Prueba de fuego con el lenguaje elegido
            dummy_img = np.zeros((64, 64, 3), dtype=np.uint8)
            self._ocr_module.recognize_cv2_sync(dummy_img, self.active_lang)
            logger.info("OCREngine: Motor nativo WinOCR (WinRT) verificado correctamente.")
            
        except Exception as e:
            logger.error(f"Error crítico inicializando el OCR de Windows: {e}")
            raise

    def scan_image(self, image: np.ndarray) -> list[DetectedElement]:
        if self._ocr_module is None:
            raise RuntimeError("OCREngine no inicializado.")

        scale_val = self.config.get("image_scale")
        scale_factor = float(scale_val) if scale_val is not None else 1.0
        original_h, original_w = image.shape[:2]
        
        if scale_factor != 1.0 and scale_factor > 0:
            new_w, new_h = int(original_w * scale_factor), int(original_h * scale_factor)
            if new_w > 0 and new_h > 0:
                process_image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            else:
                process_image = image
        else:
            process_image = image

        # ---------------------------------------------------------
        # PIPELINE DE MEJORAS (Portado de Paddle OCR)
        # ---------------------------------------------------------
        has_improvements = any([
            self.config.get("use_sharpening", False),
            self.config.get("use_clahe", False),
            self.config.get("use_binarization", False),
            self.config.get("use_dilation", False)
        ])

        if has_improvements:
            # 1. Pasamos a gris de entrada para procesamiento rápido
            if len(process_image.shape) == 3:
                process_image = cv2.cvtColor(process_image, cv2.COLOR_BGR2GRAY)

            # 2. Enfoque (Sharpening)
            if self.config.get("use_sharpening", False):
                kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
                process_image = cv2.filter2D(process_image, -1, kernel)

            # 3. Contraste (CLAHE)
            if self.config.get("use_clahe", False):
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                process_image = clahe.apply(process_image)

            # 4. Binarización (Blanco y Negro puro)
            if self.config.get("use_binarization", False):
                process_image = cv2.adaptiveThreshold(process_image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

            # 5. Engrosar letras (Dilatación)
            if self.config.get("use_dilation", False):
                kernel = np.ones((2,2), np.uint8)
                process_image = cv2.dilate(process_image, kernel, iterations=1)

            # Reconversión a BGR para asegurar compatibilidad con winocr/WinRT que pueden esperar 3 canales.
            if len(process_image.shape) == 2:
                process_image = cv2.cvtColor(process_image, cv2.COLOR_GRAY2BGR)
        # ---------------------------------------------------------

        try:
            # Usamos el lenguaje que determinamos en la inicialización
            result = self._ocr_module.recognize_cv2_sync(process_image, self.active_lang)
            logger.info(f"OCREngine: Resultado crudo de winocr recibido. Líneas: {len(result.get('lines', [])) if result else 0}")
        except Exception as e:
            logger.error(f"Error en escaneo nativo ({self.active_lang}): {e}")
            return []

        if not result or 'lines' not in result:
            logger.warning("OCREngine: No se obtuvieron líneas en el resultado.")
            return []

        elements = []
        # Para WinOCR no necesitamos agrupar (ya vienen líneas), pero usamos una tolerancia fija
        # de 20px para el ordenamiento y asegurar un flujo de lectura coherente.
        row_tolerance = 20 

        for line in result['lines']:
            line_text = line.get('text', '').strip()
            words = line.get('words', [])
            if not words or not line_text:
                continue

            xs, ys, max_xs, max_ys = [], [], [], []
            line_words = []
            for w in words:
                # CORRECCIÓN: La librería winocr usa 'bounding_rect'
                rect = w.get('bounding_rect', {})
                w_text = w.get('text', '')
                if rect and w_text:
                    wx_val, wy_val = rect.get('x', 0), rect.get('y', 0)
                    ww_val, wh_val = rect.get('width', 0), rect.get('height', 0)
                    if scale_factor != 1.0 and scale_factor > 0:
                        wx_val /= scale_factor
                        wy_val /= scale_factor
                        ww_val /= scale_factor
                        wh_val /= scale_factor
                    line_words.append({'text': w_text, 'x': wx_val, 'y': wy_val, 'w': ww_val, 'h': wh_val})
                    xs.append(rect.get('x', 0))
                    ys.append(rect.get('y', 0))
                    max_xs.append(rect.get('x', 0) + rect.get('width', 0))
                    max_ys.append(rect.get('y', 0) + rect.get('height', 0))

            if not xs:
                continue

            x_min, y_min = min(xs), min(ys)
            x_max, y_max = max(max_xs), max(max_ys)
            w_line = x_max - x_min
            h_line = y_max - y_min

            if scale_factor != 1.0 and scale_factor > 0:
                x_min /= scale_factor
                y_min /= scale_factor
                w_line /= scale_factor
                h_line /= scale_factor

            center_x = x_min + (w_line / 2.0)
            center_y = y_min + (h_line / 2.0)

            bbox = [
                [x_min, y_min],
                [x_min + w_line, y_min],
                [x_min + w_line, y_min + h_line],
                [x_min, y_min + h_line]
            ]

            elements.append(DetectedElement(
                text=line_text,
                bbox=bbox,
                center_x=center_x,
                center_y=center_y,
                confidence=1.0,
                x=x_min,
                y=y_min,
                w=w_line,
                h=h_line,
                words_list=line_words
            ))

        logger.info(f"OCREngine: Escaneo completado. Elementos procesados: {len(elements)}")
        elements.sort(key=lambda e: (round(e.center_y / row_tolerance) * row_tolerance, e.center_x))
        return elements