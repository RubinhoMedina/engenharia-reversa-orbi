"""Configuration from environment and a literal local .env file."""
from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path=ROOT / '.env'):
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or not key.replace('_', '').isalnum():
            raise ValueError('Linha inválida no arquivo .env.')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def integer(name, default, minimum, maximum):
    try:
        result = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f'{name} deve ser inteiro.')
    if not minimum <= result <= maximum:
        raise ValueError(f'{name} fora do intervalo permitido.')
    return result


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    public_url: str = ''
    session_hours: int = 12
    push_subject: str = ''
    push_interval: int = 10

    @property
    def public_origin(self):
        return self.public_url.rstrip('/')

    @property
    def secure_cookie(self):
        return self.public_url.startswith('https://')

    @classmethod
    def from_env(cls):
        load_dotenv()
        public_url = os.getenv('PUBLIC_URL', '').strip().rstrip('/')
        if public_url:
            parsed = urlparse(public_url)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
                raise ValueError('PUBLIC_URL deve conter apenas protocolo, domínio e porta opcional.')
        return cls(Path(os.getenv('ORBIT_DATA_DIR') or ROOT / 'server' / 'data').resolve(), public_url, integer('SESSION_HOURS', 12, 1, 168), os.getenv('VAPID_SUBJECT', '').strip(), integer('PUSH_INTERVAL_SECONDS', 10, 2, 3600))

    def safe_status(self):
        return {'public_url': self.public_url, 'secure_cookie': self.secure_cookie, 'mode': 'public' if self.secure_cookie else 'local'}
