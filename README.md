# Taller de apuntes: PDF → texto → Markdown → LaTeX → PDF

Aplicación **local** (Python + navegador) para trabajar con el temario de tus asignaturas. Coges los PDF de clase
(diapositivas, sobre todo), la app extrae su texto e imágenes sola, te deja ver el resultado como texto, Markdown y
LaTeX, edita y compila el LaTeX con un editor al estilo Overleaf, y te deja un PDF limpio, listo para imprimir.

Todo funciona en tu ordenador: tus PDF nunca se suben a ningún sitio.

```
PDF de clase ──► texto.txt ──► texto.md ──► texto.tex ──► "<nombre> VersionLatex.pdf"
 (visor)        (se extrae solo)  (recortar)   (editar y compilar)      (imprimir)
```

## Contenido

- [Qué hace](#qué-hace)
- [Instalación y arranque](#instalación-y-arranque)
- [Cómo se usa](#cómo-se-usa)
- [Qué se genera y dónde](#qué-se-genera-y-dónde)
- [El LaTeX que sale](#el-latex-que-sale)
- [Casos especiales que resuelve](#casos-especiales-que-resuelve)
- [Limitaciones](#limitaciones)
- [Problemas frecuentes](#problemas-frecuentes)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Privacidad y seguridad](#privacidad-y-seguridad)
- [Licencia](#licencia)

## Qué hace

- **Varias asignaturas a la vez.** Eliges una carpeta con una subcarpeta por asignatura (y dentro, su temario) y la
  app las muestra todas en un árbol de tarjetas. Si cambias archivos desde el Explorador (crear, renombrar, borrar),
  la lista se actualiza sola en un par de segundos.
- **Extracción automática y sin repetir trabajo.** En segundo plano extrae texto e imágenes de cada PDF nuevo (hasta 4
  a la vez). Los que ya estaban hechos no se tocan.
- **Cuatro vistas por PDF:** PDF original, Texto, Markdown y LaTeX, más un quinto botón **PDF LaTeX** cuando ya has
  compilado su versión.
- **Taller LaTeX tipo Overleaf:** editor a la izquierda, PDF a la derecha, compilación con
  [Tectonic](https://tectonic-typesetting.github.io) (sin instalar TeX Live ni MiKTeX), compilación automática
  opcional, registro de errores resumido y conversiones entre PDF, Markdown y LaTeX.
- **Contador de caracteres** (📊) que compara el PDF original con el texto, el Markdown y el LaTeX extraídos.
- **ZIP con todos tus PDF de LaTeX** (⬇ ZIP) para llevártelos o imprimirlos de una vez.
- Renombrar PDF en línea, buscador en todas las asignaturas, barra lateral fija y redimensionable.

## Instalación y arranque

**Requisitos**

- Python 3.9 o superior (con `tkinter`, que viene incluido en Windows y macOS; en Linux: `sudo apt install python3-tk`).
- Conexión a internet **solo la primera vez** (descarga PyMuPDF, Tectonic y los paquetes LaTeX habituales).
- Un navegador moderno (Edge, Chrome, Firefox).

**Arrancar**

| Sistema | Cómo |
|---|---|
| Windows | doble clic en `iniciar.bat` |
| Linux / macOS | `sh iniciar.sh` |
| A mano | `pip install -r requirements.txt`, `python setup.py` y `python servidor.py` |

La primera vez se ejecuta `setup.py`, que instala **PyMuPDF**, descarga **Tectonic** en `_herramientas/` y precarga los
paquetes LaTeX más usados. Después se abre `http://localhost:8000`.

> Está pensada y probada en **Windows**. En Linux y macOS debería funcionar, pero no se ha probado.

## Cómo se usa

### 1. Elige tu carpeta

La primera vez la barra lateral te pide una carpeta (se abre el selector de carpetas del sistema). Esa carpeta debe
tener **una carpeta por asignatura** y, dentro, su temario:

```
MisApuntes/
├── Redes/
│   ├── Tema 1/   2526_tema1_parte1.pdf
│   └── Tema 2/   ...
└── Algebra/
    └── Tema 1/   ...
```

Puedes cambiarla cuando quieras con **Elegir carpeta…**. La elección se guarda en `config.json` (no se sube a git).
El botón **+** crea una asignatura nueva.

### 2. Mira tus PDF

Cada PDF es una **tarjeta**. Mientras la app lo extrae, la tarjeta pone «pendiente»; al terminar, «texto listo».

| Botón | Qué muestra |
|---|---|
| **PDF** | El PDF original en el visor |
| **Texto** | `texto.txt` limpio y legible |
| **Markdown** | `texto.md` maquetado como documento, con las imágenes en su sitio |
| **LaTeX** | `texto.tex` en el Taller, listo para editar y compilar |
| **PDF LaTeX** | Aparece cuando ya has compilado el LaTeX: el PDF resultante |

Iconos de la tarjeta: **✎** renombrar (se edita en la propia tarjeta), **↻** rehacer la extracción, **📊** contar caracteres.

### 3. Edita y compila el LaTeX

El botón **LaTeX** abre el **Taller**: el panel de tarjetas de la izquierda sigue visible y el editor ocupa el resto.

- **Guardar** `Ctrl+S` · **Compilar** `Ctrl+Enter` · casilla **Compilar automáticamente** (2 s después de dejar de escribir).
- Si el PDF ya estaba compilado y el `.tex` no ha cambiado, **no se recompila**: se muestra el guardado.
- Si hay un error, aparece un panel con el motivo resumido y el registro completo.
- Menú **Convertir**:
  - *PDF → Markdown*: convierte el PDF abierto en el visor en un `.md` junto a él.
  - *Markdown → LaTeX*: genera el `.tex` final de un `.md`.
  - *Regenerar con el estilo de apuntes*: rehace un `texto.tex` desde su Markdown con la plantilla actual
    (la versión anterior se guarda en `anterior/`).
- **Descargar** e **Imprimir** abren el PDF ya publicado en su tema.

### 4. Imprime o comparte

Al compilar, el PDF se guarda en el propio tema con el nombre del original más ` VersionLatex`
(`Tema 3/Parte I VersionLatex.pdf`). El botón **⬇ ZIP** de la cabecera «Asignaturas» descarga todos los que tengas,
con su estructura de carpetas.

## Qué se genera y dónde

Junto a cada PDF se crea una carpeta `<nombre>_extraido/` (la app la ignora en el árbol):

```
Tema 3/
├── Parte I.pdf                      ← tu PDF original (no se modifica nunca)
├── Parte I VersionLatex.pdf         ← el PDF compilado desde LaTeX (lo que imprimes)
└── Parte I_extraido/
    ├── texto.txt                    texto limpio
    ├── texto.md                     Markdown (con las imágenes)
    ├── texto.tex                    LaTeX con el estilo de apuntes
    ├── texto.pdf                    PDF de trabajo del Taller
    ├── imagenes/                    imágenes extraídas y páginas como imagen
    ├── anterior/                    copia de lo que había antes de rehacer a mano
    └── .fuente.json                 registro interno (tamaño, fecha y huella del PDF)
```

**Cómo evita repetir trabajo.** Cada extracción guarda el tamaño, la fecha y una huella SHA-1 del PDF:

- sin cambios → no se hace nada;
- cambió solo la fecha (copiado, movido) pero el contenido es el mismo → tampoco;
- **renombras el PDF** → se renombra su carpeta, sin volver a extraer;
- el PDF cambió de verdad → se vuelve a extraer;
- las extracciones antiguas **no se rehacen** aunque actualices el programa; solo con **↻**, y entonces lo que habías
  editado se copia a `anterior/`.

Al arrancar, la app solo detecta los PDF nuevos o modificados; revisar una carpeta ya extraída tarda milésimas.

## El LaTeX que sale

El `texto.tex` usa una plantilla de apuntes: cabecera con la sección actual, índice, numeración, la diapositiva de
origen en el margen (`diap. 8`), figuras centradas, listados de código con color y cajas para ejercicios. La conversión
aplica estas reglas:

- **Estructura:** las diapositivas «separador» pasan a ser secciones; las series «Título (I)», «(II)», «(III)» se unen
  en un solo apartado (`\diapo{15--17}`); se quitan diapositivas vacías y las de índice; si los títulos traen
  numeración propia («1.5.1.»), se usa para los niveles y LaTeX numera (con el prefijo del tema).
- **Código:** se detecta por su fuente monoespaciada, conserva sangrías y saltos de línea, y se resalta como HTTP, JSON,
  HTML o Java cuando lo reconoce.
- **Limpieza:** se descartan números de pie de página y pies repetidos; las URL pasan a `\url{}`; las comillas, a
  `\enquote{}`; las viñetas de Wingdings, a listas; los subtítulos en negrita, a `\paragraph{}`.
- **Imágenes:** se descartan logos y adornos repetidos; 3 o más imágenes de una diapositiva van en cuadrícula.
- **Ejercicios:** las diapositivas cuyo título empieza por «Ejercicio» van dentro de una caja.
- Funciona con **Tectonic (XeTeX)** y con pdfLaTeX (la plantilla elige las fuentes según el motor).

**Sigue siendo trabajo manual:** tablas, cajas de definición, rehacer diagramas, unir diapositivas en apartados lógicos
por tema, corregir erratas del temario y reescribir frases.

## Casos especiales que resuelve

- **PDF con la fuente rota.** Algunos PDF guardan las letras con otra codificación y el texto sale como
  «TOk6k‘kGk» en vez de «Protocolo». La app lo detecta y, en esas páginas, muestra **la diapositiva como imagen** con
  una nota; la tarjeta lo indica («N págs. como imagen»).
- **Antivirus.** Windows Defender puede marcar como virus un `texto.txt` que contenga código de ataques de ejemplo. La
  app localiza el fragmento exacto, lo sustituye por un aviso, muestra esa página como imagen y no entra en bucle.
- **Errores de extracción.** Un PDF dañado, protegido o a medio copiar no bloquea al resto: aparece en un aviso con su
  nombre, su ruta, el motivo y un botón **Reintentar**.

## Limitaciones

- No hay **OCR**: solo se extrae el texto que el PDF ya trae. Un PDF escaneado saldrá sin texto.
- Las **fórmulas**, **tablas** y **diagramas** no se reconocen como tales (las tablas salen como texto).
- En diapositivas con varias columnas muy mezcladas, el orden del texto puede no ser perfecto.
- Las cifras de «Letras y dígitos» del contador son aproximadas para Markdown y LaTeX, porque se descuentan las marcas
  de formato.
- Solo está probada en Windows.

## Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| «El servidor en marcha es una versión antigua» o un error `Unexpected token '<'` | Cierra la ventana de `iniciar.bat`, ábrela de nuevo y recarga la página |
| La primera compilación tarda mucho | Está descargando paquetes LaTeX una sola vez; después se usa la caché local |
| Compilar falla sin internet | Un paquete nuevo necesita descargarse una vez; los habituales ya están en la caché |
| El botón PDF → Markdown da error | Abre antes un PDF en el visor: convierte el que esté abierto |
| `py -3` abre una versión de Python distinta | Ejecuta `python setup.py` con el Python que quieras usar |
| El puerto 8000 está ocupado | Cierra la otra instancia de la app (otra ventana de `iniciar.bat`) |
| Defender bloquea o borra archivos de `_extraido` | Es un falso positivo; la app lo gestiona. Puedes permitirlo en *Seguridad de Windows → Historial de protección* |

La caché de paquetes LaTeX está en `%LOCALAPPDATA%\TectonicProject` (Windows) o `~/.cache/Tectonic` (Linux/macOS).

## Estructura del proyecto

| Archivo | Para qué sirve |
|---|---|
| `servidor.py` | Servidor local (puerto 8000), API y archivos estáticos |
| `extractor.py` | Extracción en segundo plano, en paralelo y sin repetir trabajo; estadísticas de texto |
| `limpieza.py` | Convierte el texto del PDF en texto y Markdown limpios (filas, viñetas, código, fuentes rotas) |
| `latex_api.py` | Markdown → LaTeX con el estilo de apuntes, compilación con Tectonic, PDF publicado |
| `config.py` | Carpeta elegida y selector de carpetas del sistema |
| `setup.py` | Instala PyMuPDF y Tectonic y precarga los paquetes LaTeX |
| `index.html` | Interfaz principal: árbol de tarjetas, visores y avisos |
| `lab.js`, `lab.css` | El Taller LaTeX (editor, compilación, menú Convertir) |
| `ui.js` | Ventanas modales propias (sustituyen a `alert`, `confirm` y `prompt`) |
| `iniciar.bat`, `iniciar.sh` | Arranque con instalación automática en la primera ejecución |

No hay *build*: el frontend es HTML/CSS/JavaScript sin dependencias, salvo [`marked`](https://marked.js.org), que se
carga desde internet para dibujar el Markdown en el Taller.

## Privacidad y seguridad

- El servidor escucha **solo en `127.0.0.1`**; no está pensado para exponerse a internet.
- Solo puede leer y escribir **dentro de la carpeta que elegiste**; las rutas que salen de ella se rechazan.
- Tus PDF y apuntes no salen del equipo. Lo único que se descarga de internet es: PyMuPDF (pip), Tectonic y sus
  paquetes LaTeX (GitHub y el servidor de paquetes de Tectonic), y `marked` (CDN) para el Markdown del Taller.
- `config.json`, `_herramientas/` y las carpetas `*_extraido/` están en `.gitignore`: tus datos no acaban en el repo.

## Licencia

[MIT](LICENSE)
