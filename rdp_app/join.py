# rdp_app/join.py
# WebSocket client to view a remote session

import asyncio
import websockets
import os
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image

# --- Load .env file ---
load_dotenv()

# --- Configuration ---
WS_SERVER = os.getenv("WS_SERVER", "ws://40.160.241.226:50001")  # Your VPS public IP
SESSION_CODE = os.getenv("SESSION_CODE")

async def connect_and_receive():
    while True:
        try:
            print(f"Connecting to {WS_SERVER} ... with session code {SESSION_CODE}")
            async with websockets.connect(WS_SERVER, max_size=None, open_timeout=10) as ws:
                # Send authentication
                auth_msg = f"CLIENT,{SESSION_CODE}"
                await ws.send(auth_msg)
                print(f"Authenticated with session code '{SESSION_CODE}'")
                print("Waiting for frames...")

                while True:
                    frame = await ws.recv()
                    if isinstance(frame, bytes):
                        # Display the image
                        image = Image.open(BytesIO(frame))
                        image.show()  # Opens system viewer
                    else:
                        print(f"Received unexpected text: {frame}")

        except (ConnectionRefusedError, websockets.InvalidURI, websockets.WebSocketException) as e:
            print(f"Connection failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except KeyboardInterrupt:
            print("Client stopped by user.")
            break
        except Exception as e:
            print(f"Unexpected error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(connect_and_receive())
