import wx
import os
import json
import logging
import threading
from config import CONFIG_FILE, DEFAULT_CONFIG, save_config

logger = logging.getLogger(__name__)

class HotkeyCaptureDialog(wx.Dialog):
    def __init__(self, parent, config, key_id):
        super().__init__(parent, title="Capturar Atajo", size=(350, 180))
        self.config = config; self.key_id = key_id; self.final_hotkey = ""
        panel = wx.Panel(self); sizer = wx.BoxSizer(wx.VERTICAL)
        self.label = wx.StaticText(panel, label="Presioná el atajo de teclas deseado.\nUsá R para restaurar, o Suprimir para borrarlo.", style=wx.ALIGN_CENTER)
        sizer.Add(self.label, 1, wx.EXPAND | wx.ALL, 20)
        panel.SetSizer(sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)

    def on_key_down(self, event):
        vk = event.GetKeyCode(); mods = []
        if event.ControlDown(): mods.append("ctrl")
        if event.AltDown(): mods.append("alt")
        if event.ShiftDown(): mods.append("shift")
        
        if vk == ord('R') and not mods:
            self.final_hotkey = DEFAULT_CONFIG["global"].get(self.key_id, "")
            self.EndModal(wx.ID_OK)
            return
            
        if vk == wx.WXK_DELETE and not mods:
            self.final_hotkey = "Sin asignar"
            self.EndModal(wx.ID_OK)
            return
        
        key = ""
        if 32 <= vk <= 126: key = chr(vk).lower()
        elif vk == wx.WXK_UP: key = "up"
        elif vk == wx.WXK_DOWN: key = "down"
        elif vk == wx.WXK_LEFT: key = "left"
        elif vk == wx.WXK_RIGHT: key = "right"
        elif vk == wx.WXK_RETURN: key = "enter"
        elif vk == wx.WXK_ESCAPE: key = "esc"
        elif vk == wx.WXK_SPACE: key = "space"
        elif vk == wx.WXK_TAB: key = "tab"
        elif vk == wx.WXK_BACK: key = "backspace"
        elif wx.WXK_F1 <= vk <= wx.WXK_F12: key = f"f{vk - wx.WXK_F1 + 1}"
        elif vk == wx.WXK_WINDOWS_MENU: key = "apps"
        elif vk == wx.WXK_HOME: key = "home"
        elif vk == wx.WXK_END: key = "end"
        elif vk == wx.WXK_PAGEUP: key = "page up"
        elif vk == wx.WXK_PAGEDOWN: key = "page down"
        elif vk == wx.WXK_INSERT: key = "insert"
        elif vk == wx.WXK_DELETE: key = "delete"

        if key:
            self.final_hotkey = "+".join(mods + [key]) if mods else key
            self.EndModal(wx.ID_OK)
        elif not mods: event.Skip()

