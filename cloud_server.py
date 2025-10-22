# cloud_server.py
# TCP <-> WebSocket protocol translator/bridge
#
# - Waits for a TCP "HOST" connection (your streamer).
# - Also accepts a WebSocket "CLIENT" connection (your React app).
# - Bridges screen frames TCP -> WS (binary), and input WS -> TCP (text).
#
# Environment (optional):
#   HOST_HOST=0.0.0.0
#   HOST_PORT=50000
#   WS_HOST=0.0.0.0
#   WS_PORT=50001
#
# The TCP peer must authenticate first line as:  HOST,<session>
# The WebSocket peer must send first message as: CLIENT,<session>
#
# Frame format from TCP host: [4 bytes big-endian length][JPEG bytes]
# Input messages from WS -> TCP: UTF-8 text (opaque to bridge)

import asyncio
import os
import socket
import websockets
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

HOST_HOST = os.getenv("HOST_HOST", "0.0.0.0")
HOST_PORT = int(os.getenv("HOST_PORT", "50000"))
WS_HOST   = os.getenv("WS_HOST",   "0.0.0.0")
WS_PORT   = int(os.getenv("WS_PORT",   "50001"))

# --------------------------
# TCP Host side (asyncio)
# --------------------------

async def recv_exactly(reader: asyncio.StreamReader, n: int) -> bytes:
    """Read exactly n bytes (or raise IncompleteReadError)."""
    return await reader.readexactly(n)

async def read_line(reader: asyncio.StreamReader) -> str:
    """Read a line (until \n) and return decoded UTF-8 (strip CR/LF)."""
    line = await reader.readline()
    if not line:
        return ""
    return line.decode("utf-8", errors="replace").strip()

class Bridge:
    """Holds the paired endpoints + session."""
    def __init__(self, session_code: str):
        self.session_code = session_code
        self.host_writer: asyncio.StreamWriter | None = None
        self.host_reader: asyncio.StreamReader | None = None
        self.ws: websockets.WebSocketServerProtocol | None = None
        self.closed = asyncio.Event()

    def is_ready(self) -> bool:
        return self.host_writer is not None and self.ws is not None

    async def close(self):
        if not self.closed.is_set():
            self.closed.set()
            # Close both sides
            try:
                if self.ws:
                    await self.ws.close()
            except Exception:
                pass
            try:
                if self.host_writer:
                    self.host_writer.close()
                    await self.host_writer.wait_closed()
            except Exception:
                pass

# Active bridges by session code
BRIDGES: dict[str, Bridge] = {}

# --------------------------
# TCP server: accept HOST
# --------------------------

async def tcp_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    print(f"[TCP] Connection from {peer}")

    # First, expect an auth line: HOST,<code>\n  (we accept also without newline if sender used sendall once)
    # Try reading a line first; if empty, try a short read for non-line auth
    try:
        # Make socket line-oriented for the initial auth
        writer.write(b"")  # flushable no-op
        await writer.drain()

        # Use small timeout so a non-line first-send doesn't hang
        try:
            auth_line = await asyncio.wait_for(read_line(reader), timeout=3.0)
        except asyncio.TimeoutError:
            # Fall back to a raw short read
            auth_bytes = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            auth_line = auth_bytes.decode("utf-8", errors="replace").strip()

        if not auth_line.startswith("HOST,"):
            print(f"[TCP] Bad auth from {peer}: {auth_line!r}")
            writer.close()
            await writer.wait_closed()
            return

        session_code = auth_line.split(",", 1)[1].strip()
        print(f"[TCP] HOST authenticated for session: {session_code}")

        # Get or create bridge
        bridge = BRIDGES.get(session_code)
        if bridge is None:
            bridge = Bridge(session_code)
            BRIDGES[session_code] = bridge

        # If a host is already connected for this session, replace it
        if bridge.host_writer is not None:
            try:
                bridge.host_writer.close()
                await bridge.host_writer.wait_closed()
            except Exception:
                pass

        bridge.host_reader = reader
        bridge.host_writer = writer

        # If the WS is already present, start pumping frames
        if bridge.ws is not None:
            asyncio.create_task(pump_tcp_to_ws(bridge))
            asyncio.create_task(pump_ws_to_tcp(bridge))

        # Keep the TCP handler alive until closed
        await bridge.closed.wait()

    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
        print("[TCP] Host disconnected")
    except Exception as e:
        print(f"[TCP] Error: {e}")
    finally:
        # If this TCP was part of a bridge, close the session
        try:
            # Find which bridge this writer belonged to
            for code, b in list(BRIDGES.items()):
                if b.host_writer is writer:
                    await b.close()
                    BRIDGES.pop(code, None)
                    break
        except Exception:
            pass

