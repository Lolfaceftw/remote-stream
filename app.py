from flask import Flask, render_template, Response, jsonify, request
import cv2
import numpy as np
from mss import mss
import threading
import time
from datetime import datetime
import sys
from queue import Queue, Full, Empty
import gc

app = Flask(__name__)

# Global variables for frame management
frame_queue = Queue(maxsize=1)  # Further reduced queue size to prioritize recency
last_frame_time = time.time()
error_message = None

# Quality settings - slightly adjusted for performance
quality_settings = {
    '480p': {'scale': 0.44, 'jpeg_quality': 20},  # Slightly lower quality for speed
    '720p': {'scale': 0.67, 'jpeg_quality': 25},
    '1080p': {'scale': 1.0, 'jpeg_quality': 30}
}
current_quality = '720p'
quality_lock = threading.Lock()

def capture_screen():
    """Continuously capture the screen and update the frame queue."""
    global last_frame_time, error_message
    
    sct = mss()
    monitor = sct.monitors[1]
    
    screen_width = monitor["width"]
    screen_height = monitor["height"]
    
    while True:
        try:
            screenshot = sct.grab(monitor)
            
            with quality_lock:
                scale = quality_settings[current_quality]['scale']
            
            # Optimized resize
            new_width = int(screen_width * scale)
            new_height = int(screen_height * scale)
            
            # Ensure dimensions are valid for cv2.resize
            if new_width <= 0 or new_height <= 0:
                # Fallback to a minimum size or skip frame if scaling results in invalid dimensions
                # This can happen if original monitor res is very small and scale is also small
                print(f"Warning: Invalid dimensions after scaling: {new_width}x{new_height}. Skipping frame.", file=sys.stderr)
                time.sleep(0.033) # Approx 30 FPS on skip
                continue

            frame = cv2.resize(np.array(screenshot), 
                             (new_width, new_height),
                             interpolation=cv2.INTER_NEAREST)
            
            last_frame_time = time.time()
            error_message = None
            
            # Manage the queue: clear old frame, then add new one
            try:
                # Non-blocking clear of the queue
                while not frame_queue.empty():
                    frame_queue.get_nowait()
            except Empty:
                pass # Queue is already empty
            except Exception as e:
                print(f"Error clearing frame queue: {e}", file=sys.stderr)


            try:
                frame_queue.put_nowait(frame)
            except Full:
                # This should ideally not happen often if we clear first
                # If it does, we just skip the frame
                print("Frame queue was full after attempting to clear, skipping frame.", file=sys.stderr)
                pass 
            
            time.sleep(0.016) # Target ~60 FPS in capture loop

        except Exception as e:
            error_message = f"Screen capture error: {str(e)}"
            print(error_message, file=sys.stderr)
            time.sleep(0.1)

def generate_frames():
    """Generate frames for the video stream with minimal latency."""
    global last_frame_time, error_message
    
    while True:
        try:
            if time.time() - last_frame_time > 3: # Increased slightly from 2 to 3
                current_lag = time.time() - last_frame_time
                print(f"Warning: No new frames for {current_lag:.2f} seconds.", file=sys.stderr)

            try:
                # Get frame from queue with a very short timeout to prevent blocking
                frame = frame_queue.get(timeout=0.01) 
            except Empty:
                # If queue is empty, wait briefly and try again
                time.sleep(0.01) # Wait for a new frame
                continue
            
            with quality_lock:
                jpeg_quality = quality_settings[current_quality]['jpeg_quality']
            
            encode_params = [
                cv2.IMWRITE_JPEG_QUALITY, jpeg_quality,
                cv2.IMWRITE_JPEG_OPTIMIZE, 0 
            ]
            
            ret, buffer = cv2.imencode('.jpg', frame, encode_params)
            if not ret:
                print("Error encoding frame", file=sys.stderr)
                continue
            
            frame_bytes = buffer.tobytes()
            
            # No explicit gc.collect() here, let Python manage it unless proven necessary
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            # Small sleep to allow other threads to run, might help if encoding is CPU bound
            time.sleep(0.001)

        except Exception as e:
            print(f"Frame generation error: {str(e)}", file=sys.stderr)
            time.sleep(0.016) # Brief sleep on error

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
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/status')
def status():
    """Check stream status."""
    global last_frame_time, error_message
    current_lag = time.time() - last_frame_time
    
    if error_message:
        return {'status': 'error', 'message': error_message, 'latency': round(current_lag * 1000, 2)}
    
    if current_lag > 3: # Check against the same 3s threshold
        return {'status': 'error', 'message': f'No frames captured for {current_lag:.2f}s', 'latency': round(current_lag * 1000, 2)}
        
    return {
        'status': 'ok',
        'latency': round(current_lag * 1000, 2), 
        'queue_size': frame_queue.qsize()
    }

@app.route('/set_quality/<quality>')
def set_quality_route(quality): # Renamed to avoid conflict with global current_quality
    """Set the stream quality."""
    global current_quality # Explicitly declare usage of global
    
    if quality not in quality_settings:
        return jsonify({
            'status': 'error',
            'message': f'Invalid quality setting. Must be one of: {", ".join(quality_settings.keys())}'
        }), 400
    
    with quality_lock:
        current_quality = quality
    
    # Clear frame queue to apply new quality faster
    cleared_count = 0
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
            cleared_count +=1
        except Empty:
            break
        except Exception as e:
            print(f"Error clearing queue during quality set: {e}", file=sys.stderr)
            break # Avoid infinite loop on persistent error
    print(f"Quality set to {quality}. Cleared {cleared_count} frames from queue.", file=sys.stdout)
    
    return jsonify({
        'status': 'success',
        'message': f'Quality set to {quality}',
        'quality': quality
    })

@app.route('/get_quality')
def get_quality_route(): # Renamed
    """Get current quality setting."""
    global current_quality # Explicitly declare usage of global
    with quality_lock:
        quality = current_quality
    return jsonify({
        'status': 'success',
        'quality': quality,
        'available_qualities': list(quality_settings.keys())
    })

if __name__ == '__main__':
    capture_thread = threading.Thread(target=capture_screen, daemon=True)
    capture_thread.start()
    
    import socket
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"\nAccess your screen stream at: http://{local_ip}:5000")
    except socket.gaierror:
        local_ip = "127.0.0.1" # Fallback for environments where hostname isn't resolvable
        print(f"\nCould not determine local IP. Access stream at: http://{local_ip}:5000 or http://localhost:5000")

    print("Make sure your mobile device is connected to the same network.")
    print("If you can't connect, try these steps:")
    print("1. Check if you can access http://localhost:5000 on this computer")
    print("2. Temporarily disable your firewall")
    print("3. Make sure your mobile device is on the same WiFi network")
    print("4. Try using a lower resolution or quality if the stream is slow\n")
    
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False) # debug=False for production/performance 