import logging
import winsound
import threading
import os
import sys

logger = logging.getLogger(__name__)


class TTSEngine:
    """
    Abstracción de salida de voz con cadena de fallback y soporte para earcons (sonidos).
    """

    def __init__(self):
        self._ao2_output = None
        self._sapi_voice = None
        self._init_assets()
        self._init_accessible_output2()
        if self._ao2_output is None:
            self._init_sapi()

    def _init_assets(self):
        """Calcula la ruta de los sonidos, manejando el empaquetado de PyInstaller."""
        if getattr(sys, 'frozen', False):
            # Si es un ejecutable (PyInstaller)
            base_path = sys._MEIPASS
        else:
            # Si es el script de desarrollo
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        self.sounds_path = os.path.join(base_path, "src", "assets", "sounds")
        logger.info("TTS: Ruta de sonidos configurada en %s", self.sounds_path)

    def _play_file(self, filename):
        """Reproduce un archivo WAV de la carpeta de assets."""
        def _play():
            path = os.path.join(self.sounds_path, filename)
            if os.path.exists(path):
                try:
                    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                except Exception as e:
                    logger.error("Error al reproducir sonido %s: %s", filename, e)
            else:
                logger.warning("Sonido no encontrado: %s", path)
        
        threading.Thread(target=_play, daemon=True).start()

    def play_startup(self):
        """Sonido de bienvenida al iniciar el programa."""
        self._play_file("startup.wav")

    def play_shutdown(self):
        """Sonido de despedida al cerrar el programa."""
        self._play_file("shutdown.wav")

    def play_scan_start(self):
        """Sonido sutil de inicio de escaneo."""
        self._play_file("scan_start.wav")

    def play_scan_success(self):
        """Sonido de éxito."""
        self._play_file("scan_success.wav")

    def play_error(self):
        """Sonido de error."""
        self._play_file("error.wav")

    def _init_accessible_output2(self):
        """Intenta inicializar accessible_output2 para hablar directo al lector de pantalla."""
        try:
            from accessible_output2.outputs.auto import Auto
            self._ao2_output = Auto()
            logger.info("TTS: accessible_output2 inicializado (lector de pantalla detectado)")
        except Exception as e:
            logger.warning("TTS: accessible_output2 no disponible (%s), usando fallback SAPI5", e)

    def _init_sapi(self):
        """Fallback: SAPI5 via COM (siempre disponible en Windows)."""
        try:
            import win32com.client
            self._sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
            logger.info("TTS: SAPI5 inicializado como fallback")
        except Exception as e:
            logger.error("TTS: No se pudo inicializar SAPI5: %s", e)

    def speak(self, text: str, interrupt: bool = True):
        """
        Habla el texto dado.
        Si interrupt=True, corta cualquier speech anterior antes de hablar.
        """
        if not text:
            return

        # Intentar accessible_output2 primero
        if self._ao2_output is not None:
            try:
                self._ao2_output.output(text, interrupt=interrupt)
                return
            except Exception as e:
                logger.warning("TTS: Error en accessible_output2: %s, probando SAPI5", e)

        # Fallback SAPI5
        if self._sapi_voice is not None:
            try:
                # Flags: 1 = SVSFlagsAsync, 2 = SVSFPurgeBeforeSpeak
                flags = 3 if interrupt else 1
                self._sapi_voice.Speak(text, flags)
                return
            except Exception as e:
                logger.error("TTS: Error en SAPI5: %s", e)

        # Si todo falla, al menos mostrar en consola
        print(f"[TTS] {text}")

    def stop(self):
        """Detiene cualquier speech en curso."""
        if self._ao2_output is not None:
            try:
                self._ao2_output.output("", interrupt=True)
            except Exception:
                pass
        if self._sapi_voice is not None:
            try:
                self._sapi_voice.Speak("", 3)
            except Exception:
                pass
