"""
Runtime hook para CTranslate2 y SentencePiece en PyInstaller.
"""
import os
import sys
import ctypes
import glob

if sys.platform == "win32":
    # Evitar colisión de hilos de OpenMP en librerías dinámicas
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    
    # Seteamos el límite de hilos óptimo desde el arranque
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["OPENBLAS_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    
    # CTranslate2: Pre-cargar DLLs para que Python las reconozca antes de la importación
    ct2_dir = os.path.join(base, "ctranslate2")
    if os.path.isdir(ct2_dir):
        os.add_dll_directory(ct2_dir)
        os.environ["PATH"] = ct2_dir + os.pathsep + os.environ.get("PATH", "")
        for dll_path in glob.glob(os.path.join(ct2_dir, "*.dll")):
            try:
                ctypes.CDLL(dll_path)
            except OSError:
                pass