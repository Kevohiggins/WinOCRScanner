import logging
import os
import sys
import cv2
from rapid_table import RapidTable
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class TableEngine:
    """
    Motor de reconocimiento de tablas usando la librería oficial RapidTable.
    Configurado para usar el backend de OpenVINO.
    """

    def __init__(self, config: dict):
        self.config = config
        self.table_engine = None

    def initialize(self):
        """Inicializa RapidTable con nuestro modelo de OpenVINO."""
        try:
            if getattr(sys, 'frozen', False):
                base_dir = sys._MEIPASS
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            model_path = os.path.join(base_dir, "models", "slanet.xml")
            
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"No se encontró el modelo de tablas en {model_path}")
            
            # Inicializamos RapidTable usando nuestro modelo de OpenVINO
            # Note: RapidTable elige el engine basándose en el entorno y modelo
            self.table_engine = RapidTable(model_path=model_path)
            
            logger.info("TableEngine: RapidTable inicializado con éxito.")
        except Exception as e:
            logger.error("Error inicializando TableEngine: %s", e)
            self.table_engine = None

    def process_table_region(self, table_img):
        """
        Usa RapidTable para convertir una imagen de tabla en HTML.
        """
        if not self.table_engine:
            return None
        
        try:
            # RapidTable devuelve (html_result, elapse)
            table_html, _ = self.table_engine(table_img)
            return table_html
        except Exception as e:
            logger.error("Error en RapidTable: %s", e)
            return None

    def html_to_matrix(self, html):
        """
        Convierte el HTML generado por RapidTable en una matriz (lista de listas) 
        para facilitar la inserción en Word/Excel.
        """
        if not html:
            return []
            
        try:
            soup = BeautifulSoup(html, 'html.parser')
            rows = []
            for tr in soup.find_all('tr'):
                cells = []
                for td in tr.find_all(['td', 'th']):
                    cells.append(td.get_text().strip())
                if cells:
                    rows.append(cells)
            return rows
        except Exception as e:
            logger.error("Error parseando HTML de tabla: %s", e)
            return []
