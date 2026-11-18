# Taller de apuntes: PDF → Markdown → LaTeX → PDF

App local (Python + navegador) para organizar el temario de varias asignaturas y rehacer los PDFs a tu gusto:

1. **Visor de PDF** con todas tus asignaturas y temas en un árbol.
2. **PDF → Markdown**: extrae el texto (títulos, negritas, listas) para recortar y limpiar.
3. **Markdown → LaTeX**: genera un `.tex` final.
4. **Editor LaTeX tipo Overleaf**: edita a la izquierda, PDF a la derecha, compila con Tectonic.
5. Imprime el PDF final.

## Requisitos
- Python 3.9+
- Conexión a internet la primera vez (descarga Tectonic y sus paquetes LaTeX)

## Uso
- Windows: doble clic en `iniciar.bat`
- Linux/macOS: `sh iniciar.sh`

La primera ejecución ejecuta `setup.py` (instala PyMuPDF y descarga Tectonic). Se abre `http://localhost:8000`.

## Tus asignaturas
La primera vez la app te pide **elegir una carpeta** (se abre el selector de Windows). Esa carpeta debe contener una carpeta por asignatura y, dentro de cada una, su temario:

```
MiCarpeta/
  Redes/
    Tema 1/   Tema 2/   ...
  Algebra/
    Tema 1/   ...
```

Luego eliges la asignatura en el desplegable de la barra lateral (el botón **+** crea una nueva). Puedes cambiar de carpeta cuando quieras con **Elegir carpeta…**. La elección se guarda en `config.json` (no se sube a git) y tus archivos nunca salen de tu carpeta.

## Limitaciones
- PDF → Markdown no reconoce bien fórmulas, tablas ni imágenes: revisa el resultado.
- El servidor solo escucha en `127.0.0.1`; no está pensado para exponerse a internet.

## Licencia
MIT

## Paquetes LaTeX y caché
Tectonic descarga los paquetes LaTeX que necesita **una sola vez** y los guarda en su caché local
(Windows: `%LOCALAPPDATA%\TectonicProject`; Linux/macOS: `~/.cache/Tectonic`). `setup.py` precarga los
habituales al instalar, así que después compilar funciona sin internet. Solo si un `.tex` usa un paquete
nuevo se descargará ese paquete la primera vez.

## PDF compilado desde LaTeX
Al compilar el LaTeX de un PDF (botón **LaTeX** de su tarjeta), el resultado se guarda dentro del propio tema, junto al
original y con su mismo nombre más ` VersionLatex`, por ejemplo `Tema 3/Parte I VersionLatex.pdf`. Aparece como una
tarjeta más (marcada «versión LaTeX») y no se vuelve a extraer.
