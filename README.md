# AirPulse Lite (heartlung-flask-fixed)

A lightweight Flask prototype for capturing cardiopulmonary sounds from the browser, visualizing waveforms, storing recordings locally, and running ML inference on spectrogram chunks.

This workspace contains a minimal app you can use while developing your ML model integration.

## Features added in this update

- `/health` endpoint — verifies server, DB presence, and uploads folder writeability.
- `/model-info` endpoint — returns model metadata (path, classes, device, sample rate).
- Improved upload UX with progress feedback in the browser (`static/js/diagnose.js`).
- Basic logging in `app.py` and inference timing returned from `/api/analyze`.
- `README.md` with quickstart notes and developer hints.
- Model-info display on the homepage showing whether a model was found.

## Quickstart (Windows)

1. Create and activate a virtualenv (optional but recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run the app:

```powershell
python app.py
```

4. Open your browser to `http://127.0.0.1:5000`.

## Notes & Next steps

- The ML model path is currently set in `ml_inference.py` as `MODEL_PATH`. Ensure the path points to a compatible PyTorch `.pth` state_dict. If you don't have a model, the app will still work for recording and storing audio.
- `ml_inference.py` provides `get_model_info()` used by `/model-info`.
- Consider adding tests, pinning runtime dependencies, and moving configuration (model path, DB path, sample rate) into environment variables.


