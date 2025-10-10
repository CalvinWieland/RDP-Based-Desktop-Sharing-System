import ctypes
import platform

# Determine the library file name based on the OS
if platform.system() == "Windows":
    lib_name = "rdp_core.dll"
elif platform.system() == "Darwin": # macOS
    lib_name = "librdp_core.dylib"
else: # Linux
    lib_name = "librdp_core.so"

# Construct the full path to the library
lib_path = f"./rdp_core/target/debug/{lib_name}"

try:
    # Load the Rust library
    rdp_lib = ctypes.CDLL(lib_path)
    print("Successfully loaded Rust library.")

    # Call the Rust function
    print("Calling Rust function...")
    rdp_lib.hello_from_rust()
    print("Successfully called Rust function.")

except OSError as e:
    print(f"Error loading library: {e}")
    print("\nHave you run 'cargo build' in the 'rdp_core' directory?")