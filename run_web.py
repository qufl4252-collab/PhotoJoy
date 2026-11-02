"""Run PhotoJoy in a local browser; public deployment uses the same app factory."""
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("photojoy_web.app:app_factory", factory=True, host="127.0.0.1",
                port=int(os.getenv("PORT", "8765")), proxy_headers=False)
