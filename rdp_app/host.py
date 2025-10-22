# rdp_app/host.py

# We import socket for networking, time for pausing, ctypes for talking to Rust, platform to detect the OS, select for non-blocking network I/O
# pathlib for robust file paths, and sys to exit the program on critical errors.
import socket, time, ctypes, platform, select, pathlib, sys
import os
from dotenv import load_dotenv

# --- Load .env file ---
load_dotenv()

# --- Configuration ---
# Get variables from the environment, with fallback defaults
SERVER_IP = os.getenv("SERVER_IP", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", 50000))
SESSION_CODE = os.getenv("SESSION_CODE", "default-code")

# --- Ctypes Bridge Definition ---
# Python's exact mirror of the Rust RawImage struct.
# ctypes.Structure is the base, and field defines the memory layout.
class RawImage(ctypes.Structure):
    # POINTER(c_uint8) matches *mut u8, and c_size_t matches usize.
    _fields_ = [("data", ctypes.POINTER(ctypes.c_uint8)),
                ("len", ctypes.c_size_t)]
    
def get_rust_library():
    "Loads the compiled library using a robust, absolute path"
    script_dir = pathlib.Path(__file__).parent.resolve() # gets path to the current script, '.parent' navigates up to the rdp_app dir., 
    # '.resolve()' gets the full, absolute path.
    project_root = script_dir.parent # Navigates up again to the project's root folder.
    
    if platform.system() == "Windows":
        lib_name = "rdp_core.dll"
    elif platform.system() == "Darwin":
        lib_name = "librdp_core.dylib"
    else:
        lib_name = "librdp_core.so"

    # OS detection
    lib_path = project_root / "rdp_core" / "target" / "release" / lib_name # The '/' operator from pathlib is used to build a path in an OS-agnostic way.
    
    # DEBUG: Print the path we are trying to load
    print(f"Attempting to load library from: {lib_path}")
    
    rdp_lib = ctypes.CDLL(str(lib_path)) # Command that loads our compiler Rust library into memory.

    # Explicitly define the function signatures. It tells ctypes what data types to expect and return.
    rdp_lib.capture_and_encode.argtypes = [ctypes.c_uint32, ctypes.c_uint32] # Use unsigned int
    rdp_lib.capture_and_encode.restype = ctypes.POINTER(RawImage)
    rdp_lib.free_image.argtypes = [ctypes.POINTER(RawImage)]

    return rdp_lib

def main():
    # wrap the library loading in a try...except block. If the file is missing or corrupted, ctypes.CDLL will raise an OSError.
    try:
        rdp_lib = get_rust_library()
        print("Successfully loaded Rust Library.")
    except OSError as e:
        print("\n-- FATAL ERROR --")
        print(f"Failed to load the Rust library: {e}")
        print("\nPlease check the following:")
        print("1. Does the file mentioned above actually exist?")
        print("2. Did you run 'cargo build --release' in the 'rdp_core' directory?")
        sys.exit(1)

    # --- Connection and Authentication ---
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((SERVER_IP, SERVER_PORT))
            print("Connected. Authenticating...")
            auth_message = f"HOST,{SESSION_CODE}" # Removed extra space
            s.sendall(auth_message.encode('utf-8'))
            print(f"Authenticated with session code: '{SESSION_CODE}'.")
        
            # --- Main Streaming Loop (CORRECTED: INDENTED) ---
            target_resolution = (0, 0)
            while True:
                # 1. Listen for commands from the server (non-blocking)
                ready_to_read, _,  _ = select.select([s], [], [], 0.01)

                if ready_to_read:
                    command_raw = s.recv(1024)
                    if not command_raw: break
                    command = command_raw.decode('utf-8').strip()
                    parts = command.split(',')
                    if parts[0] == "set_resolution" and len(parts) == 3:
                        target_resolution = (int(parts[1]), int(parts[2]))
                        print(f"Resolution changed to {target_resolution}")
                
                # 2. Call Rust to capture, resize, and encode.
                raw_image_ptr = rdp_lib.capture_and_encode(target_resolution[0], target_resolution[1])
                if raw_image_ptr:
                    try:
                        # Use slicing and bytes() conversion
                        jpeg_data = bytes(raw_image_ptr.contents.data[:raw_image_ptr.contents.len])
                        
                        size_bytes = len(jpeg_data).to_bytes(4, 'big')
                        s.sendall(size_bytes)
                        s.sendall(jpeg_data)
                    finally:
                        rdp_lib.free_image(raw_image_ptr)
                
                time.sleep(0.033) # ~30 FPS
                
    except ConnectionRefusedError:
        print("Connection failed. Is the server script running?")
    except (ConnectionResetError, BrokenPipeError):
        print("\nConnection to server lost.")
    except KeyboardInterrupt:
        print("\nHost application stopped by user.")

if __name__ == "__main__":
    main()