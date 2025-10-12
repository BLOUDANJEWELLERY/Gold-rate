from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import uuid
import threading
import time
import asyncio
from pyppeteer import launch
import requests
import json

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = 'downloads'
MAX_FILE_AGE = 3600

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

async def get_video_info_with_browser(url):
    """Use real browser to bypass bot detection"""
    browser = await launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu'
        ]
    )
    
    try:
        page = await browser.newPage()
        
        # Set realistic user agent
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        # Navigate to YouTube
        await page.goto(url, {'waitUntil': 'networkidle2'})
        
        # Wait for page to load
        await asyncio.sleep(3)
        
        # Extract video info using JavaScript
        video_info = await page.evaluate('''() => {
            const video = document.querySelector('video');
            const title = document.querySelector('h1.ytd-video-primary-info-renderer')?.innerText || 
                         document.querySelector('title')?.innerText.replace(' - YouTube', '') ||
                         'Unknown Title';
            
            const channel = document.querySelector('#channel-name a')?.innerText || 
                          document.querySelector('.ytd-channel-name a')?.innerText ||
                          'Unknown Channel';
            
            const thumbnail = document.querySelector('meta[property="og:image"]')?.content ||
                            document.querySelector('link[rel="image_src"]')?.href ||
                            '';
            
            return {
                title: title,
                author: channel,
                thumbnail: thumbnail,
                duration: video ? video.duration : 0,
                available: true
            };
        }''')
        
        return video_info
        
    except Exception as e:
        return {'error': str(e), 'available': False}
    finally:
        await browser.close()

def get_video_info_sync(url):
    """Sync wrapper for async browser function"""
    return asyncio.get_event_loop().run_until_complete(
        get_video_info_with_browser(url)
    )

@app.route('/api/info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400
        
        # Try browser method first
        browser_info = get_video_info_sync(url)
        
        if browser_info.get('available'):
            # Return basic format options
            formats = [
                {'quality': '360p', 'format_id': '18', 'ext': 'mp4', 'filesize': 0},
                {'quality': '720p', 'format_id': '22', 'ext': 'mp4', 'filesize': 0},
                {'quality': 'Best', 'format_id': 'best', 'ext': 'mp4', 'filesize': 0}
            ]
            
            return jsonify({
                'title': browser_info['title'],
                'author': browser_info['author'],
                'thumbnail': browser_info['thumbnail'],
                'duration': browser_info['duration'],
                'formats': formats
            })
        else:
            return jsonify({'error': 'Could not fetch video information'}), 400
            
    except Exception as e:
        return jsonify({'error': f'Failed to get video info: {str(e)}'}), 500

# Add these new requirements to requirements.txt
# pyppeteer==1.0.2
# requests==2.31.0