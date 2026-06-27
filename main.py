import input
import time
import keyboard
import threading

TARGET_X = 500
TARGET_Y = 300

SPELL_X      = 692   # coordenadas donde lanzar el hechizo
SPELL_Y      = 404
SPELL_NUMBER = 1     # tecla del hechizo
SPELL_INTERVAL = 11 # segundos entre cada cast

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
    print("  F8  - Salir")
    print("  F9  - Mostrar última posición capturada")
    print()
    print("[!] Hacé un click manual en el juego primero")
    print("=" * 50)

    autocasting     = False
    autocast_thread = None
    stop_event      = threading.Event()

    def autocast_loop():
        print(f"[*] Autocast iniciado — hechizo {SPELL_NUMBER} en ({SPELL_X},{SPELL_Y}) cada {SPELL_INTERVAL}s")
        while not stop_event.is_set():
            if game.ready:
                game.cast_spell(SPELL_NUMBER, SPELL_X, SPELL_Y)
            stop_event.wait(SPELL_INTERVAL)
        print("[*] Autocast detenido")

    running        = True
    f4_was_pressed = False
    f9_was_pressed = False

    while running:
        try:
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
                else:
                    autocasting = False
                    stop_event.set()
            f4_was_pressed = f4_now

            if keyboard.is_pressed('f5'):
                if not game.ready:
                    print("[!] Hacé un click manual en el juego primero")
                else:
                    print(f"\n[*] F5: Clic en ({TARGET_X}, {TARGET_Y})")
                    game.click_at(TARGET_X, TARGET_Y)
                time.sleep(0.3)

            elif keyboard.is_pressed('f8'):
                print("\n[*] Saliendo...")
                stop_event.set()
                running = False

            f9_now = keyboard.is_pressed('f9')
            if f9_now and not f9_was_pressed:
                pos = game.last_captured
                if pos:
                    print(f"\n[F9] Posición capturada: X={pos[0]}, Y={pos[1]}")
                    print(f"     → game.click_at({pos[0]}, {pos[1]})")
                    print(f"     → game.cast_spell(1, {pos[0]}, {pos[1]})")
                else:
                    print("\n[F9] Aún no se capturó ningún click.")
            f9_was_pressed = f9_now

            time.sleep(0.01)

        except Exception as e:
            print(f"[-] Error: {e}")
            break

    game.close()
    print("[+] Programa terminado")


if __name__ == "__main__":
    main()