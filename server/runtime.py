"""Start an already installed local Ollama runtime when selected by the owner."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import urlopen
from urllib.error import URLError
import config


def available():
    try:
        with urlopen('http://127.0.0.1:11434/api/version', timeout=2) as response:
            return bool(json.loads(response.read(4096)).get('version'))
    except (OSError, URLError, ValueError):
        return False


def main():
    settings = config.Settings.from_env()
    if os.getenv('ORBIT_AI_PROVIDER', 'rules') != 'ollama' or available():
        return
    executable = shutil.which('ollama')
    if not executable:
        candidate = Path(os.getenv('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'ollama.exe'
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        raise RuntimeError('Ollama não está instalado. Instale a versão oficial ou selecione outro motor no assistente.')
    # This installation uses CPU after GPU discovery failed during setup.
    environment = dict(os.environ, OLLAMA_HOST='127.0.0.1:11434', OLLAMA_NO_CLOUD='1')
    if os.getenv('ORBIT_OLLAMA_CPU', 'true').lower() == 'true':
        environment.update(OLLAMA_VULKAN='false', CUDA_VISIBLE_DEVICES='-1', ROCR_VISIBLE_DEVICES='-1')
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with (settings.data_dir / 'ollama-out.log').open('a') as output, (settings.data_dir / 'ollama-error.log').open('a') as errors:
        subprocess.Popen([executable, 'serve'], env=environment, stdout=output, stderr=errors,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    print('Iniciando Ollama local. A primeira descoberta de hardware pode levar até 90 segundos.', flush=True)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if available():
            print('Ollama disponível.', flush=True)
            return
        time.sleep(1)
    raise RuntimeError('Ollama não respondeu em 90 segundos. Consulte Conta e fontes e os logs locais do runtime.')


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
