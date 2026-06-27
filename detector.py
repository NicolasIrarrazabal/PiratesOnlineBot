import win32api
import win32gui
import win32con

hwnd = win32gui.FindWindow(None, "Pirates Online - Moonlight Haven")

f5_presionado = False

while True:
    estado = bool(win32api.GetAsyncKeyState(win32con.VK_F5))

    if estado and not f5_presionado:
        pos = win32gui.ScreenToClient(hwnd, win32api.GetCursorPos())
        print(f"X: {pos[0]}, Y: {pos[1]}")

    f5_presionado = estado