async def pump_tcp_to_ws(bridge: Bridge):
    """Move framed JPEGs from TCP host -> WebSocket client as binary frames."""
    assert bridge.host_reader and bridge.ws
    print(f"[BRIDGE {bridge.session_code}] Pumping TCP -> WS")
    try:
        while not bridge.closed.is_set():
            # Read 4-byte size
            size_bytes = await recv_exactly(bridge.host_reader, 4)
            frame_len = int.from_bytes(size_bytes, "big")
            if frame_len <= 0 or frame_len > (64 * 1024 * 1024):
                # Sanity limit: 64MB
                raise ValueError(f"Unreasonable frame length: {frame_len}")

            # Read frame
            frame = await recv_exactly(bridge.host_reader, frame_len)

            # Send as binary WS frame
            await bridge.ws.send(frame)
    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
        print(f"[BRIDGE {bridge.session_code}] Host closed while sending frames")
    except (ConnectionClosedOK, ConnectionClosedError):
        print(f"[BRIDGE {bridge.session_code}] WS closed while sending frames")
    except Exception as e:
        print(f"[BRIDGE {bridge.session_code}] Error in TCP->WS: {e}")
    finally:
        await bridge.close()

async def pump_ws_to_tcp(bridge: Bridge):
    """Move control/input messages from WebSocket -> TCP host as UTF-8 lines."""
    assert bridge.host_writer and bridge.ws
    print(f"[BRIDGE {bridge.session_code}] Pumping WS -> TCP")
    try:
        async for msg in bridge.ws:
            # If React sends text -> forward as text line to host
            # If React accidentally sends binary (e.g., ArrayBuffer), ignore or decide a policy.
            if isinstance(msg, str):
                data = (msg.rstrip("\r\n") + "\n").encode("utf-8")
                bridge.host_writer.write(data)
                await bridge.host_writer.drain()
            else:
                # Binary from client is not expected (frames are TCP->WS direction)
                # You can decide to forward or drop. For safety, drop here:
                pass
    except (ConnectionClosedOK, ConnectionClosedError):
        print(f"[BRIDGE {bridge.session_code}] WS closed")
    except (BrokenPipeError, ConnectionResetError):
        print(f"[BRIDGE {bridge.session_code}] TCP closed")
    except Exception as e:
        print(f"[BRIDGE {bridge.session_code}] Error in WS->TCP: {e}")
    finally:
        await bridge.close()

# --------------------------
# WebSocket server: accept CLIENT
# --------------------------

async def ws_handler(ws: websockets.WebSocketServerProtocol):
    peer = ws.remote_address
    print(f"[WS] Connection from {peer}")
    try:
        # Expect first message: CLIENT,<code>
        try:
            hello = await asyncio.wait_for(ws.recv(), timeout=5.0)
        except asyncio.TimeoutError:
            await ws.close(code=4000, reason="Auth timeout")
            return

        if not isinstance(hello, str) or not hello.startswith("CLIENT,"):
            await ws.close(code=4001, reason="Bad auth")
            return

        session_code = hello.split(",", 1)[1].strip()
        print(f"[WS] CLIENT authenticated for session: {session_code}")

        bridge = BRIDGES.get(session_code)
        if bridge is None:
            bridge = Bridge(session_code)
            BRIDGES[session_code] = bridge

        # If an old client exists, close it
        if bridge.ws is not None:
            try:
                await bridge.ws.close(code=4002, reason="Replaced by new client")
            except Exception:
                pass

        bridge.ws = ws

        # If the host is ready, start pumps
        if bridge.host_writer is not None and bridge.host_reader is not None:
            asyncio.create_task(pump_tcp_to_ws(bridge))
            asyncio.create_task(pump_ws_to_tcp(bridge))

        # Keep the WS handler alive until the bridge closes
        await bridge.closed.wait()

    except Exception as e:
        print(f"[WS] Error: {e}")
    finally:
        # Ensure cleanup
        try:
            for code, b in list(BRIDGES.items()):
                if b.ws is ws:
                    await b.close()
                    BRIDGES.pop(code, None)
                    break
        except Exception:
            pass

# --------------------------
# Boot both servers
# --------------------------

async def main():
    # TCP listener for host
    tcp_server = await asyncio.start_server(tcp_handler, HOST_HOST, HOST_PORT)
    tcp_socks = ", ".join(str(s.getsockname()) for s in tcp_server.sockets or [])
    print(f"[TCP] Listening on {tcp_socks}")

    # WebSocket listener for client
    ws_server = await websockets.serve(ws_handler, WS_HOST, WS_PORT, max_size=None)
    print(f"[WS ] Listening on ws://{WS_HOST}:{WS_PORT}")

    # Run until cancelled
    async with tcp_server, ws_server:
        await asyncio.gather(tcp_server.serve_forever())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutting down.")
