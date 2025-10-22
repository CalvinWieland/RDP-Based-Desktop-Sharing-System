# cloud_server.py

import socket
import sys

def receive_all(sock, length):
    """
    Helper function to reliably receive an exact number of bytes.
    This is critical for reading our 'framed' data (size + image).
    """
    data = bytearray()
    while len(data) < length:
        # Request the remaining number of bytes
        packet = sock.recv(length - len(data))
        if not packet:
            # Connection was lost before we got all the data
            return None
        data.extend(packet)
    return data

def run_server():
    HOST = '0.0.0.0' # Listen on all network interfaces
    PORT = 50000     # The port your host is connecting to

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        
        # --- This line helps prevent "Address already in use" ---
        # It tells the OS to reuse the port even if it's in a timeout state
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # ---------------------------------------------------------
        
        try:
            s.bind((HOST, PORT))
            s.listen()
            print(f"Server is listening on {HOST}:{PORT}...")
            
            conn, addr = s.accept()
            with conn:
                print(f"Host connected from {addr}")
                
                # 1. Wait for and read the authentication message
                auth_data = conn.recv(1024).decode('utf-8')
                
                if auth_data.startswith("HOST,"):
                    code = auth_data.split(',')[1]
                    print(f"Host successfully authenticated with session code: {code}")
                    
                    # 2. Now, just receive the screen stream in a loop
                    # This proves the host is working correctly.
                    while True:
                        # First, read the 4-byte size header
                        size_bytes = receive_all(conn, 4)
                        if not size_bytes:
                            print("Host disconnected (failed to read size).")
                            break
                        
                        img_size = int.from_bytes(size_bytes, 'big')
                        
                        # Second, read the full image data
                        img_data = receive_all(conn, img_size)
                        if not img_data:
                            print("Host disconnected (failed to read image data).")
                            break
                        
                        # We don't need to do anything with the data,
                        # just confirm we got it.
                        print(f"Received image frame of size {img_size} bytes")

                else:
                    print("Connection did not authenticate as a HOST. Closing.")

        except KeyboardInterrupt:
            print("\nServer shutting down.")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    run_server()