"""Modal backend layer — an ADDITION to the existing Hugging Face deployment.

This package is completely separate from the HF/Gradio entrypoint (`app.py`
at the repo root) and does not modify it, `frontend/`, or `vercel.json`.

Modules:
    modal_app/image.py  — Modal Image (dependencies actually required by backend/)
    modal_app/api.py    — FastAPI JSON API (GET /health, POST /query) -> controller
    modal_app/app.py    — Modal App: GPU class + @modal.enter model lifecycle

Deploy (never run as part of a code change unless explicitly asked):
    pip install -U modal
    modal deploy modal_app/app.py
"""
