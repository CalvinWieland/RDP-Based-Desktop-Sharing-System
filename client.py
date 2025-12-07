# client.py
import socket, io, pygame, select
import os
from dotenv import load_dotenv

load_dotenv()

SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", 50000))
SESSION_CODE = os.getenv("SESSION_CODE", "default-code")

def receive_all(sock, length):
    """Helper to ensure we get exactly the number of bytes we asked for."""
    data = bytearray()
    while len(data) < length:
        try:
            packet = sock.recv(length - len(data))
            if not packet:
                return None
            data.extend(packet)
        except BlockingIOError:
            continue
    return data

def main():
    pygame.init()

    # Temporary size; we'll replace it with the remote frame size
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Remote Desktop Client")

    first_frame = True  # will resize window to match remote once we see the first frame

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Disable Nagle's Algorithm for lower latency
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        s.connect((SERVER_IP, SERVER_PORT))
        print("Connected. Authenticating...")

        s.sendall(f"CLIENT,{SESSION_CODE}\n".encode("utf-8"))
        print("Authenticated.")

        running = True
        while running:
            # 1. Check if network has data (wait max 0.01s)
            ready_to_read, _, _ = select.select([s], [], [], 0.01)

            # --- Receive Video Data ---
            if ready_to_read:
                size_bytes = receive_all(s, 4)
                if not size_bytes:
                    break

                img_size = int.from_bytes(size_bytes, "big")
                img_data = receive_all(s, img_size)

                if img_data:
                    try:
                        image = pygame.image.load(io.BytesIO(img_data))

                        # On the first frame, snap the window to match the remote resolution
                        if first_frame:
                            remote_size = image.get_size()  # (w, h) of the captured frame
                            screen = pygame.display.set_mode(remote_size)
                            pygame.display.set_caption("Remote Desktop Client")
                            print(f"Resized client window to remote size: {remote_size}")
                            first_frame = False

                        screen.blit(image, (0, 0))
                        pygame.display.flip()
                    except Exception as e:
                        # Ignore bad frames but log once in case it's useful
                        print(f"Frame decode error: {e}")

            # --- Handle Inputs ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue

                cmd = None

                if event.type == pygame.MOUSEBUTTONDOWN:
                    btn = "left" if event.button == 1 else "right" if event.button == 3 else None
                    if btn:
                        cmd = f"mouse_click,{btn}\n"

                elif event.type == pygame.MOUSEMOTION:
                    x, y = event.pos
                    # Now 1:1 with remote pixels because window == remote frame size
                    cmd = f"mouse_move,{x},{y}\n"

                elif event.type == pygame.MOUSEWHEEL:
                    # Pygame 2: MOUSEWHEEL has .y for vertical scroll
                    dy = event.y
                    cmd = f"mouse_scroll,{dy}\n"

                elif event.type == pygame.KEYDOWN:
                    key_name = pygame.key.name(event.key)
                    if key_name == "return":
                        key_name = "Key.enter"
                    elif len(key_name) > 1:
                        key_name = f"Key.{key_name}"
                    cmd = f"key_down,{key_name}\n"

                elif event.type == pygame.KEYUP:
                    key_name = pygame.key.name(event.key)
                    if key_name == "return":
                        key_name = "Key.enter"
                    elif len(key_name) > 1:
                        key_name = f"Key.{key_name}"
                    cmd = f"key_up,{key_name}\n"

                if cmd:
                    try:
                        s.sendall(cmd.encode("utf-8"))
                    except OSError:
                        running = False
                        break

    except Exception as e:
        print(f"Error: {e}")
    finally:
        s.close()
        pygame.quit()

if __name__ == "__main__":
    main()
