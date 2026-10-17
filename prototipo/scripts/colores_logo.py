"""Extrae los colores dominantes del logo y calcula su contraste (WCAG) sobre blanco y sobre negro.

Uso:  uv run python scripts/colores_logo.py ../utils/logo_fondo_transparente.png
No forma parte de la aplicación: solo sirve para elegir la paleta del diseño.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def luminancia(rgb) -> float:
    def canal(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b) -> float:
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hexa(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(v)) for v in rgb)


def kmeans(puntos: np.ndarray, k: int, iteraciones: int = 40, semilla: int = 3) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(semilla)
    centros = puntos[rng.choice(len(puntos), k, replace=False)].astype(float)
    for _ in range(iteraciones):
        etiquetas = np.argmin(((puntos[:, None, :] - centros[None]) ** 2).sum(axis=2), axis=1)
        nuevos = np.array([puntos[etiquetas == i].mean(axis=0) if (etiquetas == i).any() else centros[i]
                           for i in range(k)])
        if np.allclose(nuevos, centros, atol=0.5):
            break
        centros = nuevos
    return centros, etiquetas


def main(ruta: str, k: int = 8) -> None:
    img = Image.open(ruta).convert("RGBA")
    img.thumbnail((220, 220))
    a = np.array(img)
    opacos = a[a[:, :, 3] > 220][:, :3].astype(float)
    luz = opacos.mean(axis=1)
    opacos = opacos[luz < 235]  # fuera lo casi blanco
    centros, etiquetas = kmeans(opacos, k)
    pesos = np.bincount(etiquetas, minlength=k) / len(etiquetas)
    print(f"{len(opacos)} píxeles de color analizados\n")
    print(f"{'color':8s} {'peso':>6s}  {'sobre blanco':>12s}  {'sobre negro':>11s}")
    for i in np.argsort(-pesos):
        c = centros[i]
        print(f"{hexa(c):8s} {pesos[i]*100:5.1f}%  {contraste(c, (255, 255, 255)):12.2f}  {contraste(c, (0, 0, 0)):11.2f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent.parent.parent / "utils" /
                                                    "logo_fondo_transparente.png"))
