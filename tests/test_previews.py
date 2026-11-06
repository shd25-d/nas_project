from io import BytesIO
import zipfile

from .test_files import upload


def make_docx(text='Hello NAS', extra=None):
    out = BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>')
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return out.getvalue()


def test_text_preview_escapes_nothing_into_html(signed):
    upload(signed, 'code.py', b'<script>evil()</script>\nprint(1)')
    result = signed.get('/api/preview?path=code.py')
    assert result.status_code == 200
    assert result.json() == {'kind': 'text', 'text': '<script>evil()</script>\nprint(1)'}


def test_preview_rejects_binary_or_large_text(signed, settings):
    upload(signed, 'binary.txt', b'\x00\xff\x80')
    assert signed.get('/api/preview?path=binary.txt').status_code == 415
    (settings.files_dir / 'large.txt').write_bytes(b'x' * (2 * 1024 * 1024 + 1))
    assert signed.get('/api/preview?path=large.txt').status_code == 413


def test_docx_content_preview(signed):
    upload(signed, 'document.docx', make_docx())
    result = signed.get('/api/preview?path=document.docx')
    assert result.status_code == 200, result.text
    assert result.json()['kind'] == 'docx'
    assert '<p>Hello NAS</p>' in result.json()['html']


def test_docx_html_and_entities_remain_inert(signed):
    upload(signed, 'hostile.docx', make_docx('&lt;script&gt;alert(1)&lt;/script&gt;'))
    result = signed.get('/api/preview?path=hostile.docx')
    assert result.status_code == 200
    assert '<script>' not in result.json()['html']
    upload(signed, 'entity.docx', make_docx(extra={'word/evil.xml': '<!DOCTYPE x [<!ENTITY x "boom">]><x/>'}))
    assert signed.get('/api/preview?path=entity.docx').status_code == 422


def test_docx_corruption_and_zip_expansion_rejected(signed):
    upload(signed, 'broken.docx', b'not a zip')
    assert signed.get('/api/preview?path=broken.docx').status_code == 422
    upload(signed, 'expanded.docx', make_docx(extra={'word/large.xml': 'x' * (33 * 1024 * 1024)}))
    assert signed.get('/api/preview?path=expanded.docx').status_code == 413


def test_unknown_preview_is_download_only(signed):
    upload(signed, 'unknown.bin', b'123')
    assert signed.get('/api/preview?path=unknown.bin').status_code == 415
