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
Pon tus archivos en `University/`. Al arrancar se crean `Assignment 1` … `Assignment 5`; renómbralas o crea más.
Esa carpeta **no se sube a git** (son tus apuntes).

```
University/
  Assignment 1/
    Tema 1/   Tema 2/   ...
  Assignment 2/
```

## Limitaciones
- PDF → Markdown no reconoce bien fórmulas, tablas ni imágenes: revisa el resultado.
- El servidor solo escucha en `127.0.0.1`; no está pensado para exponerse a internet.

## Licencia
MIT
