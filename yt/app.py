from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading

app = Flask(__name__)
CORS(app)

# Configuration
DOWNLOAD_FOLDER = 'downloads'
MAX_FILE_AGE = 3600  # 1 hour in seconds

# Ensure download folder exists
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def cleanup_old_files():
    """Clean up files older than MAX_FILE_AGE"""
    try:
        for filename in os.listdir(DOWNLOAD_FOLDER):
            filepath = os.path.join(DOWNLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                file_age = time.time() - os.path.getctime(filepath)
                if file_age > MAX_FILE_AGE:
                    os.remove(filepath)
    except Exception as e:
        print(f"Cleanup error: {e}")

@app.route('/api/info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats = []
            for f in info.get('formats', []):
                if f.get('filesize') or f.get('filesize_approx'):
                    formats.append({
                        'format_id': f['format_id'],
                        'ext': f['ext'],
                        'quality': f.get('format_note', 'N/A'),
                        'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        'resolution': f.get('height', 'N/A')
                    })
            
            video_info = {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'author': info.get('uploader', 'Unknown'),
                'formats': formats
            }
            
            return jsonify(video_info)
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        url = data.get('url')
        format_id = data.get('format_id', 'best')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        # Generate unique filename
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        
        ydl_opts = {
            'outtmpl': filepath.replace('.mp4', ''),
            'format': format_id,
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            actual_filename = ydl.prepare_filename(info)
            
            # Ensure we have the correct file extension
            if not actual_filename.endswith('.mp4'):
                new_filename = actual_filename + '.mp4'
                if os.path.exists(actual_filename):
                    os.rename(actual_filename, new_filename)
                    actual_filename = new_filename
            else:
                actual_filename = actual_filename
            
            return jsonify({
                'download_url': f'/api/file/{filename}',
                'title': info.get('title', 'video')
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/<filename>')
def serve_file(filename):
    try:
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy'})

# Cleanup thread
def cleanup_thread():
    while True:
        time.sleep(1800)  # Run every 30 minutes
        cleanup_old_files()

# Start cleanup thread
import time
threading.Thread(target=cleanup_thread, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
