import os
import tempfile
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple
from flask import Flask, request, jsonify
from paddleocr import PaddleOCR

# Configure environment for GPU and logging
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("FLAGS_log_dir", tempfile.gettempdir())

app = Flask(__name__)

def box_area(box: List[List[float]] | np.ndarray) -> float:
    """Compute the area of a quadrilateral or its bounding rectangle."""
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    if pts.shape[0] < 3:
        _, _, w, h = cv2.boundingRect(pts.astype(np.int32))
        return float(w * h)
    return float(cv2.contourArea(pts))


def box_origin(box: List[List[float]] | np.ndarray) -> Tuple[float, float]:
    """Return the top-left x, y coordinates of a polygon."""
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    x = float(pts[:, 0].min())
    y = float(pts[:, 1].min())
    return x, y


def preprocess_array(img: np.ndarray) -> np.ndarray:
    """Enhance contrast and prepare image for OCR."""
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Contrast Limited Adaptive Histogram Equalization
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    # Convert single channel back to BGR for OCR
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

# Initialize PaddleOCR (GPU use is automatic via environment variables)
try:
    ocr_model = PaddleOCR(use_angle_cls=True, lang='en')
except Exception as e:
    raise RuntimeError(
        "Failed to initialize PaddleOCR."
        " Ensure paddlepaddle-gpu is installed and CUDA_VISIBLE_DEVICES is correct."
        f"\nOriginal error: {e}"
    )

@app.route("/gpu-check")
def gpu_check():
    import paddle
    return jsonify({
        "cuda_compiled": paddle.is_compiled_with_cuda(),
        "device_count": paddle.device.cuda.device_count()
    })

@app.route('/ocr', methods=['POST'])
def ocr():
    files = request.files.getlist('image')
    if not files:
        return jsonify({'error': 'No image uploaded'}), 400

    # Parse optional crop parameters
    try:
        left = int(request.form.get('left', 0))
        top = int(request.form.get('top', 0))
        width = int(request.form.get('width', 0))
        height = int(request.form.get('height', 0))
        use_crop = width > 0 and height > 0
    except ValueError:
        return jsonify({'error': 'Invalid crop parameters'}), 400

    debug_mode = request.args.get('mode') == 'debug'
    processed_imgs: List[np.ndarray] = []

    for f in files:
        img_bytes = f.read()
        npimg = np.frombuffer(img_bytes, np.uint8)
        orig = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if orig is None:
            return jsonify({'error': 'Image decoding failed'}), 400

        # Apply cropping with a small margin to capture full characters
        if use_crop:
            h_full, w_full = orig.shape[:2]
            pad_w = int(0.05 * width)
            pad_h = int(0.05 * height)
            x1 = max(0, left - pad_w)
            y1 = max(0, top - pad_h)
            x2 = min(w_full, left + width + pad_w)
            y2 = min(h_full, top + height + pad_h)
            orig = orig[y1:y2, x1:x2]

        try:
            processed_imgs.append(preprocess_array(orig))
        except Exception as e:
            return jsonify({'error': f'Image processing failed: {e}'}), 400

    # Run OCR inference using predict()
    try:
        result = (
            ocr_model.predict(processed_imgs[0])
            if len(processed_imgs) == 1
            else ocr_model.predict(processed_imgs)
        )
    except Exception as e:
        return jsonify({'error': f'OCR failed: {e}'}), 500

    lines: List[Dict[str, Any]] = []

    for item in result:
        if isinstance(item, dict):
            raw_boxes = item.get('rec_boxes')
            if raw_boxes is None:
                raw_boxes = item.get('boxes', [])
            raw_texts = item.get('rec_texts')
            if raw_texts is None:
                raw_texts = item.get('texts', [])
            raw_scores = item.get('rec_scores')
            if raw_scores is None:
                raw_scores = item.get('scores', [None] * len(raw_texts))

            boxes = list(raw_boxes)
            texts = list(raw_texts)
            scores = list(raw_scores)
            for box, txt, conf in zip(boxes, texts, scores):
                lines.append({
                    'text': txt,
                    'confidence': float(conf or 1.0),
                    'box': np.asarray(box, float).reshape(-1, 2).tolist(),
                    'area': box_area(box)
                })

        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            box, (txt, conf) = item[0], item[1]
            lines.append({
                'text': txt,
                'confidence': float(conf),
                'box': np.asarray(box, float).reshape(-1, 2).tolist(),
                'area': box_area(box)
            })

    if lines:
        max_area = max(l['area'] for l in lines)
        area_threshold = 0.3 * max_area
        filtered = [l for l in lines if l['area'] >= area_threshold]
        filtered.sort(key=lambda l: (box_origin(l['box'])[1], box_origin(l['box'])[0]))
    else:
        filtered = []

    full_text: List[str] = [l['text'] for l in filtered]

    payload: Dict[str, Any] = {
        'lines': filtered,
        'text': '\n'.join(full_text)
    }
    if debug_mode:
        payload['debug'] = {
            'n_lines': len(lines),
            'n_filtered': len(filtered)
        }

    return jsonify(payload), 200

if __name__ == '__main__':
    app.run(port=5001, debug=True)
