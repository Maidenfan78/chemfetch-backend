import os
import json
import tempfile
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple

import cv2
import numpy as np
from flask import Flask, request, jsonify
from paddleocr import PaddleOCR
from PIL import Image

# -----------------------------------------------------------------------------
# Environment & global config
# -----------------------------------------------------------------------------
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("FLAGS_log_dir", tempfile.gettempdir())

app = Flask(__name__)
# Debug image dumping via env var or ?mode=debug
DEBUG_IMAGES_ENV = os.getenv("DEBUG_IMAGES", "0") == "1"
DEBUG_DIR = Path("debug_images")
DEBUG_DIR.mkdir(exist_ok=True)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def box_area(box: List[List[float]] | np.ndarray) -> float:
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    if pts.shape[0] < 3:
        _, _, w, h = cv2.boundingRect(pts.astype(np.int32))
        return float(w * h)
    return float(cv2.contourArea(pts))


def box_origin(box: List[List[float]] | np.ndarray) -> Tuple[float, float]:
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    return float(pts[:, 0].min()), float(pts[:, 1].min())


def resize_to_max_side(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    scale = min(max_side / w, max_side / h, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    return img.resize((new_w, new_h))


def pil_to_cv(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def preprocess_array(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

# -----------------------------------------------------------------------------
# Initialize OCR model
# -----------------------------------------------------------------------------
try:
    ocr_model = PaddleOCR(use_angle_cls=True, lang="en")
except Exception as e:
    raise RuntimeError(f"Failed to initialize PaddleOCR: {e}")

# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------
@app.route("/gpu-check")
def gpu_check():
    import paddle
    compiled = getattr(paddle, "is_compiled_with_cuda", lambda: False)()
    try:
        count = paddle.device.cuda.device_count()
    except Exception:
        count = 0
    return jsonify({"cuda_compiled": compiled, "device_count": count})

# -----------------------------------------------------------------------------
# OCR endpoint
# -----------------------------------------------------------------------------
@app.route('/ocr', methods=['POST'])
def ocr():
    print("[OCR] Form keys:", list(request.form.keys()), "Files:", list(request.files.keys()))

    file = request.files.get('image')
    if not file:
        return jsonify({'error': 'No image uploaded'}), 400

    # Parse crop coords
    try:
        left = int(request.form.get('left', 0))
        top = int(request.form.get('top', 0))
        width = int(request.form.get('width', 0))
        height = int(request.form.get('height', 0))
    except ValueError:
        left = top = width = height = 0
    # Legacy JSON crop:
    if width == 0 and height == 0 and 'crop' in request.form:
        try:
            c = json.loads(request.form['crop'])
            left = int(c.get('left', 0))
            top = int(c.get('top', 0))
            width = int(c.get('width', 0))
            height = int(c.get('height', 0))
        except Exception:
            left = top = width = height = 0

    debug_mode = request.args.get('mode') == 'debug'
    save_images = DEBUG_IMAGES_ENV or debug_mode
    tag = datetime.utcnow().strftime('%Y%m%dT%H%M%S_%f')

    # Open full-resolution image
    img_stream = BytesIO(file.read())
    full = Image.open(img_stream)
    if save_images:
        full_path = DEBUG_DIR / f"{tag}_full.jpg"
        full.save(full_path)
        print(f"[OCR] Saved full image to {full_path}")

    # Parse screen dims for correct scaling
    try:
        screen_w = float(request.form.get('screenWidth', 0))
        screen_h = float(request.form.get('screenHeight', 0))
    except ValueError:
        screen_w = screen_h = 0.0
    if screen_w > 0 and screen_h > 0:
        sx = full.width / screen_w
        sy = full.height / screen_h
    else:
        sx = sy = 1.0
    print(f"[OCR] full={full.width}x{full.height}, screen={screen_w}x{screen_h}, sx={sx:.2f}, sy={sy:.2f}")

    # Crop on full-res with proper scaling
    if width > 0 and height > 0:
        l = int(left * sx)
        t = int(top * sy)
        w = int(width * sx)
        h = int(height * sy)
        print(f"[OCR] crop full-res: l={l}, t={t}, w={w}, h={h}")
        roi = full.crop((l, t, l + w, t + h))
    else:
        roi = full
    if save_images:
        crop_path = DEBUG_DIR / f"{tag}_crop.jpg"
        roi.save(crop_path)
        print(f"[OCR] Saved cropped image to {crop_path}")

    # Down-scale to limit
    scaled = resize_to_max_side(roi, max_side=4000)
    if save_images:
        scaled_path = DEBUG_DIR / f"{tag}_scaled.jpg"
        scaled.save(scaled_path)
        print(f"[OCR] Saved scaled image to {scaled_path}")

    # To OpenCV
    cv_img = pil_to_cv(scaled)
    # Preprocess
    try:
        proc = preprocess_array(cv_img)
    except Exception as e:
        return jsonify({'error': f'Preprocess failed: {e}'}), 400
    if save_images:
        proc_path = DEBUG_DIR / f"{tag}_proc.jpg"
        cv2.imwrite(str(proc_path), proc)
        print(f"[OCR] Saved processed image to {proc_path}")

    # OCR inference
    try:
        result = ocr_model.predict(proc)
    except Exception as e:
        return jsonify({'error': f'OCR failed: {e}'}), 500

    # Parse results placeholder
    lines: List[Dict[str, Any]] = []
    text = ''.join(l['text'] for l in lines)

    resp = {'lines': lines, 'text': text}
    if save_images or debug_mode:
        resp['debug'] = {'tag': tag, 'saved_images': save_images}

    return jsonify(resp), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)
