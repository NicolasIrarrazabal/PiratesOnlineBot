import time
import threading

import keyboard

import input

# ─────────────────────────────────────────────
#  Configuración
# ─────────────────────────────────────────────
TARGET_X = 500
TARGET_Y = 300

SPELL_X        = 692
SPELL_Y        = 404
SPELL_NUMBER   = 1
SPELL_INTERVAL = 11.1

PERSONAJE_NUMERO = 1  # Número de personaje (1, 2, 3). Aún no implementado.

# Coordenadas del flujo de reconexión (ajustar según resolución)
# Temporal hasta encontrar memorias de reconexión.
SWITCH_X,  SWITCH_Y  = 712, 562
CONFIRM_X, CONFIRM_Y = 636, 435


# ─────────────────────────────────────────────
#  Detector de posición del mouse (detector.py)
# ─────────────────────────────────────────────
def start_mouse_detector():
    """
    detector.py corre su propio bucle infinito (while True) escuchando
    el numpad '*' para imprimir la posición del mouse relativa a la
    ventana del juego. Se importa recién aquí, dentro de un hilo daemon,
    para que ese bucle no bloquee el arranque de main().
    """
    def _run():
        import detector  # el import dispara el bucle de detector.py

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────
def main():
    game = input.GameInput()

    if not game.attach():
        print("[-] No se pudo conectar al juego")
        return

    print("=" * 50)
    print("CONTROLADOR DE MOUSE - Pirates Online")
    print("=" * 50)
    print("Modo: Frida / SDL2 (funciona minimizado)")
    print()
    print("Comandos:")
    print("  F4  - Iniciar/detener autocast")
    print("  F5  - Clic manual en coordenadas predefinidas")
    print("  F6  - Mostrar última posición capturada")
    print("  F7  - Reconnect (Escape → Switch → Confirm)")
    print("  F8  - Salir")
    print("  *   - (numpad) Mostrar posición actual del mouse (detector.py)")
    print()
    print("[✓] Mouse inicializado automáticamente — no hace falta click manual.")
    print("=" * 50)

    start_mouse_detector()

    # ── Estado de autocast ────────────────────────────────────────────────
    autocasting     = False
    autocast_thread = None
    stop_event      = threading.Event()

    # Se usa para "despertar" el autocast_loop apenas el bot se reanuda
    # tras un reconnect, en vez de esperar el resto del SPELL_INTERVAL.
    resume_event    = threading.Event()

    def autocast_loop():
        print(f"[*] Autocast iniciado — hechizo {SPELL_NUMBER} en ({SPELL_X},{SPELL_Y}) cada {SPELL_INTERVAL}s")
        while not stop_event.is_set():
            if game.ready:
                game.cast_spell(SPELL_NUMBER, SPELL_X, SPELL_Y)

            resume_event.clear()
            woke_early = resume_event.wait(SPELL_INTERVAL)
            if stop_event.is_set():
                break
            if woke_early:
                print("[*] Autocast retomado inmediatamente tras reconexión.")
                continue  # vuelve arriba y tira el hechizo ya, sin esperar el resto del intervalo
        print("[*] Autocast detenido")

    # ── Resume callback: se llama automáticamente cuando GameInput termina
    #    un reconnect (manual F7 o automático por captcha) ─────────────────
    def on_bot_resumed():
        if autocasting:
            resume_event.set()

    game.set_resume_callback(on_bot_resumed)

    # ── Loop principal de hotkeys ─────────────────────────────────────────
    running        = True
    f4_was_pressed = False
    f6_was_pressed = False
    f7_was_pressed = False

    while running:
        try:
            # ── F4: toggle autocast ──────────────────────────────────────
            f4_now = keyboard.is_pressed('f4')
            if f4_now and not f4_was_pressed:
                if not autocasting:
                    if not game.ready:
                        print("[!] Hacé un click manual en el juego primero")
                    else:
                        autocasting = True
                        stop_event.clear()
                        autocast_thread = threading.Thread(target=autocast_loop, daemon=True)
                        autocast_thread.start()
                        print("[*] Autocast ACTIVADO")
                else:
                    autocasting = False
                    stop_event.set()
                    resume_event.set()  # libera el wait() para que el loop salga al instante
                    print("[*] Autocast DESACTIVADO")
            f4_was_pressed = f4_now

            # ── F5: click manual ─────────────────────────────────────────
            if keyboard.is_pressed('f5'):
                if not game.ready:
                    print("[!] Hacé un click manual en el juego primero")
                else:
                    print(f"\n[F5] Clic en ({TARGET_X}, {TARGET_Y})")
                    game.click_at(TARGET_X, TARGET_Y)
                time.sleep(0.3)

            # ── F6: mostrar última posición capturada ────────────────────
            f6_now = keyboard.is_pressed('f6')
            if f6_now and not f6_was_pressed:
                pos = game._last_captured  # acceso directo al atributo interno
                if pos:
                    print(f"\n[F6] Posición capturada: X={pos[0]}, Y={pos[1]}")
                    print(f"     → game.click_at({pos[0]}, {pos[1]})")
                    print(f"     → game.cast_spell(1, {pos[0]}, {pos[1]})")
                else:
                    print("\n[F6] Aún no se capturó ningún click.")
            f6_was_pressed = f6_now

            # ── F7: reconnect ────────────────────────────────────────────
            f7_now = keyboard.is_pressed('f7')
            if f7_now and not f7_was_pressed:
                print("\n[F7] Reconnect disparado.")
                game.reconnect(SWITCH_X, SWITCH_Y, CONFIRM_X, CONFIRM_Y)
            f7_was_pressed = f7_now

            # ── F8: salir ────────────────────────────────────────────────
            if keyboard.is_pressed('f8'):
                print("\n[*] Saliendo...")
                stop_event.set()
                resume_event.set()
                running = False

            time.sleep(0.01)

        except Exception as e:
            print(f"[-] Error: {e}")
            break

    game.close()
    print("[+] Programa terminado")


if __name__ == "__main__":
    main()