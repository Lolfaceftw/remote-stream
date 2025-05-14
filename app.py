from flask import Flask, render_template, Response, jsonify, request
import cv2
import numpy as np
from mss import mss
import threading
import time
from datetime import datetime
import sys

app = Flask(__name__)

# Global variables for frame management
current_frame = None
frame_lock = threading.Lock()
last_frame_time = time.time()
error_message = None

# Quality settings
quality_settings = {
    '480p': {'scale': 0.33, 'jpeg_quality': 30},  # 33% of original size
    '720p': {'scale': 0.50, 'jpeg_quality': 35},  # 50% of original size
    '1080p': {'scale': 0.75, 'jpeg_quality': 40}  # 75% of original size
}
current_quality = '720p'  # Default quality
quality_lock = threading.Lock()  # Lock for thread-safe quality changes

def capture_screen():
    """Continuously capture the screen and update the current frame."""
    global current_frame, error_message, last_frame_time, current_quality
    
    # Initialize screen capture
    sct = mss()
    
    while True:
        try:
            # Capture the entire screen (first monitor)
            screenshot = sct.grab(sct.monitors[1])  # monitor 1 is the primary monitor
            
            # Convert to numpy array
            frame = np.array(screenshot)
            
            # Get current quality settings thread-safely
            with quality_lock:
                scale = quality_settings[current_quality]['scale']
            
            # Resize frame according to current quality setting
            frame = cv2.resize(frame, None, fx=scale, fy=scale)
            
            # Update the current frame thread-safely
            with frame_lock:
                current_frame = frame
                last_frame_time = time.time()
                error_message = None
            
            # Add a small delay to control CPU usage
            time.sleep(0.05)  # ~20 FPS for better performance
            
        except Exception as e:
            error_message = f"Screen capture error: {str(e)}"
            print(error_message, file=sys.stderr)
            time.sleep(1)  # Wait before retrying

def generate_frames():
    """Generate frames for the video stream."""
    global last_frame_time, error_message, current_quality
    while True:
        try:
            # Check if frames are being captured
            if time.time() - last_frame_time > 5:
                print("Warning: No frames received for 5 seconds", file=sys.stderr)
            
            # Get the current frame thread-safely
            with frame_lock:
                if current_frame is None:
                    if error_message:
                        print(f"Stream error: {error_message}", file=sys.stderr)
                    time.sleep(0.1)
                    continue
                frame = current_frame.copy()
            
            # Get current quality settings thread-safely
            with quality_lock:
                jpeg_quality = quality_settings[current_quality]['jpeg_quality']
            
            # Encode the frame as JPEG with quality based on current setting
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            if not ret:
                print("Error encoding frame", file=sys.stderr)
                continue
                
            # Convert to bytes and yield for streaming
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                   
        except Exception as e:
            print(f"Frame generation error: {str(e)}", file=sys.stderr)
            time.sleep(0.1)

@app.route('/')
def index():
    """Render the home page."""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Video streaming route."""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def status():
    """Check stream status."""
    global last_frame_time, error_message
    if error_message:
        return {'status': 'error', 'message': error_message}
    if time.time() - last_frame_time > 5:
        return {'status': 'error', 'message': 'No frames being captured'}
    return {'status': 'ok'}

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
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, threaded=True) 