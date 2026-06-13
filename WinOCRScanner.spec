# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import glob
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# --- CONFIGURACIÓN DE RUTAS ---
VENV_SP = os.path.join(sys.prefix, 'Lib', 'site-packages')

# 1. DATOS (Archivos fijos requeridos)
datas = [
    ('src/assets', 'src/assets'), # Iconos y sonidos
]

datas += collect_data_files('winocr')
datas += collect_data_files('sentencepiece')
datas += collect_data_files('accessible_output2')

binaries = []

# CTranslate2 (Motor de Traducción Offline): 
# Copiamos manualmente sus DLLs a su carpeta interna para el empaquetado seguro
ct2_src = os.path.join(VENV_SP, 'ctranslate2')
if os.path.exists(ct2_src):
    for f in glob.glob(os.path.join(ct2_src, '*.dll')) + glob.glob(os.path.join(ct2_src, '*.pyd')):
        binaries.append((f, 'ctranslate2'))

# SentencePiece: Tokenizador
sp_dir = os.path.join(VENV_SP, 'sentencepiece')
if os.path.exists(sp_dir):
    for f in glob.glob(os.path.join(sp_dir, '*.pyd')) + glob.glob(os.path.join(sp_dir, '*.dll')):
        binaries.append((f, 'sentencepiece'))

# 2. ANÁLISIS DE CÓDIGO
a = Analysis(
    ['src/main.py'],           # Punto de entrada
    pathex=['src'],            # Buscar nuestros módulos .py
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'winocr',               # Motor OCR nativo
        'accessible_output2',   # Lector de pantalla
        'cv2',                  # OpenCV
        'translators',          # Traducción en la nube
        'ctranslate2',          # Motor offline
        'sentencepiece',        # Tokenizador
        'fitz',                 # PyMuPDF
        'docx'                  # python-docx
    ],
    runtime_hooks=['runtime_hook_ctranslate2.py'], # Inyección de DLLs al iniciar
    excludes=[
        # Excluir solo el motor OCR pesado de OpenVINO/RapidOCR
        'torch', 'scipy', 'matplotlib', 'pandas', 'tkinter', 
        'openvino', 'rapidocr_openvino'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 3. CONFIGURACIÓN DEL EJECUTABLE
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WinOCR Scanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='src/assets/icon.ico' if os.path.exists('src/assets/icon.ico') else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 4. RECOLECCIÓN
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='WinOCR Scanner',
)