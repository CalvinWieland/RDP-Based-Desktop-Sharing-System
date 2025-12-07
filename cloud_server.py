import socket
import threading

waiting_hosts = {}

def forward_stream(source, dest, description):
    """Continuously reads from source and writes to dest."""
    try:
        while True:
            data = source.recv(4096)
            if not data: break
            dest.sendall(data)
    except Exception:
        pass
    finally:
        print(f"{description} closed.")
        source.close()
        dest.close()

def handle_client(conn, addr):
    """
    First message from each connection must be:
        HOST,<SESSION_CODE>\n
    or
        CLIENT,<SESSION_CODE>\n

    Based on this, we either:
      - Register a host in `waiting_hosts`
      - Match a client with a host and start forwarding threads
    """
    global waiting_hosts
    print(f"New connection from {addr}")
    
    try:
        raw_data = conn.recv(1024).decode('utf-8')
        if not raw_data:
            return

        auth_line = raw_data.split('\n')[0].strip()
        
        if ',' not in auth_line:
            print(f"Invalid auth format from {addr}: {auth_line}")
            conn.close()
            return

        role, code = auth_line.split(',')
        
        if role == "HOST":
            print(f"HOST registered for session: {code}")
            waiting_hosts[code] = conn
            
        elif role == "CLIENT":
            print(f"CLIENT requesting session: {code}")
            if code in waiting_hosts:
                host_conn = waiting_hosts.pop(code)
                print(f"Match found! Linking Client {addr} to Host.")
                
                t1 = threading.Thread(target=forward_stream, args=(host_conn, conn, "Video Stream"))
                t2 = threading.Thread(target=forward_stream, args=(conn, host_conn, "Command Stream"))
                
                t1.start()
                t2.start()
            else:
                print(f"Session {code} not found.")
                conn.close()
        else:
            print(f"Unknown role: {role}")
            conn.close()
                
    except Exception as e:
        print(f"Auth error: {e}")
        conn.close()

def main():
    HOST = '0.0.0.0'
    PORT = 50000
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    
    print(f"TCP Router listening on {PORT}...")
    
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr)).start()

if __name__ == "__main__":
    main()
