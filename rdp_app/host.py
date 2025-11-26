import socket
import pyautogui
from PIL import Image
import io
import threading
import time
from dotenv import load_dotenv
import os

load_dotenv()

SERVER_IP = os.getenv("SERVER_IP")
SERVER_PORT = int(os.getenv("SERVER_PORT"))

print("SERVER_IP: ", SERVER_IP)
print("SERVER_PORT: ", SERVER_PORT)

running = True

# this gets logical pixels of computer
LOGICAL_WIDTH, LOGICAL_HEIGHT = pyautogui.size()

# scale factor for logical pixels to actual pixel conversion
SCALE_X = 1.0
SCALE_Y = 1.0

def calculate_scale_factor():
    # there's a difference between logical pixels and actual pixels, this is the scale factor for conversion
    global SCALE_X, SCALE_Y
    try:
        # take a screenshoot to get actual screen width
        screenshot = pyautogui.screenshot()
        phys_w, phys_h = screenshot.size
        
        SCALE_X = phys_w / LOGICAL_WIDTH
        SCALE_Y = phys_h / LOGICAL_HEIGHT
        
        # write down screen sizes
        print(f"Screen size information:")
        print(f"  Logical pixel width x height:   {LOGICAL_WIDTH}x{LOGICAL_HEIGHT}")
        print(f"  Actual screen resolution:  {phys_w}x{phys_h}")
        print(f"  Scale Factor:       {SCALE_X:.2f}x, {SCALE_Y:.2f}x")
    except Exception as e:
        print("Error in getting screen sizes/scale factor: ", e)

def send_screen(conn):
    global running
    while running:
        try:
            # capture screen
            screenshot = pyautogui.screenshot()
            
            # convert and send screenshot
            screenshot = screenshot.convert('RGB')
            buf = io.BytesIO()
            screenshot.save(buf, format='JPEG', quality=50)
            data = buf.getvalue()
            size = len(data).to_bytes(4, 'big')
            conn.sendall(size + data)
        except (BrokenPipeError, ConnectionResetError):
            print("Exception thrown in send screen loop")
            running = False
            break
        except Exception as e:
            print("Error in send screen loop: ", e)
            running = False
            break
        time.sleep(0.03)

def receive_input(conn):
    global running
    while running:
        try:
            data = conn.recv(1024)
            if not data:
                print("[HOST] Viewer disconnected (input thread)")
                running = False
                break

            for line in data.decode().splitlines():
                parts = line.split()
                if not parts: continue

                if parts[0] == 'CLICK' and len(parts) == 4:
                    _, btn_str, x_str, y_str = parts
                    try:
                        # gets physcial pixel placement of mouse
                        pixel_x = int(x_str)
                        pixel_y = int(y_str)
                        
                        # convert coordinates to logical coordinates by scale factor
                        logical_x = int(pixel_x / SCALE_X)
                        logical_y = int(pixel_y / SCALE_Y)

                        # convert instruction into compatible form
                        mouse_btn = btn_str.replace("Button.", "").lower()
                        if mouse_btn not in ['left', 'right', 'middle']:
                            mouse_btn = 'left'

                        # check we aren't clicking outside of the screen
                        logical_x = max(0, min(logical_x, LOGICAL_WIDTH - 1))
                        logical_y = max(0, min(logical_y, LOGICAL_HEIGHT - 1))

                        pyautogui.click(x=logical_x, y=logical_y, button=mouse_btn)
                        
                    except ValueError:
                        print("Error in click")

        except (BrokenPipeError, ConnectionResetError):
            running = False
            break
        except Exception as e:
            print("Input error: ", e)
            running = False
            break

def main():
    global running
    
    # calculate logical scale factor
    calculate_scale_factor()
    
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        conn.connect((SERVER_IP, SERVER_PORT))
        conn.sendall(b'HOST')
        print("Connected to server")
    except Exception as e:
        print("Error in connecting: ", e)
        return

    # multithread sending screen and receiving input
    threading.Thread(target=send_screen, args=(conn,), daemon=True).start()
    threading.Thread(target=receive_input, args=(conn,), daemon=True).start()

    print("Host is running")
    try:
        while running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nshutting down")
        running = False

    conn.close()

if __name__ == "__main__":
    main()