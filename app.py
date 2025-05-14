from flask import Flask, render_template, Response, jsonify, request
import cv2
import numpy as np
from mss import mss
import threading
import time
from datetime import datetime
import sys
from queue import Queue, Full
import gc

app = Flask(__name__)

# Global variables for frame management
frame_queue = Queue(maxsize=2)  # Small queue to minimize latency
last_frame_time = time.time()
error_message = None

# Quality settings with optimized parameters
quality_settings = {
    '480p': {'scale': 0.33, 'jpeg_quality': 25},  # Reduced quality for better speed
    '720p': {'scale': 0.50, 'jpeg_quality': 30},
    '1080p': {'scale': 0.75, 'jpeg_quality': 35}
}
current_quality = '720p'
quality_lock = threading.Lock()

def capture_screen():
    """Continuously capture the screen and update the frame queue."""
    global last_frame_time, error_message
    
    # Initialize screen capture with optimized settings
    sct = mss()
    monitor = sct.monitors[1]  # Primary monitor
    
    # Pre-allocate numpy array for better performance
    screen_width = monitor["width"]
    screen_height = monitor["height"]
    
    while True:
        try:
            # Capture screen with minimal processing
            screenshot = sct.grab(monitor)
            
            # Get current quality settings thread-safely
            with quality_lock:
                scale = quality_settings[current_quality]['scale']
            
            # Convert to numpy array and resize in one step
            frame = cv2.resize(np.array(screenshot), 
                             (int(screen_width * scale), int(screen_height * scale)),
                             interpolation=cv2.INTER_NEAREST)  # Faster interpolation
            
            # Update timestamp
            last_frame_time = time.time()
            error_message = None
            
            # Try to add to queue without blocking
            try:
                frame_queue.put_nowait(frame)
                # Remove old frame if queue is full
                if frame_queue.full():
                    try:
                        frame_queue.get_nowait()
                    except:
                        pass
            except Full:
                # Skip frame if queue is full
                continue
            
            # Minimal sleep to prevent CPU overload
            time.sleep(0.016)  # Target ~60 FPS
            
        except Exception as e:
            error_message = f"Screen capture error: {str(e)}"
            print(error_message, file=sys.stderr)
            time.sleep(0.1)  # Brief sleep on error

def generate_frames():
    """Generate frames for the video stream with minimal latency."""
    global last_frame_time, error_message
    
    while True:
        try:
            # Check stream health
            if time.time() - last_frame_time > 2:  # Reduced timeout
                print("Warning: No frames received for 2 seconds", file=sys.stderr)
            
            # Get frame from queue with timeout
            try:
                frame = frame_queue.get(timeout=0.1)
            except:
                continue
            
            # Get current quality settings thread-safely
            with quality_lock:
                jpeg_quality = quality_settings[current_quality]['jpeg_quality']
            
            # Optimize JPEG encoding for speed
            encode_params = [
                cv2.IMWRITE_JPEG_QUALITY, jpeg_quality,
                cv2.IMWRITE_JPEG_OPTIMIZE, 0  # Disable optimization for speed
            ]
            
            # Encode frame
            ret, buffer = cv2.imencode('.jpg', frame, encode_params)
            if not ret:
                print("Error encoding frame", file=sys.stderr)
                continue
            
            # Generate frame bytes
            frame_bytes = buffer.tobytes()
            
            # Force garbage collection occasionally
            if frame_queue.qsize() == 0:
                gc.collect()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
        except Exception as e:
            print(f"Frame generation error: {str(e)}", file=sys.stderr)
            time.sleep(0.016)  # Brief sleep on error

@app.route('/')
def index():
    """Render the home page."""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Video streaming route with minimal buffering."""
    response = Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/status')
def status():
    """Check stream status."""
    global last_frame_time, error_message
    if error_message:
        return {'status': 'error', 'message': error_message}
    if time.time() - last_frame_time > 2:  # Reduced timeout
        return {'status': 'error', 'message': 'No frames being captured'}
    return {
        'status': 'ok',
        'latency': round((time.time() - last_frame_time) * 1000, 2),  # ms
        'queue_size': frame_queue.qsize()
    }

@app.route('/set_quality/<quality>')
def set_quality(quality):
    """Set the stream quality."""
    global current_quality
    
    if quality not in quality_settings:
        return jsonify({
            'status': 'error',
            'message': f'Invalid quality setting. Must be one of: {", ".join(quality_settings.keys())}'
        }), 400
    
    # Update quality thread-safely
    with quality_lock:
        current_quality = quality
    
    # Clear frame queue to reduce latency after quality change
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except:
            break
    
    return jsonify({
        'status': 'success',
        'message': f'Quality set to {quality}',
        'quality': quality
    })

@app.route('/get_quality')
def get_quality():
    """Get current quality setting."""
    global current_quality
    with quality_lock:
        quality = current_quality
    return jsonify({
        'status': 'success',
        'quality': quality,
        'available_qualities': list(quality_settings.keys())
    })

if __name__ == '__main__':
    # Start the screen capture thread
    capture_thread = threading.Thread(target=capture_screen, daemon=True)
    capture_thread.start()
    
    # Get local IP address
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\nAccess your screen stream at: http://{local_ip}:5000")
    print("Make sure your mobile device is connected to the same network.")
    print("If you can't connect, try these steps:")
    print("1. Check if you can access http://localhost:5000 on this computer")
    print("2. Temporarily disable your firewall")
    print("3. Make sure your mobile device is on the same WiFi network")
    print("4. Try using a lower resolution or quality if the stream is slow\n")
    
    # Run the Flask app with optimized settings
    app.run(host='0.0.0.0', port=5000, threaded=True) 