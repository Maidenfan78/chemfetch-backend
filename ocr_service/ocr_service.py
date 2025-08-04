import os
import tempfile
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
from flask import Flask, request, jsonify
from paddleocr import PaddleOCR

# -----------------------------------------------------------------------------
# Environment & global config
# -----------------------------------------------------------------------------

# Force‑select GPU 0 (if multiple) and silence verbose paddle logs
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("FLAGS_log_dir", tempfile.gettempdir())

app = Flask(__name__)

# Debug image dumping (set DEBUG_IMAGES=1 to enable, or pass ?mode=debug)
DEBUG_IMAGES_ENV = os.getenv("DEBUG_IMAGES", "0") == "1"
DEBUG_DIR = Path("debug_images")  # add to .gitignore in the repo root
DEBUG_DIR.mkdir(exist_ok=True)

# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------

def box_area(box: List[List[float]] | np.ndarray) -> float:
    """Compute the area of a quadrilateral or its bounding rectangle."""
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    if pts.shape[0] < 3:  # fallback to bounding‑rect for degenerate cases
        _, _, w, h = cv2.boundingRect(pts.astype(np.int32))
        return float(w * h)
    return float(cv2.contourArea(pts))


def box_origin(box: List[List[float]] | np.ndarray) -> Tuple[float, float]:
    """Return the top‑left (x, y) coordinates of a polygon."""
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    x = float(pts[:, 0].min())
    y = float(pts[:, 1].min())
    return x, y


def preprocess_array(img: np.ndarray) -> np.ndarray:
    """Enhance contrast and prepare image for OCR."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

# -----------------------------------------------------------------------------
# Model initialisation
# -----------------------------------------------------------------------------

try:
    ocr_model = PaddleOCR(use_angle_cls=True, lang='en')  # GPU auto‑selected
except Exception as e:
    raise RuntimeError(
        "Failed to initialise PaddleOCR. "
        "Ensure paddlepaddle‑gpu is installed and CUDA_VISIBLE_DEVICES is correct."\
        f"\nOriginal error: {e}"
    )

# -----------------------------------------------------------------------------
# Health‑check endpoint
# -----------------------------------------------------------------------------

@app.route("/gpu-check")
def gpu_check():
    """Simple endpoint to verify CUDA availability inside the container/host."""
    import paddle

    cuda_compiled = getattr(paddle, "is_compiled_with_cuda", lambda: False)()
    try:
        device_count = paddle.device.cuda.device_count()
    except Exception:  # pragma: no cover – device API may differ per version
        device_count = 0

    return jsonify({
        "cuda_compiled": cuda_compiled,
        "device_count": device_count,
    })

# -----------------------------------------------------------------------------
# Main OCR endpoint
# -----------------------------------------------------------------------------

@app.route('/ocr', methods=['POST'])
def ocr():
    # --- Debug logging --------------------------------------------------------
    print(f"[OCR Service] Incoming Headers: {dict(request.headers)}")
    print(f"[OCR Service] Form keys: {list(request.form.keys())}, Files: {list(request.files.keys())}")
    # -------------------------------------------------------------------------

    files = request.files.getlist('image')
    if not files:
        return jsonify({'error': 'No image uploaded'}), 400

    # Parse optional crop parameters (left/top/width/height)
    try:
        left = int(request.form.get('left', 0))
        top = int(request.form.get('top', 0))
        width = int(request.form.get('width', 0))
        height = int(request.form.get('height', 0))
        use_crop = width > 0 and height > 0
    except ValueError:
        return jsonify({'error': 'Invalid crop parameters'}), 400

    # Debug / image‑dump mode
    debug_mode = request.args.get('mode') == 'debug'
    save_images = DEBUG_IMAGES_ENV or debug_mode
    req_tag = datetime.utcnow().strftime('%Y%m%dT%H%M%S_%f')

    processed_imgs: List[np.ndarray] = []

    for idx, f in enumerate(files):
        img_bytes = f.read()
        npimg = np.frombuffer(img_bytes, np.uint8)
        orig_full = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if orig_full is None:
            return jsonify({'error': 'Image decoding failed'}), 400

        # Expand crop slightly to capture borders
        if use_crop:
            h_full, w_full = orig_full.shape[:2]
            pad_w = int(0.05 * width)
            pad_h = int(0.05 * height)
            x1 = max(0, left - pad_w)
            y1 = max(0, top - pad_h)
            x2 = min(w_full, left + width + pad_w)
            y2 = min(h_full, top + height + pad_h)
            orig = orig_full[y1:y2, x1:x2]
        else:
            orig = orig_full

        if save_images:
            cv2.imwrite(str(DEBUG_DIR / f"{req_tag}_{idx}_orig.jpg"), orig)

        try:
            processed = preprocess_array(orig)
        except Exception as e:
            return jsonify({'error': f'Image processing failed: {e}'}), 400

        if save_images:
            cv2.imwrite(str(DEBUG_DIR / f"{req_tag}_{idx}_proc.jpg"), processed)

        processed_imgs.append(processed)

    # -------------------- OCR inference --------------------------------------
    try:
        result = ocr_model.predict(processed_imgs[0] if len(processed_imgs) == 1 else processed_imgs)
    except Exception as e:
        return jsonify({'error': f'OCR failed: {e}'}), 500

    # -------------------- Post‑processing ------------------------------------
    lines: List[Dict[str, Any]] = []

    for item in result:
        if isinstance(item, dict):
            # Avoid ndarray truth‑value errors – use explicit None check
            raw_boxes = item.get('rec_boxes')
            if raw_boxes is None:
                raw_boxes = item.get('boxes', [])

            raw_texts = item.get('rec_texts')
            if raw_texts is None:
                raw_texts = item.get('texts', [])

            raw_scores = item.get('rec_scores')
            if raw_scores is None:
                raw_scores = item.get('scores', [None] * len(raw_texts))

            for box, txt, conf in zip(raw_boxes, raw_texts, raw_scores):
                lines.append({
                    'text': txt,
                    'confidence': float(conf or 1.0),
                    'box': np.asarray(box, float).reshape(-1, 2).tolist(),
                    'area': box_area(box),
                })

        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            box, (txt, conf) = item[0], item[1]
            lines.append({
                'text': txt,
                'confidence': float(conf),
                'box': np.asarray(box, float).reshape(-1, 2).tolist(),
                'area': box_area(box),
            })

    # Filter out very small boxes – keeps the most relevant text
    if lines:
        max_area = max(l['area'] for l in lines)
        area_threshold = 0.30 * max_area
        filtered = [l for l in lines if l['area'] >= area_threshold]
        filtered.sort(key=lambda l: (box_origin(l['box'])[1], box_origin(l['box'])[0]))
    else:
        filtered = []

    full_text = '\n'.join(l['text'] for l in filtered)

    payload: Dict[str, Any] = {
        'lines': filtered,
        'text': full_text,
    }

    if debug_mode or save_images:
        payload['debug'] = {
            'n_lines': len(lines),
            'n_filtered': len(filtered),
            'saved_images': save_images,
            'tag': req_tag,
        }

    return jsonify(payload), 200

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Listen on every interface so LAN devices & emulators can reach us
    app.run(host="0.0.0.0", port=5001, debug=False)
