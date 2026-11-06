from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass
class Settings:
    files_dir: Path = field(default_factory=lambda: Path(os.getenv('NAS_FILES_DIR', 'data/files')))
    app_dir: Path = field(default_factory=lambda: Path(os.getenv('NAS_APP_DIR', 'data/app')))
    static_dir: Path = field(default_factory=lambda: Path(os.getenv('NAS_STATIC_DIR', 'web/dist')))
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv('NAS_MAX_UPLOAD_BYTES', str(10 * 1024 ** 3))))
    session_seconds: int = field(default_factory=lambda: int(os.getenv('NAS_SESSION_SECONDS', '604800')))
    secure_cookie: bool = field(default_factory=lambda: os.getenv('NAS_SECURE_COOKIE', 'false').lower() == 'true')

    def __post_init__(self):
        self.files_dir = Path(self.files_dir).absolute()
        self.app_dir = Path(self.app_dir).absolute()
        self.static_dir = Path(self.static_dir).absolute()
        if self.max_upload_bytes <= 0 or self.session_seconds <= 0:
            raise ValueError('Upload and session limits must be positive')
