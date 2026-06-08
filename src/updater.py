import urllib.request
import json
import os
import sys
import threading
import wx
import subprocess
from config import VERSION

REPO = "kevohiggins/WinOCRScanner"

def check_updates_async(parent, silent=False):
    def run():
        url = f"https://api.github.com/repos/{REPO}/releases/latest"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'WinOCRScanner-Updater'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                latest_tag = "".join([c for c in data.get("tag_name", "") if c.isdigit() or c == '.'])
                
                def parse_version(v):
                    parts = [int(x) for x in v.split('.') if x.isdigit()]
                    while len(parts) < 3:
                        parts.append(0)
                    return parts
                
                if parse_version(latest_tag) > parse_version(VERSION):
                    wx.CallAfter(show_update_dialog, parent, data)
                elif not silent:
                    wx.CallAfter(wx.MessageBox, f"Estás en la versión más reciente ({VERSION}).", "Actualizador")
        except Exception as e:
            if not silent:
                wx.CallAfter(wx.MessageBox, f"Error al buscar actualizaciones: {e}", "Error")
            
    threading.Thread(target=run, daemon=True).start()

def show_update_dialog(parent, data):
    tag = data.get("tag_name")
    body = data.get("body", "No hay descripción.")
    msg = f"¡Hay una nueva versión disponible: {tag}!\n\nCambios:\n{body}\n\n¿Deseas actualizar ahora?"
    
    if wx.MessageBox(msg, "Actualización Disponible", wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
        download_update(parent, data)

def download_update(parent, data):
    assets = data.get("assets", [])
    url = None
    for asset in assets:
        if asset.get("name", "").endswith("_Update.zip"):
            url = asset.get("browser_download_url")
            break
            
    if not url:
        wx.MessageBox("No se encontró el archivo de actualización (_Update.zip) en el lanzamiento.", "Error")
        return
        
    prog = wx.ProgressDialog("Descargando", "Descargando actualización...", parent=parent, style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
    
    def run():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'WinOCRScanner-Updater'})
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 8192
                
                from config import get_base_path
                base_path = get_base_path()
                zip_path = os.path.join(base_path, "update.zip")
                
                last_percent = -1
                with open(zip_path, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            if percent > last_percent:
                                last_percent = percent
                                wx.CallAfter(prog.Update, percent, f"Descargando: {percent}%")
                                
                wx.CallAfter(prog.Destroy)
                wx.CallAfter(apply_update, base_path, zip_path)
        except Exception as e:
            wx.CallAfter(prog.Destroy)
            wx.CallAfter(wx.MessageBox, f"Error al descargar: {e}", "Error")
            
    threading.Thread(target=run, daemon=True).start()

def apply_update(base_path, zip_path):
    import zipfile
    tmp_dir = os.path.join(base_path, "update_tmp")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmp_dir)
            
        items = os.listdir(tmp_dir)
        source_dir = tmp_dir
        if len(items) == 1 and os.path.isdir(os.path.join(tmp_dir, items[0])):
            source_dir = os.path.join(tmp_dir, items[0])
            
        bat_path = os.path.join(base_path, "apply_update.bat")
        exe_name = "WinOCR Scanner.exe"
        
        bat_content = f"""@echo off
chcp 65001 > nul
set "EXE_NAME={exe_name}"

:wait_loop
tasklist /FI "IMAGENAME eq %EXE_NAME%" 2>NUL | find /I "%EXE_NAME%" >nul
if %errorlevel% equ 0 (
    timeout /t 1 /nobreak > nul
    goto :wait_loop
)
timeout /t 2 /nobreak > nul

robocopy "{source_dir}" "{base_path}" /E /MOVE /IS /IT /R:5 /W:1 > nul

rmdir /s /q "{tmp_dir}" > nul 2>&1
del "{zip_path}" > nul 2>&1

start "" "{os.path.join(base_path, exe_name)}"
del "%~f0"
"""
        
        with open(bat_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)
            
        subprocess.Popen([bat_path], shell=True)
        wx.CallAfter(wx.GetApp().ExitMainLoop)
    except Exception as e:
        wx.MessageBox(f"Error al aplicar la actualización: {e}", "Error")