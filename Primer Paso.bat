@echo off
echo === Creando Entorno Virtual Hibrido .venv ===
python -m venv .venv

echo === Activando e Instalando Dependencias (WinOCR + Traduccion Offline) ===
call .venv\Scripts\activate
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install winocr wxpython mss opencv-python psutil translators pywin32 ctranslate2 sentencepiece accessible-output2 libloader

echo === Proceso Terminado. Entorno Listo! ===
pause