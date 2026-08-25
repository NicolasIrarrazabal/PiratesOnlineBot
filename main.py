import time
import threading

import keyboard

import config
from game_input import GameInput, capture_window_full


def start_mouse_detector():
    """Lanza detector.py en un hilo daemon para no bloquear el arranque."""
    def _run():
        import detector
    threading.Thread(target=_run, daemon=True).start()


def _ts() -> str:
    return time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"


def main():
    game = GameInput()
    if not game.attach():
        print("[-] No se pudo conectar al juego.")
        return

    print("=" * 55)
    print("  Pirates Online — Bot de autocast + TRAYECTOS")
    print("=" * 55)
    print("  F4   — Iniciar/detener autocast")
    print("  F5   — Click manual en TARGET")
    print("  F6   — Mostrar última posición capturada")
    print("  F7   — Reconnect manual")
    print("  F8   — Salir")
    print("  ─────────────────────────────────────────────────")
    print("  F9   — Iniciar/detener TRAYECTO (una vez)")
    print("  F10  — Iniciar/detener TRAYECTO (bucle infinito)")
    print("  F11  — Cambiar trayecto activo")
    print("  *    — (numpad) Posición actual del mouse")
    print("=" * 55)

    start_mouse_detector()

    # ── Estado de autocast ─────────────────────────────────────────────────
    autocasting     = False
    autocast_thread = None
    stop_event      = threading.Event()
    resume_event    = threading.Event()

    # ── Estado de trayectos ────────────────────────────────────────────────
    trayecto_running     = False
    trayecto_thread      = None
    trayecto_stop_event  = threading.Event()
    trayecto_loop_mode   = False
    trayecto_activo_id = config.TRAYECTO_ACTIVO

    def autocast_loop():
        print(f"[*] Autocast iniciado — hechizo {config.SPELL_NUMBER} "
              f"en ({config.SPELL_X},{config.SPELL_Y}) cada {config.SPELL_INTERVAL}s")
        last_cast = None

        while not stop_event.is_set():
            if game.ready:
                sent = game.cast_spell(config.SPELL_NUMBER, config.SPELL_X, config.SPELL_Y)
                now  = time.monotonic()
                if sent:
                    delta = f"{now - last_cast:.3f}s" if last_cast else "primer disparo"
                    print(f"[{_ts()}] ENVIADO hechizo {config.SPELL_NUMBER} | {delta}")
                    last_cast = now
                else:
                    print(f"[{_ts()}] DESCARTADO (bot pausado)")

            resume_event.clear()
            woke_early = resume_event.wait(config.SPELL_INTERVAL)
            if stop_event.is_set():
                break
            if woke_early:
                print(f"[{_ts()}] Autocast retomado inmediatamente tras reconexión.")

        print("[*] Autocast detenido.")

    def on_bot_resumed():
        """Callback: despierta el autocast_loop apenas termina un reconnect."""
        if autocasting:
            resume_event.set()

    game.set_resume_callback(on_bot_resumed)

    # ── Loop de hotkeys ────────────────────────────────────────────────────
    running = True
    prev    = {'f4': False, 'f6': False, 'f7': False,
               'f9': False, 'f10': False, 'f11': False}

    while running:
        try:
            # F4 — toggle autocast
            f4 = keyboard.is_pressed('f4')
            if f4 and not prev['f4']:
                if not autocasting:
                    if not game.ready:
                        print("[!] Hacé un click manual en el juego primero.")
                    else:
                        autocasting = True
                        stop_event.clear()
                        autocast_thread = threading.Thread(
                            target=autocast_loop, daemon=True)
                        autocast_thread.start()
                        print("[*] Autocast ACTIVADO")
                else:
                    autocasting = False
                    stop_event.set()
                    resume_event.set()
                    print("[*] Autocast DESACTIVADO")
            prev['f4'] = f4

            # F5 — click manual
            if keyboard.is_pressed('f5'):
                if not game.ready:
                    print("[!] Hacé un click manual en el juego primero.")
                else:
                    print(f"[F5] Click en ({config.TARGET_X}, {config.TARGET_Y})")
                    game.click_at(config.TARGET_X, config.TARGET_Y)
                time.sleep(0.3)

            # F6 — mostrar última posición capturada
            f6 = keyboard.is_pressed('f6')
            if f6 and not prev['f6']:
                pos = game._last_captured
                if pos:
                    print(f"[F6] Última posición: ({pos[0]}, {pos[1]})")
                else:
                    print("[F6] Ningún click capturado aún.")
            prev['f6'] = f6

            # F7 — reconnect manual
            f7 = keyboard.is_pressed('f7')
            if f7 and not prev['f7']:
                print("[F7] Reconnect manual.")
                game.reconnect(config.SWITCH_X, config.SWITCH_Y,
                               config.CONFIRM_X, config.CONFIRM_Y)
            prev['f7'] = f7

            # ═══════════════════════════════════════════════════════════════
            #  TRAYECTOS
            # ═══════════════════════════════════════════════════════════════

            # F9 — trayecto una vez
            f9 = keyboard.is_pressed('f9')
            if f9 and not prev['f9']:
                if not trayecto_running:
                    trayecto = config.TRAYECTOS.get(trayecto_activo_id)
                    if not trayecto:
                        print(f"[!] Trayecto {trayecto_activo_id} no existe.")
                    elif not game.ready:
                        print("[!] Hacé un click manual en el juego primero.")
                    else:
                        # ── DEBUG: posición actual y destino antes de arrancar ──
                        pos = game.get_position()
                        first_walk = next((s for s in trayecto if s.get('type') == 'walk'), None)
                        print("\n   ╔══════════════════════════════════════════════════╗")
                        print("   ║  [DEBUG] INICIANDO TRAYECTO                     ║")
                        print("   ╠══════════════════════════════════════════════════╣")
                        if pos:
                            print(f"   ║  Posición actual:  ({pos['x']}, {pos['y']})              ║")
                        else:
                            print(f"   ║  Posición actual:  (desconocida)                 ║")
                        if first_walk:
                            print(f"   ║  Primer destino:   ({first_walk['x']}, {first_walk['y']})              ║")
                        else:
                            print(f"   ║  Primer destino:  (no hay paso 'walk')           ║")
                        print("   ╚══════════════════════════════════════════════════╝\n")

                        trayecto_running = True
                        trayecto_loop_mode = False
                        trayecto_stop_event.clear()
                        trayecto_thread = threading.Thread(
                            target=game.run_trayecto,
                            args=(trayecto, trayecto_stop_event, False),
                            daemon=True)
                        trayecto_thread.start()
                        print(f"[*] TRAYECTO {trayecto_activo_id} ACTIVADO (una vez)")
                else:
                    trayecto_running = False
                    trayecto_stop_event.set()
                    print("[*] TRAYECTO DETENIDO")
            prev['f9'] = f9

            # F10 — trayecto en bucle
            f10 = keyboard.is_pressed('f10')
            if f10 and not prev['f10']:
                if not trayecto_running:
                    trayecto = config.TRAYECTOS.get(trayecto_activo_id)
                    if not trayecto:
                        print(f"[!] Trayecto {trayecto_activo_id} no existe.")
                    elif not game.ready:
                        print("[!] Hacé un click manual en el juego primero.")
                    else:
                        # ── DEBUG: posición actual y destino antes de arrancar ──
                        pos = game.get_position()
                        first_walk = next((s for s in trayecto if s.get('type') == 'walk'), None)
                        print("\n   ╔══════════════════════════════════════════════════╗")
                        print("   ║  [DEBUG] INICIANDO TRAYECTO (BUCLE)             ║")
                        print("   ╠══════════════════════════════════════════════════╣")
                        if pos:
                            print(f"   ║  Posición actual:  ({pos['x']}, {pos['y']})              ║")
                        else:
                            print(f"   ║  Posición actual:  (desconocida)                 ║")
                        if first_walk:
                            print(f"   ║  Primer destino:   ({first_walk['x']}, {first_walk['y']})              ║")
                        else:
                            print(f"   ║  Primer destino:  (no hay paso 'walk')           ║")
                        print("   ╚══════════════════════════════════════════════════╝\n")

                        trayecto_running = True
                        trayecto_loop_mode = True
                        trayecto_stop_event.clear()
                        trayecto_thread = threading.Thread(
                            target=game.run_trayecto,
                            args=(trayecto, trayecto_stop_event, True),
                            daemon=True)
                        trayecto_thread.start()
                        print(f"[*] TRAYECTO {trayecto_activo_id} ACTIVADO (bucle)")
                else:
                    trayecto_running = False
                    trayecto_stop_event.set()
                    print("[*] TRAYECTO DETENIDO")
            prev['f10'] = f10

            # F11 — cambiar trayecto activo
            f11 = keyboard.is_pressed('f11')
            if f11 and not prev['f11']:
                ids = sorted(config.TRAYECTOS.keys())
                if ids:
                    idx = ids.index(trayecto_activo_id) if trayecto_activo_id in ids else -1
                    trayecto_activo_id = ids[(idx + 1) % len(ids)]
                    print(f"[*] Trayecto activo cambiado a: {trayecto_activo_id}")
            prev['f11'] = f11

            # F8 — salir
            if keyboard.is_pressed('f8'):
                print("[*] Saliendo...")
                stop_event.set()
                resume_event.set()
                trayecto_stop_event.set()
                running = False

            time.sleep(0.01)

        except Exception as e:
            print(f"[-] Error en loop principal: {e}")
            break

    game.close()
    print("[+] Programa terminado.")


if __name__ == "__main__":
    main()