# ─────────────────────────────────────────────────────────────────
#  Configuración central — todas las constantes del bot
# ─────────────────────────────────────────────────────────────────

# Proceso y ventana del juego
PROCESS_NAME      = "Game.exe"
GAME_WINDOW_TITLE = "Pirates Online - Moonlight Haven"

# ── Reconnect ────────────────────────────────────────────────────
# Coordenadas del botón "Switch" en el menú de pausa (frmSettings)
SWITCH_X,  SWITCH_Y  = 712, 562
# Botón de confirmación en frmAskChange
CONFIRM_X, CONFIRM_Y = 629, 436
# Botón "Switch" en el menú de escape (no usado en el flujo principal)
SWITCH_ACTIVATE_X, SWITCH_ACTIVATE_Y = 696, 198

# ── Selección de personaje ────────────────────────────────────────
# 1, 2 o 3
NUMERO_PERSONAJE = 1

PERSONAJE_COORDS = {
    1: (410, 469),
    2: (686, 531),
    3: (922, 565),
}
START_X, START_Y = 405, 735

# ── Muerte / Revivir ────────────────────────────────────────────
REVIVE_X, REVIVE_Y = 0, 0   # <-- reemplazar con las coordenadas reales

# Click de calibración post-reconnect: fuerza que SDL_PollEvent
# capture el windowID/which/button reales si el juego recreó su
# ventana SDL2 al reconectar.
RECONNECT_CALIBRATE_X, RECONNECT_CALIBRATE_Y = 827, 703

# ── Captcha ───────────────────────────────────────────────────────
# Tiempo máximo de espera antes de abortar (segundos)
CAPTCHA_PAUSE_TIMEOUT = 90
# Destino del drag cuando frmCaptcha bloquea un botón
CAPTCHA_DRAG_DEST_X, CAPTCHA_DRAG_DEST_Y = 50, 50


AUTOLOOT_OFFSET = 0x824328 #Offset Autoloot

AUTOLOOT_VALUE  = 65536 # Autoloot enabled

# ── Autocast ──────────────────────────────────────────────────────
TARGET_X, TARGET_Y = 754, 446

SPELL_X      = 692
SPELL_Y      = 404
SPELL_NUMBER = 1
SPELL_INTERVAL = 11.1   # segundos entre lanzamientos

# Mapeo hechizo → (scancode SDL2, sym SDL2)
SPELL_KEYS = {
    1: (58, 0x4000003A),
    2: (59, 0x4000003B),
    3: (60, 0x4000003C),
    4: (61, 0x4000003D),
}

# Tecla Escape
KEY_ESCAPE = (41, 0x0000001B)

# ═════════════════════════════════════════════════════════════════
#  TRAYECTOS / RUTAS  (modo Dofus-like)
# ═════════════════════════════════════════════════════════════════
#
#  Cada trayecto es una lista de pasos. Cada paso puede ser:
#    - {"type": "walk", "x": int, "y": int}
#         → camina a las coordenadas del mapa (usa autowalk en memoria)
#    - {"type": "spell", "x": int, "y": int, "spell": int}
#         → lanza hechizo N en coordenadas de pantalla (spell 1-4)
#    - {"type": "wait", "seconds": float}
#         → espera N segundos antes del siguiente paso
#    - {"type": "click", "x": int, "y": int}
#         → click simple en pantalla
#
#  Ejemplo: recorre 3 puntos, lanza hechizo en cada uno, espera 5s
# ═════════════════════════════════════════════════════════════════

TRAYECTOS = {
    # Trayecto 1 —
    1: [
        {"type": "walk", "x": 1445,  "y": 1536},
        {"type": "spell", "x": 378, "y": 442, "spell": 1},
        {"type": "walk", "x": 1451,  "y": 1536},
        {"type": "spell", "x": 630, "y": 403, "spell": 1},
        {"type": "walk", "x": 1464,  "y": 1536},
        {"type": "spell", "x": 673, "y": 397, "spell": 1},
    ],
    }

# Trayecto activo por defecto (1, 2, etc.)
TRAYECTO_ACTIVO = 1

# Tiempo máximo de espera para que el personaje llegue a destino (segundos)
WALK_TIMEOUT = 8.0

# Distancia mínima considerada "llegada" (en unidades de coordenadas del juego)
WALK_ARRIVE_THRESHOLD = 3.0