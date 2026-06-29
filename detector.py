import win32api
import win32gui
import win32con

hwnd = win32gui.FindWindow(None, "Pirates Online - Moonlight Haven")

multiply_presionad = False

while True:
    estado = bool(win32api.GetAsyncKeyState(win32con.VK_MULTIPLY))

    if estado and not multiply_presionad:
        pos = win32gui.ScreenToClient(hwnd, win32api.GetCursorPos())
        print(f"X: {pos[0]}, Y: {pos[1]}")

    multiply_presionad = estado