class ConfigWindow(wx.Dialog):
    PRO_NAMES = {
        "hotkey_screen": "Escanear Pantalla", "hotkey_window": "Escanear Ventana", 
        "hotkey_config": "Abrir Configuración", "hotkey_quit": "Salir del Programa",
        "hotkey_dynamic": "Alternar Escaneo Dinámico", "hotkey_shadow_learn": "Aprender Sombras",
        "hotkey_shadow_clear": "Borrar Sombras", "hotkey_shadow_toggle": "Activar/Desactivar Sombras",
        "key_first": "Primer Resultado", "key_skip_prev": "Retroceder 5 Resultados",
        "key_prev": "Resultado Anterior", "key_next": "Resultado Siguiente",
        "key_skip_next": "Avanzar 5 Resultados", "key_last": "Último Resultado", 
        "key_copy": "Copiar Resultado", "key_repeat": "Repetir/Deletrear",
        "key_click": "Click Izquierdo", "key_double": "Doble Click",
        "key_right": "Click Derecho", "key_exit": "Salir de Navegación",
        "hotkey_manual": "Abrir Manual", "hotkey_toggle_auto_rescan": "Alternar Reescaneo"
    }

    def __init__(self, parent, full_config, current_profile="Global", active_app="", restart_callback=None):
        super().__init__(parent, title="Configuración de WinOCR Scanner", size=(650, 580))
        self.full_config = full_config
        self.current_profile = current_profile
        self.active_app = active_app
        self.temp_config = full_config["profiles"].get(current_profile, full_config["global"]).copy()
        self.restart_callback = restart_callback
        self.is_delete_mode = False
        
        from translator import translator_instance
        langs = translator_instance.get_available_languages_dict()
        self.trans_codes = sorted(langs.keys(), key=lambda k: langs[k])
        self.trans_names = [f"{langs[k]} ({k})" for k in self.trans_codes]
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Selector de Perfil
        p_sizer = wx.BoxSizer(wx.HORIZONTAL)
        p_sizer.Add(wx.StaticText(self, label="Perfil Activo:"), 0, wx.CENTER | wx.ALL, 5)
        profiles = ["Global"] + list(full_config.get("profiles", {}).keys())
        self.profile_choice = wx.Choice(self, choices=profiles)
        try:
            self.profile_choice.SetSelection(profiles.index(self.current_profile))
        except:
            self.profile_choice.SetSelection(0)
            
        self.profile_choice.Bind(wx.EVT_CHOICE, self.on_profile_change)
        p_sizer.Add(self.profile_choice, 1, wx.EXPAND | wx.ALL, 5)
        
        self.btn_add = wx.Button(self, label="Añadir Perfil"); self.btn_add.Bind(wx.EVT_BUTTON, self.on_add_profile)
        self.btn_del = wx.Button(self, label="Eliminar Perfil"); self.btn_del.Bind(wx.EVT_BUTTON, self.on_del_profile)
        p_sizer.Add(self.btn_add, 0, wx.ALL, 5); p_sizer.Add(self.btn_del, 0, wx.ALL, 5)
        main_sizer.Add(p_sizer, 0, wx.EXPAND | wx.ALL, 10)

        # Tabs
        self.tabs = wx.Notebook(self)
        self.tab_general = wx.Panel(self.tabs)
        self.tab_keys = wx.ScrolledWindow(self.tabs, style=wx.VSCROLL)
        self.tab_crops = wx.Panel(self.tabs)
        self.tab_improvements = wx.Panel(self.tabs)
        self.tab_dynamic = wx.Panel(self.tabs)
        self.tab_trans = wx.Panel(self.tabs)
        
        self.tab_keys.SetScrollRate(0, 20)
        
        self.tabs.AddPage(self.tab_general, "General")
        self.tabs.AddPage(self.tab_keys, "Atajos de Teclado")
        self.tabs.AddPage(self.tab_crops, "Recortes")
        self.tabs.AddPage(self.tab_improvements, "Mejoras de Imagen")
        self.tabs.AddPage(self.tab_dynamic, "Escaneo Dinámico")
        self.tabs.AddPage(self.tab_trans, "Traducción")
        
        self._setup_general_tab()
        self._setup_keys_tab()
        self._setup_crops_tab()
        self._setup_improvements_tab()
        self._setup_dynamic_tab()
        self._setup_trans_tab()
        
        main_sizer.Add(self.tabs, 1, wx.EXPAND | wx.ALL, 10)
        self.tabs.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)
        
        # Botones Finales
        btn_sizer = wx.StdDialogButtonSizer()
        save_btn = wx.Button(self, wx.ID_OK, label="Guardar"); save_btn.SetDefault()
        btn_sizer.AddButton(save_btn); btn_sizer.AddButton(wx.Button(self, wx.ID_CANCEL, label="Cancelar"))
        btn_sizer.Realize()
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(main_sizer); self.update_ui_from_config()
        self.Bind(wx.EVT_BUTTON, self.on_save, id=wx.ID_OK)

    def on_tab_changed(self, event):
        if self.tabs.GetPageText(event.GetSelection()) == "Traducción":
            from translator import translator_instance
            if not translator_instance._initialized and not translator_instance._initializing:
                translator_instance.ensure_initialized()
                def safe_update():
                    if self: self.update_trans_ui()
                wx.CallLater(2000, safe_update)
        event.Skip()

    def _setup_general_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL); grid = wx.FlexGridSizer(cols=2, vgap=15, hgap=10); grid.AddGrowableCol(1)
        grid.Add(wx.StaticText(self.tab_general, label="Idioma OCR de Windows (Detectados):"), 0, wx.ALIGN_CENTER_VERTICAL)
        
        # Detectar idiomas instalados dinámicamente
        try:
            from winrt.windows.media.ocr import OcrEngine
            langs = OcrEngine.available_recognizer_languages
            self.win_langs_codes = [l.language_tag for l in langs]
            win_langs_names = [f"{l.display_name} ({l.language_tag})" for l in langs]
            
            if not self.win_langs_codes:
                self.win_langs_codes = ["es-ES"]
                win_langs_names = ["Español (No detectado, fallback)"]
        except Exception as e:
            logger.error(f"Error detectando idiomas instalados: {e}")
            self.win_langs_codes = ["en-US"]
            win_langs_names = ["Inglés (Error al detectar)"]

        self.lang_choice = wx.Choice(self.tab_general, choices=win_langs_names)
        grid.Add(self.lang_choice, 1, wx.EXPAND)
        
        grid.Add(wx.StaticText(self.tab_general, label="Escala de imagen:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.scale_choice = wx.Choice(self.tab_general, choices=[
            "Baja: Muy rápida (50%)", "Alta: Precisa (100%)", "Ultra: Textos diminutos (200%)"
        ])
        grid.Add(self.scale_choice, 1, wx.EXPAND)
        
        self.shadow_burst = self._add_spin(self.tab_general, grid, "Fotos para aprendizaje de sombras (2-15):", 2, 15)
        
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 20)
        
        # Opciones de Actualización y Reescaneo
        self.check_updates = wx.CheckBox(self.tab_general, label="Buscar actualizaciones automáticamente al iniciar")
        sizer.Add(self.check_updates, 0, wx.ALL, 20)
        
        sizer.Add(wx.StaticLine(self.tab_general), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)
        self.check_rescan = wx.CheckBox(self.tab_general, label="Reescanear automáticamente tras hacer click")
        sizer.Add(self.check_rescan, 0, wx.ALL, 20)
        
        rescan_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rescan_sizer.Add(wx.StaticText(self.tab_general, label="Espera para el reescaneo (décimas):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 20)
        self.rescan_delay = wx.SpinCtrl(self.tab_general, min=1, max=100)
        rescan_sizer.Add(self.rescan_delay, 0, wx.LEFT, 10)
        sizer.Add(rescan_sizer, 0, wx.BOTTOM, 20)

        self.tab_general.SetSizer(sizer)

    def _add_spin(self, parent, sizer, label, min_v, max_v):
        sizer.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
        spin = wx.SpinCtrl(parent, min=min_v, max=max_v)
        sizer.Add(spin, 1, wx.EXPAND); return spin

    def _setup_keys_tab(self):
        self.key_sizer = wx.BoxSizer(wx.VERTICAL)
        ids = list(self.PRO_NAMES.keys())
        for kid in ids:
            btn = wx.Button(self.tab_keys, label=f"{self.PRO_NAMES[kid]}: ...", name=kid)
            btn.Bind(wx.EVT_BUTTON, self.on_capture)
            setattr(self, f"btn_{kid}", btn); self.key_sizer.Add(btn, 0, wx.EXPAND | wx.ALL, 5)
        self.tab_keys.SetSizer(self.key_sizer)

    def _setup_crops_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL); grid = wx.FlexGridSizer(cols=2, vgap=15, hgap=10); grid.AddGrowableCol(1)
        self.crop_t = self._add_spin(self.tab_crops, grid, "Recorte Superior (%):", 0, 100)
        self.crop_b = self._add_spin(self.tab_crops, grid, "Recorte Inferior (%):", 0, 100)
        self.crop_l = self._add_spin(self.tab_crops, grid, "Recorte Izquierdo (%):", 0, 100)
        self.crop_r = self._add_spin(self.tab_crops, grid, "Recorte Derecho (%):", 0, 100)
        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 20)
        self.tab_crops.SetSizer(sizer)

    def _setup_improvements_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.check_sharp = wx.CheckBox(self.tab_improvements, label="Enfoque (Sharpening)")
        self.check_clahe = wx.CheckBox(self.tab_improvements, label="Contraste Adaptativo (CLAHE)")
        self.check_bin = wx.CheckBox(self.tab_improvements, label="Binarización (Blanco y Negro puro)")
        self.check_dil = wx.CheckBox(self.tab_improvements, label="Dilatación (Engrosar letras)")
        
        sizer.Add(self.check_sharp, 0, wx.ALL, 15)
        sizer.Add(self.check_clahe, 0, wx.ALL, 15)
        sizer.Add(self.check_bin, 0, wx.ALL, 15)
        sizer.Add(self.check_dil, 0, wx.ALL, 15)
        
        info = wx.StaticText(self.tab_improvements, label="Nota: Estas mejoras ayudan al OCR en fondos complejos, pero consumen más CPU.")
        info.SetForegroundColour(wx.Colour(100, 100, 100))
        sizer.Add(info, 0, wx.ALL, 15)
        
        self.tab_improvements.SetSizer(sizer)

    def _setup_dynamic_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL); grid = wx.FlexGridSizer(cols=2, vgap=20, hgap=10); grid.AddGrowableCol(1)
        self.dyn_target = wx.RadioBox(self.tab_dynamic, label="Objetivo del escaneo", choices=["Pantalla Completa", "Ventana Activa"])
        sizer.Add(self.dyn_target, 0, wx.EXPAND | wx.ALL, 10)
        self.dyn_interval = self._add_spin(self.tab_dynamic, grid, "Intervalo de escaneo (décimas):", 1, 100)
        
        grid.Add(wx.StaticText(self.tab_dynamic, label="Sensibilidad al cambio:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.dyn_sens = wx.Choice(self.tab_dynamic, choices=[
            "Nivel 1 (Mínima)", "Nivel 3", "Nivel 5 (Medio)", "Nivel 7", "Nivel 10 (Máxima)"
        ])
        grid.Add(self.dyn_sens, 1, wx.EXPAND)
        
        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 20)
        self.dyn_diff = wx.CheckBox(self.tab_dynamic, label="Modo Diferencial: solo leer texto nuevo")
        sizer.Add(self.dyn_diff, 0, wx.ALL, 15)
        self.dyn_interrupt = wx.CheckBox(self.tab_dynamic, label="Interrumpir lector para resultados nuevos")
        sizer.Add(self.dyn_interrupt, 0, wx.ALL, 15)
        self.tab_dynamic.SetSizer(sizer)

    def _setup_trans_tab(self):
        sizer = wx.BoxSizer(wx.VERTICAL); grid = wx.FlexGridSizer(cols=2, vgap=20, hgap=10); grid.AddGrowableCol(1)
        
        grid.Add(wx.StaticText(self.tab_trans, label="Tipo de traducción:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.trans_type = wx.Choice(self.tab_trans, choices=[
            "Desactivada", "Local (Offline)", "Online (Translators)"
        ], name="Tipo de traducción")
        self.trans_type.Bind(wx.EVT_CHOICE, self.update_trans_ui)
        grid.Add(self.trans_type, 1, wx.EXPAND)
        
        # Servicio Online
        self.lbl_service = wx.StaticText(self.tab_trans, label="Servicio Online:")
        grid.Add(self.lbl_service, 0, wx.ALIGN_CENTER_VERTICAL)
        self.trans_service = wx.Choice(self.tab_trans, choices=[
            "google", "bing", "deepl", "yandex", "baidu", "alibaba", 
            "apertium", "caiyun", "cloudTranslation", "elia", "hujiang", 
            "iciba", "iflytek", "itranslate", "lingvanex", "myMemory", 
            "niutrans", "papago", "qqFanyi", "reverso", "sogou", 
            "sysTran", "translateCom", "translateMe", "volcEngine", 
            "youdao"
        ], name="Servicio Online")
        grid.Add(self.trans_service, 1, wx.EXPAND)
        
        grid.Add(wx.StaticText(self.tab_trans, label="Traducir de (Origen):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.trans_from = wx.Choice(self.tab_trans, choices=self.trans_names, name="Traducir de")
        self.trans_from.Bind(wx.EVT_CHOICE, self.update_trans_ui)
        grid.Add(self.trans_from, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self.tab_trans, label="Traducir a (Destino):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.trans_to = wx.Choice(self.tab_trans, choices=self.trans_names, name="Traducir a")
        self.trans_to.Bind(wx.EVT_CHOICE, self.update_trans_ui)
        grid.Add(self.trans_to, 1, wx.EXPAND)
        
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 15)
        
        self.trans_swap = wx.CheckBox(self.tab_trans, label="Intercambio Inteligente (Detectar idioma y traducir al opuesto)")
        sizer.Add(self.trans_swap, 0, wx.ALL, 15)
        
        self.trans_status = wx.StaticText(self.tab_trans, label="Estado: Listo")
        sizer.Add(self.trans_status, 0, wx.LEFT, 15)
        self.trans_prog = wx.Gauge(self.tab_trans, range=100); sizer.Add(self.trans_prog, 0, wx.EXPAND | wx.ALL, 15)
        self.btn_download = wx.Button(self.tab_trans, label="Descargar Modelo"); self.btn_download.Bind(wx.EVT_BUTTON, self.on_trans_action)
        sizer.Add(self.btn_download, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        self.tab_trans.SetSizer(sizer)

    def update_trans_ui(self, event=None):
        from translator import translator_instance
        
        selection = self.trans_type.GetSelection()
        enabled = (selection != 0)
        is_local = (selection == 1)
        is_online = (selection == 2)
        
        self.trans_from.Enable(enabled)
        self.trans_to.Enable(enabled)
        
        self.btn_download.Show(is_local)
        self.trans_status.Show(is_local)
        self.trans_prog.Show(is_local)
        
        self.lbl_service.Show(is_online)
        self.trans_service.Show(is_online)
        self.trans_swap.Show(is_online)
        
        current_from_code = "en"
        current_to_code = "es"
        if hasattr(self, 'current_trans_codes') and self.trans_from.GetSelection() != wx.NOT_FOUND:
            try:
                current_from_code = self.current_trans_codes[self.trans_from.GetSelection()]
                current_to_code = self.current_trans_codes[self.trans_to.GetSelection()]
            except: pass
            
        self.current_trans_names = self.trans_names
        self.current_trans_codes = self.trans_codes
        
        self.trans_from.Clear()
        self.trans_from.AppendItems(self.trans_names)
        self.trans_to.Clear()
        self.trans_to.AppendItems(self.trans_names)
        
        if current_from_code in self.trans_codes: self.trans_from.SetSelection(self.trans_codes.index(current_from_code))
        if current_to_code in self.trans_codes: self.trans_to.SetSelection(self.trans_codes.index(current_to_code))
        
        if is_local:
            f = self.trans_codes[self.trans_from.GetSelection()]
            t = self.trans_codes[self.trans_to.GetSelection()]
            if translator_instance.is_model_installed(f, t):
                self.btn_download.SetLabel(f"Eliminar Modelo {f} -> {t}")
                self.btn_download.SetForegroundColour(wx.RED)
                self.is_delete_mode = True
            else:
                self.btn_download.SetLabel(f"Descargar Modelo {f} -> {t}")
                self.btn_download.SetForegroundColour(wx.NullColour)
                self.is_delete_mode = False
                
        self.tab_trans.Layout()

    def on_trans_action(self, event):
        from translator import translator_instance
        f_code = self.trans_codes[self.trans_from.GetSelection()]
        t_code = self.trans_codes[self.trans_to.GetSelection()]
        if self.is_delete_mode:
            if wx.MessageBox(f"¿Eliminar modelo {f_code} -> {t_code}?", "Confirmar", wx.YES_NO) == wx.YES:
                if translator_instance.delete_model(f_code, t_code): self.update_trans_ui()
        else:
            self.btn_download.Disable(); self.trans_status.SetLabel("Estado: Descargando...")
            def run():
                def up(msg, p): wx.CallAfter(self.trans_status.SetLabel, f"Estado: {msg}"); wx.CallAfter(self.trans_prog.SetValue, p)
                if translator_instance.download_model(f_code, t_code, up):
                    wx.CallAfter(self.on_download_complete)
                else:
                    wx.CallAfter(lambda: wx.MessageBox("Error en descarga.", "Error", parent=self))
                wx.CallAfter(self.btn_download.Enable); wx.CallAfter(self.update_trans_ui)
            threading.Thread(target=run, daemon=True).start()

    def on_download_complete(self):
        from translator import translator_instance
        translator_instance.refresh_languages()
        self.update_trans_ui()
        wx.MessageBox("Modelo descargado", "Éxito", parent=self)
        self.btn_download.SetFocus()

    def on_profile_change(self, event):
        new_p = self.profile_choice.GetStringSelection(); self._update_temp_config_from_ui()
        if self.current_profile == "Global": self.full_config["global"].update(self.temp_config)
        else: self.full_config["profiles"][self.current_profile] = self.temp_config.copy()
        self.current_profile = new_p
        self.temp_config = self.full_config["profiles"].get(new_p, self.full_config["global"]).copy()
        self.update_ui_from_config()

    def on_add_profile(self, event):
        dlg = wx.TextEntryDialog(self, f"Nombre del nuevo perfil:", "Añadir Perfil", value=self.active_app)
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            if name and name not in self.full_config["profiles"]:
                self.full_config["profiles"][name] = self.full_config["global"].copy()
                self.profile_choice.Append(name); self.profile_choice.SetStringSelection(name); self.on_profile_change(None)

    def on_del_profile(self, event):
        p = self.profile_choice.GetStringSelection()
        if p != "Global" and wx.MessageBox(f"¿Eliminar perfil '{p}'?", "Confirmar", wx.YES_NO) == wx.YES:
            del self.full_config["profiles"][p]
            if "shadow_profiles" in self.full_config and p in self.full_config["shadow_profiles"]:
                del self.full_config["shadow_profiles"][p]
            self.profile_choice.Delete(self.profile_choice.GetSelection())
            self.current_profile = "Global"
            self.profile_choice.SetSelection(0)
            self.temp_config = self.full_config["global"].copy()
            self.update_ui_from_config()

    def on_capture(self, event):
        btn = event.GetEventObject(); kid = btn.GetName()
        dlg = HotkeyCaptureDialog(self, self.temp_config, kid)
        if dlg.ShowModal() == wx.ID_OK:
            self.temp_config[kid] = dlg.final_hotkey; btn.SetLabel(f"{self.PRO_NAMES[kid]}: {dlg.final_hotkey}")
        dlg.Destroy()

    def update_ui_from_config(self):
        c = self.temp_config; defs = DEFAULT_CONFIG["global"]
        
        lang = c.get("ocr_language", "en")
        # Buscamos la mejor coincidencia en la lista dinámica
        target_idx = 0 # Default al primero de la lista
        for i, code in enumerate(self.win_langs_codes):
            if code == lang or code.startswith(lang):
                target_idx = i
                break
        self.lang_choice.SetSelection(target_idx)

        s_map = {0.5:0, 1.0:1, 2.0:2}
        self.scale_choice.SetSelection(s_map.get(c.get("image_scale", 1.0), 1))
        
        for kid in self.PRO_NAMES: getattr(self, f"btn_{kid}").SetLabel(f"{self.PRO_NAMES[kid]}: {c.get(kid, defs.get(kid, 'Sin asignar'))}")
        
        self.crop_t.SetValue(int(c.get("crop_top", 0))); self.crop_b.SetValue(int(c.get("crop_bottom", 0)))
        self.crop_l.SetValue(int(c.get("crop_left", 0))); self.crop_r.SetValue(int(c.get("crop_right", 0)))
        
        self.check_sharp.SetValue(c.get("use_sharpening", False))
        self.check_clahe.SetValue(c.get("use_clahe", False))
        self.check_bin.SetValue(c.get("use_binarization", False))
        self.check_dil.SetValue(c.get("use_dilation", False))

        self.shadow_burst.SetValue(int(c.get("shadow_burst_count", 4)))
        self.check_updates.SetValue(c.get("auto_check_updates", True))
        self.check_rescan.SetValue(c.get("auto_rescan_after_click", False))
        self.rescan_delay.SetValue(int(c.get("auto_rescan_delay", 5)))

        self.dyn_target.SetSelection(0 if c.get("dynamic_target", "screen") == "screen" else 1)
        self.dyn_interval.SetValue(int(c.get("dynamic_interval", 1.0) * 10))
        
        sens_val = int(c.get("dynamic_sensitivity", 50))
        s_map_sens = {10:0, 30:1, 50:2, 70:3, 100:4}
        self.dyn_sens.SetSelection(s_map_sens.get(sens_val, 2))
        
        self.dyn_diff.SetValue(c.get("dynamic_diff_mode", False))
        self.dyn_interrupt.SetValue(c.get("dynamic_interrupt", False))
        
        t_type = c.get("translate_type", "local" if c.get("translate_enabled", False) else "disabled")
        if t_type == "disabled": t_idx = 0
        elif t_type == "local": t_idx = 1
        else: t_idx = 2
        self.trans_type.SetSelection(t_idx)
        
        self.trans_service.SetStringSelection(c.get("translate_service", "google"))
        self.trans_swap.SetValue(c.get("translate_swap", False))
        
        f_code = c.get("translate_from", "en"); t_code = c.get("translate_to", "es")
        if f_code in self.trans_codes: self.trans_from.SetSelection(self.trans_codes.index(f_code))
        if t_code in self.trans_codes: self.trans_to.SetSelection(self.trans_codes.index(t_code))
        
        self.update_trans_ui()

    def _update_temp_config_from_ui(self):
        self.temp_config["ocr_language"] = self.win_langs_codes[self.lang_choice.GetSelection()]
        s_vals = [0.5, 1.0, 2.0]
        self.temp_config["image_scale"] = s_vals[self.scale_choice.GetSelection()]
        self.temp_config["crop_top"] = self.crop_t.GetValue(); self.temp_config["crop_bottom"] = self.crop_b.GetValue()
        self.temp_config["crop_left"] = self.crop_l.GetValue(); self.temp_config["crop_right"] = self.crop_r.GetValue()
        
        self.temp_config["use_sharpening"] = self.check_sharp.GetValue()
        self.temp_config["use_clahe"] = self.check_clahe.GetValue()
        self.temp_config["use_binarization"] = self.check_bin.GetValue()
        self.temp_config["use_dilation"] = self.check_dil.GetValue()

        self.temp_config["shadow_burst_count"] = self.shadow_burst.GetValue()
        self.temp_config["auto_check_updates"] = self.check_updates.GetValue()
        self.temp_config["auto_rescan_after_click"] = self.check_rescan.GetValue()
        self.temp_config["auto_rescan_delay"] = self.rescan_delay.GetValue()

        self.temp_config["dynamic_target"] = "screen" if self.dyn_target.GetSelection() == 0 else "window"
        self.temp_config["dynamic_interval"] = self.dyn_interval.GetValue() / 10.0
        
        s_vals_sens = [10, 30, 50, 70, 100]
        self.temp_config["dynamic_sensitivity"] = s_vals_sens[self.dyn_sens.GetSelection()]
        self.temp_config["dynamic_diff_mode"] = self.dyn_diff.GetValue()
        self.temp_config["dynamic_interrupt"] = self.dyn_interrupt.GetValue()
        
        t_idx = self.trans_type.GetSelection()
        t_vals = ["disabled", "local", "online"]
        self.temp_config["translate_type"] = t_vals[t_idx]
        self.temp_config["translate_enabled"] = (t_idx != 0)
        self.temp_config["translate_from"] = self.trans_codes[self.trans_from.GetSelection()]
        self.temp_config["translate_to"] = self.trans_codes[self.trans_to.GetSelection()]
        self.temp_config["translate_service"] = self.trans_service.GetStringSelection()
        self.temp_config["translate_swap"] = self.trans_swap.GetValue()

    def on_save(self, event):
        self._update_temp_config_from_ui()
        if self.current_profile == "Global": self.full_config["global"].update(self.temp_config)
        else: self.full_config["profiles"][self.current_profile] = self.temp_config.copy()
        save_config(self.full_config); self.EndModal(wx.ID_OK)

def show_config_window(full_config, current_profile="Global", active_app="", restart_callback=None):
    dlg = ConfigWindow(None, full_config, current_profile, active_app=active_app, restart_callback=restart_callback)
    if dlg.ShowModal() == wx.ID_OK: return dlg.full_config
    return None