import logging
import os
import sys
import cv2
import numpy as np
from rapid_layout import RapidLayout

logger = logging.getLogger(__name__)

class LayoutEngine:
    """
    Motor de análisis de Layout basado en PicoDet con OpenVINO.
    Detecta regiones como: Texto, Tabla, Imagen, Título, etc.
    """

    def __init__(self, config: dict):
        self.config = config
        self.layout_engine = None

    def initialize(self):
        """Inicializa el modelo de Layout con OpenVINO."""
        try:
            if getattr(sys, 'frozen', False):
                base_dir = sys._MEIPASS
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            model_path = os.path.join(base_dir, "models", "layout.xml")
            
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"No se encontró el modelo de Layout en {model_path}")
            
            # Inicializamos RapidLayout (usa el backend optimizado de OpenVINO internamente si está disponible)
            self.layout_engine = RapidLayout(model_path=model_path)
            
            logger.info("LayoutEngine: PicoDet (RapidLayout) inicializado con éxito.")
        except Exception as e:
            logger.error("Error inicializando LayoutEngine: %s", e)
            self.layout_engine = None

    def analyze_page(self, img):
        """
        Analiza una imagen de página y devuelve una lista de regiones detectadas.
        Cada región: {'type': 'table'|'text', 'bbox': [x1, y1, x2, y2]}
        """
        if not self.layout_engine:
            h, w = img.shape[:2]
            return [{'type': 'text', 'bbox': [0, 0, w, h]}]
        
        try:
            # layout_res es una lista de diccionarios: 
            # [{'bbox': [x1, y1, x2, y2], 'label': 'table', 'score': 0.9}, ...]
            layout_res, _ = self.layout_engine(img)
            
            regions = []
            if not layout_res:
                h, w = img.shape[:2]
                return [{'type': 'text', 'bbox': [0, 0, w, h]}]

            for res in layout_res:
                # Mapeamos los nombres de etiquetas a tipos internos simplificados
                label = res['label'].lower()
                
                # Consideramos 'table' como tabla, y el resto como texto/otros para OCR normal
                region_type = 'table' if 'table' in label else 'text'
                
                regions.append({
                    'type': region_type,
                    'bbox': res['bbox'], # [x1, y1, x2, y2]
                    'score': res.get('score', 0)
                })
            
            # Ordenar regiones de arriba a abajo
            regions.sort(key=lambda r: r['bbox'][1])
            
            return regions
        except Exception as e:
            logger.error("Error en análisis de layout: %s", e)
            h, w = img.shape[:2]
            return [{'type': 'text', 'bbox': [0, 0, w, h]}]
