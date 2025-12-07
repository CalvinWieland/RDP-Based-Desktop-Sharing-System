import socket, time, ctypes, platform, select, pathlib, sys
import os
from dotenv import load_dotenv
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key

load_dotenv()

SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", 50000))
SESSION_CODE = os.getenv("SESSION_CODE", "default-code")

class RawImage(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("len", ctypes.c_size_t),
    ]


def get_rust_library():
    """Loads the compiled library using a robust, absolute path."""
    script_dir = pathlib.Path(__file__).parent.resolve()
    project_root = script_dir.parent

    if platform.system() == "Windows":
        lib_name = "rdp_core.dll"
    elif platform.system() == "Darwin":
        lib_name = "librdp_core.dylib"
    else:
        lib_name = "librdp_core.so"

    lib_path = project_root / "rdp_core" / "target" / "release" / lib_name
    print(f"Attempting to load library from: {lib_path}")

    rdp_lib = ctypes.CDLL(str(lib_path))

    rdp_lib.capture_and_encode.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    rdp_lib.capture_and_encode.restype = ctypes.POINTER(RawImage)
    rdp_lib.free_image.argtypes = [ctypes.POINTER(RawImage)]

    return rdp_lib


def handle_key(cmd: str, key_val: str, keyboard: KeyboardController):
    """
    Handle key_down / key_up for both printable and special keys.

    Protocol:
        - Printable: "a", "b", "1", etc.
        - Special:   "Key.enter", "Key.ctrl_l", etc. (pynput naming)
    """
    if keyboard is None:
        return

    try:
        if key_val.startswith("Key."):
            attr = key_val.split(".", 1)[1]
            special_key = getattr(Key, attr, None)
            if special_key is None:
                print(f"[KEY] Unknown special key: {key_val}")
                return

            if cmd == "key_down":
                keyboard.press(special_key)
            else:
                keyboard.release(special_key)
        else:
            # Treat as a literal character
            if len(key_val) != 1:
                print(f"[KEY] Unexpected non-special key token: {key_val}")
                return

            if cmd == "key_down":
                keyboard.press(key_val)
            else:
                keyboard.release(key_val)

    except Exception as e:
        print(f"Failed to handle key '{cmd},{key_val}': {e}")


def execute_command(command_str, mouse, keyboard):
    """Parses and executes a command from the server."""
    if mouse is None and keyboard is None:
        return

    try:
        parts = command_str.split(",")
        cmd = parts[0]

        if cmd == "mouse_move" and len(parts) == 3 and mouse:
            x, y = int(parts[1]), int(parts[2])
            mouse.position = (x, y)

        elif cmd == "mouse_click" and len(parts) == 2 and mouse:
            if parts[1] == "left":
                mouse.click(Button.left)
            elif parts[1] == "right":
                mouse.click(Button.right)

        elif cmd == "mouse_scroll" and len(parts) == 2 and mouse:
            dy = int(parts[1])
            # vertical scroll only; positive is up, negative is down
            mouse.scroll(0, dy)

        elif cmd in ("key_down", "key_up") and len(parts) == 2 and keyboard:
            key_val = parts[1]
            handle_key(cmd, key_val, keyboard)

    except Exception as e:
        print(f"Failed to execute command '{command_str}': {e}")


def main():
    # 1. Load Rust Library
    try:
        rdp_lib = get_rust_library()
        print("Successfully loaded Rust Library.")
    except OSError as e:
        print(f"FATAL ERROR: Failed to load Rust library: {e}")
        sys.exit(1)

    # 2. Initialize Input Controllers
    try:
        mouse = MouseController()
        keyboard = KeyboardController()
        print("Input controllers initialized.")
    except Exception as e:
        print(f"Warning: Could not initialize inputs: {e}")
        mouse, keyboard = None, None

    # 3. Network Connection
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            s.connect((SERVER_IP, SERVER_PORT))
            print("Connected. Authenticating...")

            auth_message = f"HOST,{SESSION_CODE}\n"
            s.sendall(auth_message.encode("utf-8"))
            print(f"Authenticated with session code: '{SESSION_CODE}'.")

            # Main Streaming Loop
            target_resolution = (0, 0)

            while True:
                # 4. Listen for commands (non-blocking)
                ready_to_read, _, _ = select.select([s], [], [], 0.01)

                if ready_to_read:
                    try:
                        data = s.recv(4096)
                        if not data:
                            break

                        # Handle multiple commands stuck together
                        commands = data.decode("utf-8", errors="ignore").split("\n")
                        for cmd in commands:
                            cmd = cmd.strip()
                            if not cmd:
                                continue

                            parts = cmd.split(",")
                            if parts[0] == "set_resolution" and len(parts) == 3:
                                target_resolution = (int(parts[1]), int(parts[2]))
                                print(f"Resolution changed to {target_resolution}")
                            else:
                                execute_command(cmd, mouse, keyboard)
                    except Exception as e:
                        print(f"Error processing command: {e}")

                # 5. Call Rust to capture, resize, and encode
                raw_image_ptr = rdp_lib.capture_and_encode(
                    target_resolution[0], target_resolution[1]
                )

                if raw_image_ptr:
                    try:
                        # Convert C-pointer data to Python bytes
                        jpeg_data = bytes(
                            raw_image_ptr.contents.data[: raw_image_ptr.contents.len]
                        )

                        # Send size (4 bytes) + image data
                        size_bytes = len(jpeg_data).to_bytes(4, "big")
                        s.sendall(size_bytes)
                        s.sendall(jpeg_data)
                    except BrokenPipeError:
                        print("Connection closed by server.")
                        break
                    finally:
                        # Critical: Free Rust memory
                        rdp_lib.free_image(raw_image_ptr)

                # Frame rate control (~30 FPS)
                time.sleep(0.033)

    except ConnectionRefusedError:
        print("Connection failed. Is the server script running?")
    except (ConnectionResetError, BrokenPipeError):
        print("\nConnection to server lost.")
    except KeyboardInterrupt:
        print("\nHost application stopped by user.")


if __name__ == "__main__":
    main()
