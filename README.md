# Screen Stream

A Python application that streams your desktop screen to mobile devices over your local network. Access your computer screen from any device connected to the same network through a web browser.

## Features

- Real-time screen streaming
- Mobile-friendly web interface
- Automatic local IP detection
- Responsive design (works in both portrait and landscape)
- ~30 FPS streaming
- Low latency

## Requirements

- Python 3.7 or higher
- Web browser (mobile or desktop)
- Devices must be on the same local network

## Installation

1. Clone this repository or download the files
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   python app.py
   ```

2. The application will display a URL (e.g., `http://192.168.1.100:5000`)

3. On your mobile device:
   - Connect to the same WiFi network as your computer
   - Open a web browser
   - Enter the URL shown in the terminal
   - The stream should start automatically

## Troubleshooting

1. **Can't access the stream:**
   - Ensure both devices are on the same network
   - Check if any firewall is blocking port 5000
   - Try accessing the stream using your computer's localhost first (`http://localhost:5000`)

2. **Stream is slow or laggy:**
   - Check your network connection
   - Reduce other network traffic
   - Try moving closer to your WiFi router

3. **Permission errors:**
   - Make sure you have screen capture permissions enabled
   - Run the application with appropriate permissions

## Performance Notes

- The stream quality is set to 60% JPEG quality for optimal performance
- The frame rate is limited to ~30 FPS to reduce CPU usage
- In landscape mode, the interface automatically hides headers for a full-screen experience

## Security Note

This application is intended for use on trusted local networks only. It does not implement authentication or encryption, so do not expose it to the public internet. 