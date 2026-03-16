import os
import asyncio
from uvicorn import Config, Server

# Ensure Windows uses an event loop that supports subprocesses (required by Playwright)
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    # Force creation of a proactor loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

if __name__ == "__main__":
    config = Config(
        app="app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        loop="none"  # Prevent uvicorn from setting its own loop
    )
    server = Server(config)
    # Run the server on the already set proactor loop
    asyncio.run(server.serve())