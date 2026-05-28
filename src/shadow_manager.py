import json
import os
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class ShadowManager:
    def __init__(self, config_path=None):
        self.config_path = config_path
        self.is_enabled = True
        self.current_app = "Global"
        self.profiles = {"Global": {"regions": [], "texts": []}}
        self.load()

    def load(self):
        if self.config_path and os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.profiles = data.get("shadow_profiles", {"Global": {"regions": [], "texts": []}})
                if "Global" not in self.profiles: self.profiles["Global"] = {"regions": [], "texts": []}
            except: pass

    def save(self):
        if not self.config_path: return
        try:
            data = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f: data = json.load(f)
            data["shadow_profiles"] = self.profiles
            
            if "profiles" not in data: data["profiles"] = {}
            if self.current_app != "Global" and self.current_app not in data["profiles"]:
                data["profiles"][self.current_app] = data.get("global", {}).copy()
                
            with open(self.config_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
        except: pass

    def set_app(self, app_name):
        self.current_app = app_name or "Global"
        if self.current_app not in self.profiles:
            self.profiles[self.current_app] = {"regions": [], "texts": []}

    def learn_from_burst(self, scan_results):
        if not scan_results or len(scan_results) < 2: return 0
        candidates = scan_results[0]
        final_shadows = []
        for cand in candidates:
            is_static = True
            for burst in scan_results[1:]:
                found = False
                for other in burst:
                    # Tolerancia de 12px para el aprendizaje inicial
                    if abs(cand.x - other.x) < 12 and abs(cand.y - other.y) < 12 and \
                       SequenceMatcher(None, cand.text.lower(), other.text.lower()).ratio() > 0.8:
                        found = True; break
                if not found: is_static = False; break
            if is_static: final_shadows.append(cand)
        
        count = 0
        for s in final_shadows:
            added_text = self.add_text_shadow(s.text)
            added_region = self.add_region(s.x, s.y, s.w, s.h)
            if added_text or added_region:
                count += 1
        if count > 0: self.save()
        return count

    def add_region(self, x, y, w, h):
        prof = self.profiles.get(self.current_app, self.profiles["Global"])
        for rx, ry, rw, rh in prof["regions"]:
            if abs(x-rx) < 10 and abs(y-ry) < 10: return False
        prof["regions"].append([x, y, w, h]); return True

    def add_text_shadow(self, text):
        if not text or len(text) < 2: return False
        prof = self.profiles.get(self.current_app, self.profiles["Global"])
        txt = text.strip().lower()
        if txt not in prof["texts"]: prof["texts"].append(txt); return True
        return False

    def clear(self):
        if self.current_app in self.profiles: self.profiles[self.current_app] = {"regions": [], "texts": []}
        self.save()

    def toggle(self):
        self.is_enabled = not self.is_enabled; return self.is_enabled

    def _calculate_overlap_with_grace(self, elem_rect, shadow_rect):
        """
        Calcula el solapamiento aplicando un MARGEN DE GRACIA de 8px a la sombra.
        """
        ex, ey, ew, eh = elem_rect
        sx, sy, sw, sh = shadow_rect
        
        # Expandir la sombra 8px en todas direcciones
        sx -= 8; sy -= 8; sw += 16; sh += 16
        
        dx = min(ex+ew, sx+sw) - max(ex, sx)
        dy = min(ey+eh, sy+sh) - max(ey, sy)
        
        if dx > 0 and dy > 0:
            overlap_area = dx * dy
            elem_area = ew * eh
            # ESCUDO DE TEXTO GRANDE: Si el elemento es 3 veces más grande que la sombra, no lo ignores
            shadow_area = (sw-16) * (sh-16) # Área original sin margen
            if elem_area > (shadow_area * 3.5):
                return 0
            
            return overlap_area / elem_area if elem_area > 0 else 0
        return 0

    def is_shadowed(self, element):
        if not self.is_enabled: return False
        txt = element.text.strip().lower()
        rect = [element.x, element.y, element.w, element.h]
        for p in ["Global", self.current_app]:
            if txt in self.profiles.get(p, {}).get("texts", []): return True
            for sr in self.profiles.get(p, {}).get("regions", []):
                if self._calculate_overlap_with_grace(rect, sr) > 0.6: return True
        return False

    def filter_elements(self, elements):
        if not self.is_enabled: return elements
        return [e for e in elements if not self.is_shadowed(e)]
