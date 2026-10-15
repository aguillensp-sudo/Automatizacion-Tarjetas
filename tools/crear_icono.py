"""Genera el icono de la aplicación (tarjeta bancaria).

Crea ``recursos/tarjetas.png`` (256 px, para la ventana) y ``recursos/tarjetas.ico``
(multitamaño, para el acceso directo del escritorio). Se ejecuta una sola vez; el
icono queda versionado en el repositorio.

    python tools/crear_icono.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "recursos"


def dibujar(lado: int = 1024) -> Image.Image:
    """Tarjeta bancaria con banda, chip y estrellas de tarjeta enmascarada."""
    imagen = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(imagen)

    u = lado / 1024.0                       # unidad de escala
    # Cuerpo de la tarjeta
    caja = (60 * u, 250 * u, 964 * u, 774 * u)
    radio = 70 * u
    dibujo.rounded_rectangle(caja, radius=radio, fill=(20, 62, 122, 255))
    # Banda magnética
    dibujo.rectangle((60 * u, 340 * u, 964 * u, 430 * u), fill=(13, 39, 78, 255))
    # Franja inferior más clara
    dibujo.rounded_rectangle((60 * u, 620 * u, 964 * u, 774 * u), radius=radio,
                             fill=(28, 84, 158, 255))
    dibujo.rectangle((60 * u, 620 * u, 964 * u, 700 * u), fill=(20, 62, 122, 255))
    # Chip dorado
    dibujo.rounded_rectangle((130 * u, 480 * u, 290 * u, 600 * u), radius=18 * u,
                             fill=(233, 190, 84, 255), outline=(180, 140, 50, 255),
                             width=int(6 * u))
    for desplazamiento in (0.33, 0.66):
        x = 130 * u + (290 - 130) * u * desplazamiento
        dibujo.line((x, 480 * u, x, 600 * u), fill=(180, 140, 50, 255), width=int(5 * u))
    dibujo.line((130 * u, 540 * u, 290 * u, 540 * u), fill=(180, 140, 50, 255),
                width=int(5 * u))
    # Número de tarjeta enmascarado
    for indice in range(4):
        x = 360 * u + indice * 150 * u
        dibujo.rounded_rectangle((x, 500 * u, x + 110 * u, 560 * u), radius=20 * u,
                                 fill=(240, 244, 250, 255))
    # Marca de la red de pago (dos círculos)
    dibujo.ellipse((700 * u, 660 * u, 830 * u, 750 * u), fill=(226, 88, 74, 255))
    dibujo.ellipse((790 * u, 660 * u, 920 * u, 750 * u), fill=(240, 190, 70, 235))
    return imagen


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    imagen = dibujar(1024)
    png = DESTINO / "tarjetas.png"
    ico = DESTINO / "tarjetas.ico"
    imagen.resize((256, 256), Image.LANCZOS).save(png)
    imagen.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                            (128, 128), (256, 256)])
    print("Generados:\n  %s\n  %s" % (png, ico))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
