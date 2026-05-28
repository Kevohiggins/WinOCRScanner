# WinOCR Scanner

Un escáner OCR para pantallas, potenciado por el motor nativo de **Windows 10/11 (WinRT)**.

## ¿De qué va esto?

Este programa es la versión "minimalista" y de bajo consumo de mi otro proyecto (PaddleOCR Scanner). Mientras que el otro usa motores un poco más pesados (y mejor entrenados, debo decir ah), **WinOCR Scanner** aprovecha la tecnología que ya tenés instalada en tu Windows.

Está diseñado para ser instantáneo: captura lo que tenés en pantalla y te permite navegar el texto detectado con el teclado, simulando un "cursor virtual" sobre los elementos.

## Características Destacadas

*   **Motor Nativo:** Utiliza el reconocimiento de texto de Windows (WinRT OCR). Es muy rápido.
*   **Ahorro de recursos:** Al no cargar modelos de IA externos pesados, es ideal para computadoras con pocos recursos o para tenerlo siempre abierto de fondo.
*   **Traducción Integrada:** Soporta traducción online (Google, Bing, etc.) y **offline** (vía CTranslate2/Argos).
*   **Perfiles por Aplicación:** Guarda configuraciones específicas (recortes, idioma, sombras) para cada programa que uses.

## Descarga y Uso

1.  Descargá la última versión desde la sección de [Releases](https://github.com/Kevohiggins/WinOCRScanner/releases/latest).
2.  Extraé y ejecutá `WinOCR Scanner.exe`. Se recomienda ejecutar como administrador para asegurar que los atajos de teclado funcionen en todas las ventanas.

Para entender cómo funciona cada modo y ver todos los atajos, **leé el `manual.html`** que viene incluido en la descarga.

## Créditos y Apoyo

Quiero dejar en claro que yo no escribí el código de esto de forma manual. Todo fue programado usando IA. Mi trabajo fue idear el proyecto, guiar el desarrollo mediante prompts, testear exhaustivamente y reportar los bugs para su corrección.

Si este programa te sirvió para algo y querés invitarme una birra, podés hacerlo acá:
*   [Mercado Pago](https://link.mercadopago.com.ar/kevohiggins) (Si sos de Argentina)
*   [PayPal](https://www.paypal.com/paypalme/KevOHiggins) (Si sos de afuera)

¿Encontraste algún bug, tenés sugerencias o querés charlar? Pasate por mi [formulario de contacto](https://kevohiggins.github.io/contactame).
