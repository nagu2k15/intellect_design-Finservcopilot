"""Entry point for running this app directly (e.g. Visual Studio's "Set as
Startup File" in Open Folder mode, or `python run.py`).

Sibling `app/` files use absolute imports like `from app.routers...`, which
only resolve when the project root is on sys.path -- true for
`python -m uvicorn app.main:app`, but NOT if a script *inside* app/ is
executed directly. Running this file instead (it lives at the project root)
keeps that import working.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
