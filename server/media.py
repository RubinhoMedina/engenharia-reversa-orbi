"""Bounded local media processing. Original media is never retained."""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

MAX_VIDEO_BYTES = 100 * 1024 * 1024
MODEL_LOCK = threading.Lock()
MODEL = None
INPUT_OPTIONS = ['-protocol_whitelist', 'file,pipe', '-format_whitelist',
                 'mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,ogg,mp3,wav']


def tool(name):
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f'{name} não foi encontrado no PATH.')
    return executable


def probe(path):
    process = subprocess.run([tool('ffprobe'), '-v', 'error', *INPUT_OPTIONS, '-show_entries', 'format=duration:stream=codec_type,width,height', '-of', 'json', str(path)], capture_output=True, timeout=30)
    if process.returncode:
        raise ValueError('O arquivo não contém mídia válida reconhecida pelo FFprobe.')
    metadata = json.loads(process.stdout)
    try:
        duration = float(metadata['format']['duration'])
    except (KeyError, ValueError, TypeError):
        raise ValueError('Não foi possível determinar a duração da mídia.')
    if not 0 < duration <= 180:
        raise ValueError('O vídeo deve ter até 3 minutos.')
    streams = metadata.get('streams', [])
    if not any(item.get('codec_type') == 'audio' for item in streams):
        raise ValueError('O arquivo não possui faixa de áudio para transcrição.')
    return duration, streams


def transcribe(path):
    global MODEL
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError('Faster Whisper indisponível. Inicie o servidor pelo Python da .venv.')
    started = time.monotonic()
    duration, streams = probe(path)
    with MODEL_LOCK:
        if MODEL is None:
            try:
                MODEL = WhisperModel('tiny', device='cpu', compute_type='int8', cpu_threads=min(os.cpu_count() or 2, 4))
            except Exception as error:
                raise RuntimeError('Não foi possível carregar ou baixar o modelo tiny. Verifique a conexão e tente novamente.') from error
        with tempfile.TemporaryDirectory(prefix='orbit-audio-') as folder:
            audio = Path(folder) / 'audio.wav'
            process = subprocess.run([tool('ffmpeg'), '-nostdin', '-v', 'error', *INPUT_OPTIONS, '-i', str(path), '-vn', '-ac', '1', '-ar', '16000', str(audio)], capture_output=True, timeout=60)
            if process.returncode:
                raise ValueError('Falha ao extrair áudio do arquivo.')
            try:
                iterator, info = MODEL.transcribe(str(audio), language='pt', beam_size=1, vad_filter=True)
                segments = [{'start': round(segment.start, 2), 'end': round(segment.end, 2), 'text': segment.text.strip()} for segment in iterator]
            except Exception as error:
                raise RuntimeError('O modelo local falhou ao transcrever. Tente novamente ou forneça a transcrição manual.') from error
    transcript = ' '.join(segment['text'] for segment in segments).strip()
    if not transcript:
        raise ValueError('Nenhuma fala foi reconhecida. Tente um áudio mais claro ou informe a transcrição manualmente.')
    return {'transcript': transcript, 'segments': segments, 'duration': duration, 'language': info.language, 'processing_seconds': round(time.monotonic() - started, 2), 'has_video': any(item.get('codec_type') == 'video' for item in streams)}


def receive_and_transcribe(stream, size, filename, mime):
    if not 0 < size <= MAX_VIDEO_BYTES:
        raise ValueError('O limite de upload é 100 MB.')
    extension = Path(filename).suffix.lower()
    if extension not in {'.mp4', '.mov', '.webm', '.mkv', '.ogg', '.mp3', '.m4a', '.wav'}:
        raise ValueError('Formato não suportado. Use MP4, MOV, WEBM ou arquivo de áudio.')
    if not mime.startswith(('video/', 'audio/')):
        raise ValueError('O tipo MIME deve ser de áudio ou vídeo.')
    with tempfile.TemporaryDirectory(prefix='orbit-upload-') as folder:
        upload = Path(folder) / f'input{extension}'
        remaining = size
        with upload.open('wb') as output:
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError('O upload foi interrompido.')
                output.write(chunk)
                remaining -= len(chunk)
        result = transcribe(upload)
        if result['has_video']:
            try:
                result['visual'] = inspect_visual(upload)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                result['visual'] = {'available': False}
        return result


def inspect_visual(path):
    """Estimate major luminance changes on a reduced-resolution video stream."""
    process = subprocess.run([
        tool('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error', *INPUT_OPTIONS, '-i', str(path),
        '-map', '0:v:0', '-vf',
        "scale=320:-2,fps=8,select='gt(scene,0.35)',metadata=print:file=-",
        '-an', '-f', 'null', '-',
    ], capture_output=True, text=True, timeout=45)
    if process.returncode:
        raise ValueError('Não foi possível medir as mudanças visuais.')
    changes = [round(float(value), 2) for value in re.findall(r'pts_time:([0-9.]+)', process.stdout)]
    return {'available': True, 'method': 'FFmpeg · diferença entre quadros a 8 fps',
            'changes': changes[:100], 'change_count': len(changes)}
