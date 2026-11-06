from pathlib import PurePosixPath

TEXT = {'py', 'cpp', 'c', 'h', 'hpp', 'js', 'jsx', 'ts', 'tsx', 'json', 'md', 'txt', 'log',
        'css', 'html', 'xml', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'sh', 'sql', 'rs', 'go', 'java', 'csv', 'dockerfile'}
IMAGES = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif', 'webp': 'image/webp'}
VIDEO = {'mp4': 'video/mp4', 'webm': 'video/webm'}
AUDIO = {'mp3': 'audio/mpeg', 'wav': 'audio/wav', 'ogg': 'audio/ogg'}


def extension(path):
    name = PurePosixPath(path).name.lower()
    return name.rsplit('.', 1)[-1]


def kind(path):
    ext = extension(path)
    if ext == 'pdf':
        return 'pdf'
    if ext == 'docx':
        return 'docx'
    if ext in IMAGES:
        return 'image'
    if ext in VIDEO:
        return 'video'
    if ext in AUDIO:
        return 'audio'
    if ext in TEXT:
        return 'text'
    return 'other'


def media_type(path):
    return {**IMAGES, **VIDEO, **AUDIO, 'pdf': 'application/pdf'}.get(extension(path), 'application/octet-stream')
