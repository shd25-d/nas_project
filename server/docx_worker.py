"""Bounded DOCX conversion worker. Receives an already authenticated file descriptor."""
import base64
from io import BytesIO
import json
import os
import resource
import sys
import zipfile


class PreviewFailure(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def convert(fd):
    import mammoth
    import nh3

    with os.fdopen(fd, 'rb') as descriptor:
        raw = descriptor.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise PreviewFailure(413, '문서가 미리보기 제한을 초과했습니다.')
    # Mammoth interprets fileobj.name as a filesystem path; fdopen.name is an int.
    with BytesIO(raw) as source:
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(i.file_size for i in entries) > 32 * 1024 * 1024:
                raise PreviewFailure(413, '문서의 압축 해제 크기가 미리보기 제한을 초과했습니다.')
            for entry in entries:
                if entry.filename.endswith(('.xml', '.rels')):
                    data = archive.read(entry)
                    # Reject declarations, including UTF-16 representations, before XML parsing.
                    flat = data.replace(b'\x00', b'').upper()
                    if b'<!DOCTYPE' in flat or b'<!ENTITY' in flat:
                        raise PreviewFailure(422, '지원하지 않는 XML 선언이 포함된 문서입니다.')
        source.seek(0)

        @mammoth.images.img_element
        def image(element):
            if element.content_type not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
                return {}
            with element.open() as picture:
                data = picture.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                return {}
            return {'src': 'data:' + element.content_type + ';base64,' + base64.b64encode(data).decode('ascii')}

        html = mammoth.convert_to_html(source, convert_image=image, external_file_access=False).value
    if len(html.encode('utf-8')) > 5 * 1024 * 1024:
        raise PreviewFailure(413, '변환한 문서가 미리보기 제한을 초과했습니다.')

    def attribute(tag, name, value):
        if tag == 'img' and name == 'src':
            return value if value.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,',
                                              'data:image/gif;base64,', 'data:image/webp;base64,')) else None
        return value

    safe = nh3.clean(html, tags={'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'u', 's',
                                'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'br',
                                'blockquote', 'pre', 'code', 'a', 'img', 'sup', 'sub', 'hr'},
                     attributes={'a': {'href', 'id'}, 'img': {'src', 'alt'}, 'td': {'colspan', 'rowspan'},
                                 'th': {'colspan', 'rowspan'}, '*': {'id'}},
                     url_schemes={'http', 'https', 'mailto', 'data'}, attribute_filter=attribute,
                     link_rel='noopener noreferrer nofollow')
    return {'kind': 'docx', 'html': safe}


def main():
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
        if sys.platform == 'linux':
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        print(json.dumps(convert(int(sys.argv[1]))))
    except PreviewFailure as error:
        print(json.dumps({'error': error.message, 'status': error.status}))
    except Exception:
        print(json.dumps({'error': '문서를 읽을 수 없습니다. 손상되었거나 암호화된 파일일 수 있습니다.', 'status': 422}))


if __name__ == '__main__':
    main()
