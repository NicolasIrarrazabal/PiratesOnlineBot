import input
import time
import keyboard

def main():
    game = input.GameInput()

    if not game.attach():
        print("[-] No se pudo conectar al juego")
        return

    print("=" * 50)
    print("CONTROLADOR DE MOUSE - Pirates Online")
    print("=" * 50)
    print("Modo:", "Interception (background)" if game._inter else "PostMessage (fallback)")
    print()
    print("Comandos:")
    print("  F5  - Clic en coordenadas predefinidas")
    print("  F6  - Mostrar posición actual en memoria")
    print("  F7  - Clic en posición actual (sin mover)")
    print("  F8  - Salir")
    print("=" * 50)

    TARGET_X = 500
    TARGET_Y = 300

    running = True

    while running:
        try:
            if keyboard.is_pressed('f5'):
                print(f"\n[*] F5: Clic en ({TARGET_X}, {TARGET_Y})")
                game.click_at(TARGET_X, TARGET_Y, use_memory=True)
                time.sleep(0.3)

            elif keyboard.is_pressed('f6'):
                x, y = game.get_mouse_pos()
                print(f"\n[*] Posición en memoria: X={x}, Y={y}")
                time.sleep(0.3)

            elif keyboard.is_pressed('f7'):
                print(f"\n[*] F7: Clic en posición actual")
                game.send_click()
                time.sleep(0.3)

            elif keyboard.is_pressed('f8'):
                print("\n[*] Saliendo...")
                running = False

            time.sleep(0.01)

        except Exception as e:
            print(f"[-] Error: {e}")
            break

    game.close()
    print("[+] Programa terminado")


if __name__ == "__main__":
    main()