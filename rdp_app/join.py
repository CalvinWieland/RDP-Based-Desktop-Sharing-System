import socket
import cv2
import io
import threading
from PIL import Image
import time
import numpy as np
import ctypes
from dotenv import load_dotenv
import os

load_dotenv()

# VPS's IP address
SERVER_IP = os.getenv("SERVER_IP")
SERVER_PORT = int(os.getenv("SERVER_PORT"))

# for windows, DPI awareness allows the DPI to change adaptively
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) 
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# random globals
latest_frame = None
running = True
click_queue = []
current_scale = 1.0
current_offset_x = 0
current_offset_y = 0
frame_ready = False 
host_screen_size = (1920, 1080)

# mouse callback for mouse activity
def cv2_mouse_callback(event, x, y, flags, param):
    # uses global variables
    global click_queue, current_scale, current_offset_x, current_offset_y, frame_ready

    # if mouse is pressed, add click to queue
    if event == cv2.EVENT_LBUTTONDOWN and frame_ready and current_scale > 0:
        #convert mouse position to the host's mouse position
        img_x = x - current_offset_x
        img_y = y - current_offset_y
        host_x = int(img_x / current_scale)
        host_y = int(img_y / current_scale)
        if 0 <= host_x < host_screen_size[0] and 0 <= host_y < host_screen_size[1]:
            click_queue.append(("Button.left", host_x, host_y))

# receives screen capture from the server
def receive_screen(conn):
    global latest_frame, running
    while running:
        try:
            size_bytes = conn.recv(4)
            if not size_bytes: break
            size = int.from_bytes(size_bytes, 'big')
            data = b''
            while len(data) < size:
                packet = conn.recv(size - len(data))
                if not packet: break
                data += packet
            img = Image.open(io.BytesIO(data))
            latest_frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        except Exception:
            running = False
            break

# sends input back to the server
def send_input(conn):
    global running, click_queue
    while running:
        try:
            while click_queue:
                btn, x, y = click_queue.pop(0)
                conn.sendall(f"CLICK {btn} {x} {y}\n".encode())
            time.sleep(0.03)
        except Exception:
            running = False
            break

def main():
    global latest_frame, running
    global current_scale, current_offset_x, current_offset_y, frame_ready, host_screen_size

    # attempt to connect to the server
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        conn.connect((SERVER_IP, SERVER_PORT))
        conn.sendall(b'VIEWER')
        print("You are now connected as a viewer")
    except Exception as e:
        print(f"There was ann error with connecting: {e}")
        return

    # multithread sending and receiving input, with the connection as the paramater
    threading.Thread(target=receive_screen, args=(conn,), daemon=True).start()
    threading.Thread(target=send_input, args=(conn,), daemon=True).start()


    # set up cv2 screen that displays host's screen, including callback
    window_name = "Host Screen"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, cv2_mouse_callback)

    # run the main program
    while running:
        if latest_frame is not None:
            # get frame height and width and store them in host_screen_size
            frame_h, frame_w = latest_frame.shape[:2]
            host_screen_size = (frame_w, frame_h)
            frame_ready = True

            try:
                # get the window width and height
                _, _, win_w, win_h = cv2.getWindowImageRect(window_name)
            except:
                win_w, win_h = 1280, 720
            
            if win_w <= 0 or win_h <= 0: win_w, win_h = 1280, 720
            
            # get scale, represented by window size over frame size
            scale = min(win_w / frame_w, win_h / frame_h)
            current_scale = scale
            new_w = int(frame_w * scale)
            new_h = int(frame_h * scale)

            # resize frame
            interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
            resized_frame = cv2.resize(latest_frame, (new_w, new_h), interpolation=interp)
            
            canvas = np.zeros((win_h, win_w, 3), dtype="uint8")
            current_offset_x = (win_w - new_w) // 2
            current_offset_y = (win_h - new_h) // 2
            
            # make the canvas matrix 
            for yy in range(new_h):
                for xx in range(new_w):
                    canvas[current_offset_y + yy, current_offset_x + xx] = resized_frame[yy, xx]
            
            # show the cv2 window
            cv2.imshow(window_name, canvas)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            running = False
            break

    cv2.destroyAllWindows()
    conn.close()

if __name__ == "__main__":
    main()