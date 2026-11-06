import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Download, FileQuestion, Minus, Plus, AlertCircle } from 'lucide-react';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';
import * as pdfjs from 'pdfjs-dist';
import workerURL from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import 'highlight.js/styles/github.css';
import { api, bytes, contentURL, downloadFile } from './api';
import { Dialog, FileIcon, Spinner } from './components';
import type { Entry, Preview } from './types';

pdfjs.GlobalWorkerOptions.workerSrc = workerURL;

function PDFView({ path }: { path: string }) {
  const [document, setDocument] = useState<pdfjs.PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState('');
  const canvas = useRef<HTMLCanvasElement>(null);
  const area = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(160, entry.contentRect.width - 32)));
    observer.observe(area.current!);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let active = true;
    const task = pdfjs.getDocument({ url: contentURL(path), withCredentials: true,
      cMapUrl: '/pdfjs/cmaps/', cMapPacked: true, standardFontDataUrl: '/pdfjs/standard_fonts/', wasmUrl: '/pdfjs/wasm/' });
    task.promise.then((doc) => { if (active) setDocument(doc); }).catch(() => {
      if (active) { setError('PDF를 열지 못했습니다. 손상되었거나 암호가 설정된 파일일 수 있습니다.'); void api('/session').catch(() => {}); }
    });
    task.onPassword = () => { if (active) setError('암호가 설정된 PDF는 다운로드해서 확인하세요.'); void task.destroy(); };
    return () => { active = false; void task.destroy(); };
  }, [path]);
  useEffect(() => {
    if (!document || !canvas.current) return;
    let active = true;
    let render: pdfjs.RenderTask | null = null;
    document.getPage(page).then((pdfPage) => {
      if (!active || !canvas.current) return;
      const base = pdfPage.getViewport({ scale: 1 });
      const scale = Math.min(width / base.width, 1.5) * zoom;
      const viewport = pdfPage.getViewport({ scale });
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const target = canvas.current;
      target.width = Math.floor(viewport.width * ratio);
      target.height = Math.floor(viewport.height * ratio);
      target.style.width = `${viewport.width}px`;
      target.style.height = `${viewport.height}px`;
      render = pdfPage.render({ canvas: target, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] });
      return render.promise;
    }).catch((reason) => { if (active && reason?.name !== 'RenderingCancelledException') setError('PDF 페이지를 표시하지 못했습니다.'); });
    return () => { active = false; render?.cancel(); };
  }, [document, page, zoom, width]);
  return <div className="pdf-view">
    <div className="pdf-toolbar"><button className="icon-button" aria-label="이전 페이지" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft size={18} /></button>
      <span>{page} / {document?.numPages ?? '…'}</span><button className="icon-button" aria-label="다음 페이지" disabled={!document || page >= document.numPages} onClick={() => setPage(page + 1)}><ChevronRight size={18} /></button>
      <i /><button className="icon-button" aria-label="축소" disabled={zoom <= 0.5} onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}><Minus size={17} /></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" aria-label="확대" disabled={zoom >= 3} onClick={() => setZoom(Math.min(3, zoom + 0.25))}><Plus size={17} /></button></div>
    <div className="pdf-pages" ref={area}>{error ? <div className="preview-error"><AlertCircle /><p>{error}</p></div> : <>{!document && <Spinner />}<canvas ref={canvas} aria-label={`PDF ${page}페이지`} /></>}</div>
  </div>;
}

function DocumentView({ entry }: { entry: Entry }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api<Preview>(`/preview?${new URLSearchParams({ path: entry.path })}`, { signal: controller.signal })
      .then(setPreview).catch((reason) => { if (reason.name !== 'AbortError') setError(reason.message); });
    return () => controller.abort();
  }, [entry.path]);
  if (error) return <div className="preview-error"><AlertCircle /><p>{error}</p></div>;
  if (!preview) return <div className="preview-loading"><Spinner /><p>파일을 불러오고 있습니다</p></div>;
  if (preview.kind === 'docx') return <div className="docx-area"><div className="preview-note">내용 중심 미리보기 · 원본 문서와 배치가 다를 수 있습니다</div><article className="docx-page" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(preview.html, { FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'form', 'input'], FORBID_ATTR: ['style'] }) }} /></div>;
  const aliases: Record<string, string> = { py: 'python', cpp: 'cpp', h: 'cpp', hpp: 'cpp', js: 'javascript', jsx: 'javascript', ts: 'typescript', tsx: 'typescript', sh: 'bash', md: 'markdown', yml: 'yaml', html: 'xml', rs: 'rust', cs: 'csharp' };
  const extension = entry.name.split('.').pop()?.toLowerCase() ?? '';
  const language = aliases[extension] ?? extension;
  const highlighted = preview.text.length <= 200_000 && hljs.getLanguage(language)
    ? hljs.highlight(preview.text, { language, ignoreIllegals: true }).value : null;
  return <div className="code-view"><div className="code-meta"><span>{extension.toUpperCase() || 'TEXT'}</span><span>UTF-8 · 읽기 전용</span></div><div className="code-scroll"><pre className="line-numbers" aria-hidden="true">{preview.text.split('\n').map((_, i) => i + 1).join('\n')}</pre><pre className="code-content">{highlighted ? <code dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(highlighted) }} /> : <code>{preview.text}</code>}</pre></div></div>;
}

function MediaView({ entry }: { entry: Entry }) {
  const [error, setError] = useState(false);
  const failed = () => { setError(true); void api('/session').catch(() => {}); };
  if (error) return <div className="preview-error"><AlertCircle /><p>이 파일을 표시하지 못했습니다.<br />브라우저가 지원하지 않는 형식이나 코덱일 수 있습니다. 원본을 다운로드하세요.</p></div>;
  return <div className={`media-view media-${entry.kind}`}>
    {entry.kind === 'image' && <img src={contentURL(entry.path)} alt={entry.name} onError={failed} />}
    {entry.kind === 'video' && <video src={contentURL(entry.path)} controls playsInline preload="metadata" onError={failed}>동영상 재생을 지원하지 않는 브라우저입니다.</video>}
    {entry.kind === 'audio' && <><FileIcon kind="audio" large /><h3>{entry.name}</h3><audio src={contentURL(entry.path)} controls preload="metadata" onError={failed} /></>}
  </div>;
}

export default function Viewer({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const [downloadError, setDownloadError] = useState('');
  return <Dialog title={entry.name} onClose={onClose} className="viewer-dialog">
    <div className="viewer-body">
      {entry.kind === 'pdf' ? <PDFView path={entry.path} /> :
        ['text', 'docx'].includes(entry.kind) ? <DocumentView entry={entry} /> :
          ['image', 'video', 'audio'].includes(entry.kind) ? <MediaView entry={entry} /> :
            <div className="unsupported"><FileQuestion size={48} strokeWidth={1.3} /><h3>미리보기를 지원하지 않는 파일</h3><p>원본을 다운로드해서 확인해 주세요.</p></div>}
    </div>
    {downloadError && <p className="form-error" role="alert">{downloadError}</p>}
    <div className="viewer-footer"><span>{bytes(entry.size)}<span className="footer-date"> · {new Date(entry.modified * 1000).toLocaleDateString('ko-KR')}</span></span><a className="button primary" href={contentURL(entry.path, true)} download onClick={(event) => { event.preventDefault(); setDownloadError(''); void downloadFile(entry.path).catch((reason) => setDownloadError(reason.message)); }}><Download size={17} />원본 다운로드</a></div>
  </Dialog>;
}
