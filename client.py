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
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Remote Desktop Client")

    first_frame = True

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        s.connect((SERVER_IP, SERVER_PORT))
        print("Connected. Authenticating...")

        s.sendall(f"CLIENT,{SESSION_CODE}\n".encode("utf-8"))
        print("Authenticated.")

        running = True
        while running:
            ready_to_read, _, _ = select.select([s], [], [], 0.01)

            if ready_to_read:
                size_bytes = receive_all(s, 4)
                if not size_bytes:
                    break

                img_size = int.from_bytes(size_bytes, "big")
                img_data = receive_all(s, img_size)

                if img_data:
                    try:
                        image = pygame.image.load(io.BytesIO(img_data))
                        if first_frame:
                            remote_size = image.get_size()
                            screen = pygame.display.set_mode(remote_size)
                            pygame.display.set_caption("Remote Desktop Client")
                            print(f"Resized client window to remote size: {remote_size}")
                            first_frame = False

                        screen.blit(image, (0, 0))
                        pygame.display.flip()
                    except Exception as e:
                        print(f"Frame decode error: {e}")

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
                    cmd = f"mouse_move,{x},{y}\n"

                elif event.type == pygame.MOUSEWHEEL:
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
