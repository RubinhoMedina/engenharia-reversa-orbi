"""Real HTTP media smoke test using an operator-provided audio file."""
from pathlib import Path
import argparse
import json
import subprocess
import tempfile
import threading
import urllib.request
import app
import media


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audio')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='orbit-media-qa-') as folder:
        location = Path(folder)
        app.DATABASE = location / 'test.sqlite3'
        app.connect().close()
        video = location / 'sample.mp4'
        subprocess.run([media.tool('ffmpeg'), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=10', '-i', args.audio, '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(video)], check=True, timeout=60)
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/api/videos'
            request = urllib.request.Request(url, data=video.read_bytes(), headers={'Content-Type': 'video/mp4', 'X-Filename': 'sample.mp4'})
            with urllib.request.urlopen(request, timeout=240) as response:
                result = json.load(response)
            analysis = result['analysis']
            assert analysis['has_video']
            assert analysis['segments']
            assert analysis['transcript']
            with app.connect() as db:
                assert len(app.records(db, 'analyses')) == 1
            print(json.dumps({'status': 'passed', 'duration': analysis['duration'], 'processing_seconds': analysis['processing_seconds'], 'segments': analysis['segments'], 'transcript': analysis['transcript']}, ensure_ascii=True))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
