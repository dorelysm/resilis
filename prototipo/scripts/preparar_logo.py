"""Prepara las imágenes del logo para la web, a partir de los originales de la carpeta utils/.

- Del PNG con fondo transparente salen el emblema de la barra (sin el texto del lema), el emblema grande de la
  página de inicio y el icono de la pestaña.
- Del JPEG con fondo blanco sale el icono para pantallas de inicio de celulares, que necesita fondo sólido.

Se recorta solo el emblema: el texto "Inteligencia que conecta, innovación que salva vidas" no aparece en el sistema.
Uso:  uv run python scripts/preparar_logo.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
ORIGINALES = RAIZ.parent / "utils"
SALIDA = RAIZ / "app" / "static" / "img"


def _filas_vacias(mascara: np.ndarray) -> list[tuple[int, int]]:
    contenido = mascara.sum(axis=1)
    rangos, inicio = [], None
    for y, n in enumerate(contenido):
        if n == 0 and inicio is None:
            inicio = y
        elif n > 0 and inicio is not None:
            rangos.append((inicio, y - 1))
            inicio = None
    if inicio is not None:
        rangos.append((inicio, len(contenido) - 1))
    return rangos


def recortar_emblema(img: Image.Image, mascara: np.ndarray) -> Image.Image:
    """Se queda con el dibujo: desde donde empieza hasta el primer hueco grande (el que lo separa del lema)."""
    alto = mascara.shape[0]
    huecos = [h for h in _filas_vacias(mascara) if h[0] > 0 and h[1] - h[0] >= 6]
    primera = next((y for y, n in enumerate(mascara.sum(axis=1)) if n > 0), 0)
    corte = next((h[0] for h in huecos if h[0] > alto * 0.5), alto)
    emblema = img.crop((0, primera, img.width, corte))
    sub = mascara[primera:corte]
    cols = np.where(sub.sum(axis=0) > 0)[0]
    return emblema.crop((cols.min(), 0, cols.max() + 1, emblema.height))


def a_cuadrado(img: Image.Image, lado: int, fondo=(0, 0, 0, 0), relleno: float = 0.0) -> Image.Image:
    util = int(lado * (1 - relleno))
    copia = img.copy()
    copia.thumbnail((util, util), Image.LANCZOS)
    lienzo = Image.new("RGBA", (lado, lado), fondo)
    lienzo.paste(copia, ((lado - copia.width) // 2, (lado - copia.height) // 2), copia)
    return lienzo


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)

    # ---- desde el PNG transparente
    png = Image.open(ORIGINALES / "logo_fondo_transparente.png").convert("RGBA")
    emblema = recortar_emblema(png, np.array(png)[:, :, 3] > 20)
    print("emblema (transparente):", emblema.size)

    barra = emblema.copy()
    barra.thumbnail((400, 96), Image.LANCZOS)  # se muestra a 48 px de alto; el doble para pantallas nítidas
    barra.save(SALIDA / "emblema-barra.webp", quality=88, method=6)
    grande = emblema.copy()
    grande.thumbnail((360, 360), Image.LANCZOS)
    grande.save(SALIDA / "emblema-grande.webp", quality=88, method=6)
    pequeno = emblema.copy()
    pequeno.thumbnail((140, 140), Image.LANCZOS)
    pequeno.save(SALIDA / "emblema-ficha.png", optimize=True)  # para imprimir: PNG, sin depender del WebP

    a_cuadrado(emblema, 32, relleno=0.04).save(SALIDA / "favicon-32.png", optimize=True)
    a_cuadrado(emblema, 192, relleno=0.06).save(SALIDA / "icono-192.png", optimize=True)
    iconos = [a_cuadrado(emblema, t, relleno=0.04) for t in (16, 32, 48)]
    iconos[0].save(SALIDA / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=iconos[1:])

    # ---- desde el JPEG con fondo blanco (icono con fondo sólido para el celular)
    jpg = Image.open(ORIGINALES / "logo_fondo_blanco.jpeg").convert("RGB")
    sobre_blanco = np.array(jpg).min(axis=2) < 235  # lo que no es casi blanco
    emblema_jpg = recortar_emblema(jpg.convert("RGBA"), sobre_blanco)
    print("emblema (fondo blanco):", emblema_jpg.size)
    base = a_cuadrado(emblema_jpg, 180, fondo=(255, 255, 255, 255), relleno=0.14)
    base.convert("RGB").save(SALIDA / "apple-touch-icon.png", optimize=True)

    for archivo in sorted(SALIDA.iterdir()):
        print(f"{archivo.name:24s} {archivo.stat().st_size / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
