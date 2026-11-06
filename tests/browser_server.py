"""Isolated fixture server for real browser tests; never uses user storage."""
import os
from pathlib import Path
import tempfile
import base64
import struct
import wave

import uvicorn

from server.auth import create_owner
from server.config import Settings
from server.main import create_app
from tests.test_previews import make_docx


def sample_pdf():
    stream = b'BT /F1 24 Tf 50 100 Td (Hello NAS) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 180] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    result, offsets = b'%PDF-1.4\n', [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(result)
    result += b'xref\n0 6\n0000000000 65535 f \n'
    result += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return result + f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='moru-e2e-') as temporary:
        root = Path(temporary)
        project = Path(__file__).resolve().parents[1]
        settings = Settings(files_dir=root / 'files', app_dir=root / 'app', static_dir=project / 'web/dist')
        create_owner(settings, 'owner', 'browser test password')
        app = create_app(settings)
        (settings.files_dir / 'welcome.py').write_text('print("Hello NAS")\n')
        (settings.files_dir / 'unknown.bin').write_bytes(b'\x00\x01')
        (settings.files_dir / 'document.docx').write_bytes(make_docx('Hello document'))
        (settings.files_dir / 'sample.pdf').write_bytes(sample_pdf())
        (settings.files_dir / 'photo.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1kAAAAASUVORK5CYII='))
        with wave.open(str(settings.files_dir / 'tone.wav'), 'wb') as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(struct.pack('<h', 0) * 8000)
        uvicorn.run(app, host='127.0.0.1', port=8765)
