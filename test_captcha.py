"""
test_panel_detection.py
========================
Prueba la detección del panel de captcha sobre imágenes locales,
usando exactamente la misma función detect_captcha_panel del game_bot.py.

Uso:
    python test_panel_detection.py imagen.png
    python test_panel_detection.py captura1.jpg captura2.jpg ...
    python test_panel_detection.py          ← usa x.jpg por defecto

Salida por imagen:
    <nombre>_debug.jpg   → imagen original con el rectángulo verde anotado
    <nombre>_crop.jpg    → recorte del panel (lo que se manda a 2Captcha)
"""

import sys
import os
import cv2
import numpy as np
from PIL import Image


# ─────────────────────────────────────────────────────────────────────────────
#  detect_captcha_panel — copia exacta de game_bot.py
# ─────────────────────────────────────────────────────────────────────────────
def detect_captcha_panel(img_pil, debug_save: str = None):
    """
    Detecta el panel del captcha usando análisis de densidad de píxeles oscuros
    por fila y columna.

    El panel tiene un fondo gris oscuro uniforme (gray < 80) que ocupa >85% de
    su ancho interior. La imagen del puzzle (zona central) puede tener píxeles
    claros, por eso se usan solo las filas de los bordes del panel para la
    detección vertical, y se rellenan huecos de hasta 60px.

    Estrategia:
      1. Analizar densidad oscura por fila en la franja interior del panel
         (x = 72%-98% del ancho de imagen) donde no hay confusión con el juego.
      2. Rellenar huecos de hasta 60 filas (imagen del puzzle en el centro).
      3. Detectar límites Y del panel como primera/última fila con >85% oscuro.
      4. En ese rango Y, detectar límites X buscando columnas con >70% oscuro
         desde el 60% del ancho hacia la derecha.

    Retorna (x, y, w, h) relativo a img_pil, o None si no se detecta.
    """
    img_cv = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    h_img, w_img = img_cv.shape[:2]
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

    DARK_THR = 80
    SCAN_X0  = int(w_img * 0.60)   # explorar X desde aquí
    INNER_X0 = int(w_img * 0.72)   # franja interior para detectar filas Y
    INNER_X1 = int(w_img * 0.98)

    # ── Paso 1: densidad oscura por fila en la franja interior ───────────────
    inner_zone   = gray[:, INNER_X0:INNER_X1]
    row_dark_pct = (inner_zone < DARK_THR).sum(axis=1) / inner_zone.shape[1]

    # ── Paso 2: rellenar huecos ≤60 filas (imagen del puzzle) ────────────────
    panel_mask = (row_dark_pct > 0.85).astype(np.uint8).reshape(-1, 1)
    k_gap      = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 60))
    panel_mask = cv2.dilate(panel_mask, k_gap)
    panel_mask = cv2.erode(panel_mask, k_gap)
    panel_rows = np.where(panel_mask.flatten() > 0)[0]

    if len(panel_rows) < 30:
        print("   [CV] No se detectaron filas oscuras suficientes para el panel.")
        return None

    y0 = int(panel_rows[0])
    y1 = int(panel_rows[-1])

    # ── Paso 3: densidad oscura por columna en el rango Y detectado ──────────
    roi_y        = gray[y0:y1, SCAN_X0:]
    col_dark_pct = (roi_y < DARK_THR).sum(axis=0) / max(y1 - y0, 1)
    dark_cols    = np.where(col_dark_pct > 0.70)[0]

    if len(dark_cols) < 5:
        print("   [CV] No se detectaron columnas oscuras del panel.")
        return None

    x0 = SCAN_X0 + int(dark_cols[0])
    x1 = SCAN_X0 + int(dark_cols[-1])

    pad = 3
    rx0 = max(0, x0 - pad)
    ry0 = max(0, y0 - pad)
    rx1 = min(w_img, x1 + pad)
    ry1 = min(h_img, y1 + pad)

    result = (rx0, ry0, rx1 - rx0, ry1 - ry0)

    if debug_save:
        dbg = img_cv.copy()
        cv2.rectangle(dbg, (rx0, ry0), (rx1, ry1), (0, 255, 0), 3)
        cv2.imwrite(debug_save, dbg)
        print(f"   [CV] Debug anotado: {debug_save}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Runner
# ─────────────────────────────────────────────────────────────────────────────
def test_image(path: str):
    print(f"\n{'='*55}")
    print(f"  Imagen: {path}")
    print(f"{'='*55}")

    if not os.path.exists(path):
        print(f"[-] Archivo no encontrado: {path}")
        return

    img_pil = Image.open(path).convert("RGB")
    print(f"[*] Tamaño: {img_pil.size[0]}x{img_pil.size[1]}")

    base     = os.path.splitext(path)[0]
    dbg_path  = f"{base}_debug.jpg"
    crop_path = f"{base}_crop.jpg"

    panel = detect_captcha_panel(img_pil, debug_save=dbg_path)

    if panel is None:
        print("[-] No se detectó ningún panel.")
        return

    px, py, pw, ph = panel
    print(f"[✓] Panel detectado:")
    print(f"    x={px}  y={py}  w={pw}  h={ph}")
    print(f"    esquina inferior-derecha: ({px+pw}, {py+ph})")

    crop = img_pil.crop((px, py, px + pw, py + ph))
    crop.save(crop_path, format="JPEG", quality=95)
    print(f"[✓] Recorte guardado: {crop_path}  ({crop.size[0]}x{crop.size[1]})")


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["x.jpg"]
    for t in targets:
        test_image(t)
    print("\n[*] Listo.")