# Recetas de prompts para recorte (quitar fondo)

Optimizadas para removedores modernos open-source (BiRefNet, RMBG-2.0, rembg/isnet).
Reemplazá `[SUJETO]` y `[FONDO]`. El fondo se elige para **contrastar** con el sujeto
(gris neutro por defecto; mas oscuro si el sujeto es claro, mas claro si es oscuro).

**Restricciones compartidas (la clave del recorte limpio):**
`centered, entire subject in frame with margin, isolated on a solid flat [FONDO] background,
even soft diffused lighting, no cast shadow, no reflection, no gradient, sharp focus,
clean crisp edges, high detail`

---

## 1. recorte-foto — objeto fotográfico realista
Para pegar sobre otras fotos reales.

```
[SUJETO], photorealistic studio product shot, front or three-quarter view,
centered, entire subject in frame with margin, isolated on a solid flat [FONDO] background,
even soft diffused lighting, no cast shadow, no reflection, no gradient,
sharp focus, clean crisp edges, high detail, no text, no logos, no hands, 4K
```

## 2. sticker-ilustrado — estilo calcomanía
Colores planos, contorno definido. Para stickers de chat/redes.

```
[SUJETO], die-cut sticker illustration, bold clean outline, flat vibrant colors,
soft cel shading, centered, entire subject in frame with margin,
on a solid flat [FONDO] background, no drop shadow, no white border, crisp clean edges,
high detail, no text
```

## 3. vector-icono — plano / minimalista
Icono geométrico, colores sólidos.

```
[SUJETO], minimal flat vector icon, simple geometric shapes, solid colors, no gradient,
centered on a solid flat [FONDO] background, no shadow, clean edges, high detail, no text
```

---

**Notas**
- Aspecto cuadrado (x1) por defecto — ideal para stickers/elementos.
- Descarga 1K por defecto; para más resolución: `FLOW_IMAGE_QUALITY=2K make t2ih ...`.
- Cada generación concreta se guarda como `prompts/<sujeto>-<estilo>.json` (biblioteca).
- Si un sujeto tiene partes muy claras y muy oscuras, gris medio (#9a9a9a) suele ser el fondo mas seguro.
