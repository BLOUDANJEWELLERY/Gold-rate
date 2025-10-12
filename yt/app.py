from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time
import random
import requests
from urllib.parse import parse_qs

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = 'downloads'
MAX_FILE_AGE = 3600

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

class YouTubeDownloader:
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
        ]
    
    def get_ydl_opts(self, for_download=False):
        base_opts = {
            'quiet': True,
            'no_warnings': False,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'http_headers': {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                'Connection': 'keep-alive',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['configs', 'webpage'],
                }
            },
            'postprocessors': [],
        }
        
        if for_download:
            base_opts.update({
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(id)s.%(ext)s'),
                'format': 'best[height<=720]',
            })
        
        return base_opts
    
    def extract_video_id(self, url):
        """Extract video ID from various YouTube URL formats"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&?\n]+)',
            r'youtube\.com\/watch\?.+&v=([^&]+)'
        ]
        
        import re
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def get_video_info(self, url):
        """Get video information with multiple fallback methods"""
        try:
            # Method 1: Direct yt-dlp with aggressive options
            ydl_opts = self.get_ydl_opts()
            ydl_opts.update({
                'extract_flat': False,
                'force_json': True,
            })
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                formats = []
                for f in info.get('formats', [])[:15]:  # Limit to first 15 formats
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
                
                # Remove duplicates
                seen = set()
                unique_formats = []
                for f in formats:
                    key = (f['quality'], f['resolution'])
                    if key not in seen:
                        seen.add(key)
                        unique_formats.append(f)
                
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'author': info.get('uploader', 'Unknown'),
                    'formats': unique_formats,
                    'success': True
                }
                
        except Exception as e:
            # Method 2: Try with different extractor args
            try:
                ydl_opts = self.get_ydl_opts()
                ydl_opts.update({
                    'extract_flat': True,
                    'force_json': True,
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android'],
                            'player_skip': ['configs', 'webpage', 'js'],
                        }
                    },
                })
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    # For flat extraction, we get limited info
                    return {
                        'title': info.get('title', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'thumbnail': f'https://i.ytimg.com/vi/{self.extract_video_id(url)}/hqdefault.jpg',
                        'author': info.get('uploader', 'Unknown'),
                        'formats': [{'quality': 'Best', 'format_id': 'best', 'ext': 'mp4', 'filesize': 0}],
                        'success': True
                    }
                    
            except Exception as e2:
                return {
                    'success': False,
                    'error': f'Failed to get video info: {str(e)}'
                }

downloader = YouTubeDownloader()

@app.route('/api/info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        result = downloader.get_video_info(url)
        
        if result['success']:
            return jsonify({
                'title': result['title'],
                'duration': result['duration'],
                'thumbnail': result['thumbnail'],
                'author': result['author'],
                'formats': result['formats']
            })
        else:
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        url = data.get('url')
        format_id = data.get('format_id', 'best[height<=720]')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        video_id = downloader.extract_video_id(url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        
        ydl_opts = downloader.get_ydl_opts(for_download=True)
        ydl_opts.update({
            'outtmpl': filepath.replace('.mp4', ''),
            'format': format_id,
            'merge_output_format': 'mp4',
        })
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Find the actual downloaded file
            actual_path = filepath
            if not os.path.exists(actual_path):
                # Try without extension
                base_path = filepath.replace('.mp4', '')
                if os.path.exists(base_path):
                    os.rename(base_path, actual_path)
                else:
                    # Try to find any file with the same base name
                    for f in os.listdir(DOWNLOAD_FOLDER):
                        if f.startswith(os.path.basename(base_path)):
                            actual_path = os.path.join(DOWNLOAD_FOLDER, f)
                            break
            
            return jsonify({
                'download_url': f'/api/file/{filename}',
                'title': info.get('title', 'video').replace('/', '_')
            })
            
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@app.route('/api/file/<filename>')
def serve_file(filename):
    try:
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=f"video_{filename}.mp4")
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/direct-download', methods=['POST'])
def direct_download():
    """Simplified direct download with minimal options"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        filename = f"{uuid.uuid4().hex}.mp4"
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        
        # Minimal options that often work better
        ydl_opts = {
            'outtmpl': filepath.replace('.mp4', ''),
            'format': 'best[height<=480]',
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'geo_bypass': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            return jsonify({
                'download_url': f'/api/file/{filename}',
                'title': info.get('title', 'video')
            })
            
    except Exception as e:
        return jsonify({'error': f'Direct download failed: {str(e)}'}), 500

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

def cleanup_old_files():
    while True:
        time.sleep(1800)
        try:
            for filename in os.listdir(DOWNLOAD_FOLDER):
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                if os.path.isfile(filepath):
                    file_age = time.time() - os.path.getctime(filepath)
                    if file_age > MAX_FILE_AGE:
                        os.remove(filepath)
        except Exception as e:
            print(f"Cleanup error: {e}")

# Start cleanup thread
threading.Thread(target=cleanup_old_files, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)