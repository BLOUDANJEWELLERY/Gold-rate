from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time
import random

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

def get_ydl_opts():
    """Get YouTube DL options with enhanced headers to avoid bot detection"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0'
    ]
    
    return {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'user_agent': random.choice(user_agents),
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': random.choice(user_agents),
        },
        # Add these options to handle bot detection
        'extractor_args': {
            'youtube': {
                'skip': ['dash', 'hls']
            }
        },
        'format': 'best[height<=720]',  # Limit to 720p to avoid heavy processing
        'socket_timeout': 30,
        'retries': 3,
    }

@app.route('/api/info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        ydl_opts = get_ydl_opts()
        ydl_opts['extract_flat'] = True
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get available formats
            formats = []
            for f in info.get('formats', [])[:10]:  # Limit to first 10 formats
                if f.get('filesize') or f.get('filesize_approx'):
                    format_note = f.get('format_note', 'N/A')
                    if format_note == 'N/A' and f.get('height'):
                        format_note = f'{f.get("height")}p'
                    
                    formats.append({
                        'format_id': f['format_id'],
                        'ext': f.get('ext', 'mp4'),
                        'quality': format_note,
                        'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        'resolution': f.get('height', 'N/A')
                    })
            
            # Remove duplicates by quality
            seen = set()
            unique_formats = []
            for f in formats:
                key = (f['quality'], f['resolution'])
                if key not in seen:
                    seen.add(key)
                    unique_formats.append(f)
            
            video_info = {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', ''),
                'author': info.get('uploader', 'Unknown'),
                'formats': unique_formats
            }
            
            return jsonify(video_info)
            
    except Exception as e:
        error_msg = str(e)
        if "Sign in to confirm you're not a bot" in error_msg:
            return jsonify({'error': 'YouTube is blocking this request. Please try again later or use a different network.'}), 429
        elif "Video unavailable" in error_msg:
            return jsonify({'error': 'Video is unavailable or private.'}), 404
        else:
            return jsonify({'error': f'Failed to get video info: {error_msg}'}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        url = data.get('url')
        format_id = data.get('format_id', 'best[height<=720]')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        # Generate unique filename
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        
        ydl_opts = get_ydl_opts()
        ydl_opts.update({
            'outtmpl': filepath.replace('.mp4', ''),
            'format': format_id,
        })
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            actual_filename = ydl.prepare_filename(info)
            
            # Ensure we have the correct file extension
            final_filename = actual_filename
            if not actual_filename.endswith('.mp4'):
                new_filename = actual_filename + '.mp4'
                if os.path.exists(actual_filename):
                    os.rename(actual_filename, new_filename)
                    final_filename = new_filename
            
            return jsonify({
                'download_url': f'/api/file/{filename}',
                'title': info.get('title', 'video').replace('/', '_')  # Sanitize filename
            })
            
    except Exception as e:
        error_msg = str(e)
        if "Sign in to confirm you're not a bot" in error_msg:
            return jsonify({'error': 'YouTube is blocking this request. Please try again later.'}), 429
        else:
            return jsonify({'error': f'Download failed: {error_msg}'}), 500

@app.route('/api/file/<filename>')
def serve_file(filename):
    try:
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=f"video_{filename}.mp4")
        else:
            return jsonify({'error': 'File not found or expired'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy'})

# Alternative endpoint for direct download (simpler approach)
@app.route('/api/direct-download', methods=['POST'])
def direct_download():
    """Simplified download endpoint with fewer options"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        
        # Very simple options
        ydl_opts = {
            'outtmpl': filepath.replace('.mp4', ''),
            'format': 'best[height<=480]',  # Lower quality for better success rate
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            return jsonify({
                'download_url': f'/api/file/{filename}',
                'title': info.get('title', 'video')
            })
            
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

# Cleanup thread
def cleanup_thread():
    while True:
        time.sleep(1800)  # Run every 30 minutes
        cleanup_old_files()

# Start cleanup thread
threading.Thread(target=cleanup_thread, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
