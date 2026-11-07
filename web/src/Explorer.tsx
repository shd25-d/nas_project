import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type DragEvent } from 'react';
import { ArrowDownToLine, ArrowUpFromLine, FileArchive, Check, ChevronRight, CircleAlert, Code2, FileText, FolderClosed, FolderPlus, Grid2X2, HardDrive, Image, List, LogOut, Menu, MoreHorizontal, MoveRight, Pencil, RefreshCw, Search, ShieldCheck, Trash2, UploadCloud, Video, X } from 'lucide-react';
import { api, archiveURL, bytes, contentURL, downloadArchive, downloadFile, upload } from './api';
import { Brand, Dialog, FileIcon, Spinner } from './components';
const Viewer = lazy(() => import('./Viewer'));
import type { Category, Entry, Listing, Session } from './types';

const categories = [
  { key: 'all', label: '전체 파일', icon: FolderClosed },
  { key: 'image', label: '사진', icon: Image },
  { key: 'document', label: '문서', icon: FileText },
  { key: 'video', label: '동영상 · 음악', icon: Video },
  { key: 'code', label: '코드 · 텍스트', icon: Code2 },
] as const;
const kindLabel: Record<string, string> = { folder: '폴더', image: '이미지', pdf: 'PDF 문서', docx: 'Word 문서', text: '코드 · 텍스트', video: '동영상', audio: '오디오', other: '파일' };
type Action = { type: 'folder' } | { type: 'rename' | 'move' | 'delete'; entry: Entry };
interface UploadItem { name: string; progress: number; status: 'waiting' | 'uploading' | 'done' | 'failed'; error?: string }

function ActionDialog({ action, path, onClose, onDone }: { action: Action; path: string; onClose: () => void; onDone: () => void }) {
  const entry = 'entry' in action ? action.entry : null;
  const [value, setValue] = useState(action.type === 'rename' ? entry!.name : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const title = { folder: '새 폴더', rename: '이름 변경', move: '파일 이동', delete: '파일 삭제' }[action.type];
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      if (action.type === 'folder') await api('/folders', { method: 'POST', body: JSON.stringify({ path, name: value }) });
      else if (action.type === 'delete') await api(`/entry?${new URLSearchParams({ path: entry!.path })}`, { method: 'DELETE' });
      else {
        const parent = action.type === 'rename' ? entry!.path.split('/').slice(0, -1).join('/') : value.trim().replace(/^\/+|\/+$/g, '');
        const name = action.type === 'rename' ? value : entry!.name;
        await api('/entry', { method: 'PATCH', body: JSON.stringify({ path: entry!.path, destination: [parent, name].filter(Boolean).join('/') }) });
      }
      onDone();
    } catch (reason) { setError((reason as Error).message); setBusy(false); }
  }
  return <Dialog title={title} onClose={onClose} busy={busy}><form onSubmit={submit} className="action-form">
    {action.type === 'delete' ? <><div className="delete-symbol"><Trash2 size={24} /></div><p><strong>{entry!.name}</strong>{entry!.is_dir ? ' 폴더와 그 안의 모든 파일을' : ' 파일을'} 영구 삭제할까요?</p><p className="muted">삭제한 파일은 복원할 수 없습니다.</p></> : <>
      {action.type === 'move' && <p className="muted"><strong>{entry!.name}</strong> 파일을 옮길 폴더를 입력하세요.</p>}
      <label htmlFor="action-value">{action.type === 'folder' ? '폴더 이름' : action.type === 'rename' ? '새 이름' : '대상 폴더 경로'}</label>
      <input id="action-value" autoFocus value={value} onChange={(event) => setValue(event.target.value)} maxLength={action.type === 'move' ? 4096 : 255} required={action.type !== 'move'} placeholder={action.type === 'move' ? '예: 사진/2026' : '이름을 입력하세요'} />
      <p className="field-hint">{action.type === 'move' ? '비워 두면 전체 파일의 최상위 폴더로 이동합니다. 대상 폴더는 미리 만들어 주세요.' : '같은 이름이 있으면 기존 항목을 덮어쓰지 않습니다.'}</p>
    </>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="dialog-actions"><button className="button secondary" type="button" onClick={onClose} disabled={busy}>취소</button><button className={`button ${action.type === 'delete' ? 'danger' : 'primary'}`} disabled={busy} type="submit">{busy ? <Spinner /> : { folder: '만들기', rename: '저장', move: '이동하기', delete: '영구 삭제' }[action.type]}</button></div>
  </form></Dialog>;
}

export default function Explorer({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [path, setPath] = useState(() => new URLSearchParams(location.search).get('folder') || '');
  const [category, setCategory] = useState<Category>('all');
  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('name');
  const [layout, setLayout] = useState<'list' | 'grid'>('list');
  const [viewer, setViewer] = useState<Entry | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [sidebar, setSidebar] = useState(false);
  const [drag, setDrag] = useState(false);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const activeUpload = useRef(false);
  const dragDepth = useRef(0);
  const requestId = useRef(0);
  const pathRef = useRef(path); pathRef.current = path;

  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    try {
      const data = await api<Listing>(`/files?${new URLSearchParams({ path: pathRef.current })}`);
      if (id === requestId.current) { setListing(data); setError(''); }
    } catch (reason) { if (id === requestId.current) setError((reason as Error).message); }
    finally { if (id === requestId.current) setLoading(false); }
  }, []);
  useEffect(() => { setListing(null); setSearch(''); void refresh(); }, [path, refresh]);
  useEffect(() => {
    const pop = () => { setPath(new URLSearchParams(location.search).get('folder') || ''); setViewer(null); };
    const closeMenu = (event: PointerEvent) => { if (!(event.target as Element).closest('.file-menu')) setMenu(null); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setMenu(null); setSidebar(false); } };
    window.addEventListener('popstate', pop); document.addEventListener('pointerdown', closeMenu); document.addEventListener('keydown', escape);
    return () => { window.removeEventListener('popstate', pop); document.removeEventListener('pointerdown', closeMenu); document.removeEventListener('keydown', escape); uploadController.current?.abort(); };
  }, []);
  function navigate(next: string) {
    if (next !== path) { history.pushState(null, '', next ? `/?${new URLSearchParams({ folder: next })}` : '/'); setPath(next); }
    setMenu(null); setSidebar(false); setCategory('all');
  }
  async function logout() {
    if (activeUpload.current) { setError('업로드를 완료하거나 취소한 뒤 로그아웃하세요.'); return; }
    try { await api('/logout', { method: 'POST' }); onLogout(); } catch (reason) { setError((reason as Error).message); }
  }
  async function startUpload(files: File[]) {
    if (activeUpload.current) { setError('진행 중인 업로드를 먼저 완료해 주세요.'); return; }
    if (!files.length) return;
    activeUpload.current = true; setUploading(true);
    const controller = new AbortController(); uploadController.current = controller;
    const targetPath = path;
    setUploads(files.map((file) => ({ name: file.name, progress: 0, status: 'waiting' })));
    const update = (index: number, changes: Partial<UploadItem>) => setUploads((current) => current.map((item, i) => i === index ? { ...item, ...changes } : item));
    for (let index = 0; index < files.length; index++) {
      if (controller.signal.aborted) { update(index, { status: 'failed', error: '업로드를 취소했습니다.' }); continue; }
      if (listing && files[index].size > listing.max_upload_bytes) { update(index, { status: 'failed', error: `파일 크기 제한: ${bytes(listing.max_upload_bytes)}` }); continue; }
      update(index, { status: 'uploading' });
      try { await upload(files[index], targetPath, (progress) => update(index, { progress }), controller.signal); update(index, { status: 'done', progress: 100 }); }
      catch (reason) { update(index, { status: 'failed', error: (reason as Error).message }); }
    }
    activeUpload.current = false; setUploading(false); uploadController.current = null;
    void refresh();
  }
  function drop(event: DragEvent) {
    event.preventDefault(); dragDepth.current = 0; setDrag(false);
    const directories = Array.from(event.dataTransfer.items).some((item) => item.webkitGetAsEntry?.()?.isDirectory);
    if (directories) { setError('폴더 업로드는 지원하지 않습니다. 폴더를 만든 뒤 파일을 올려 주세요.'); return; }
    void startUpload(Array.from(event.dataTransfer.files));
  }
  const entries = useMemo(() => {
    const filtered = (listing?.entries || []).filter((entry) => {
      const categoryMatch = category === 'all' || entry.is_dir ||
        (category === 'document' && ['pdf', 'docx'].includes(entry.kind)) ||
        (category === 'image' && entry.kind === 'image') ||
        (category === 'video' && ['video', 'audio'].includes(entry.kind)) ||
        (category === 'code' && entry.kind === 'text');
      return categoryMatch && entry.name.toLocaleLowerCase().includes(search.toLocaleLowerCase());
    });
    return filtered.sort((a, b) => Number(b.is_dir) - Number(a.is_dir) ||
      (sort === 'modified' ? b.modified - a.modified : sort === 'size' ? (b.size || 0) - (a.size || 0) : a.name.localeCompare(b.name, 'ko', { numeric: true })));
  }, [listing, category, search, sort]);
  const folderCount = listing?.entries.filter((entry) => entry.is_dir).length || 0;
  const fileCount = (listing?.entries.length || 0) - folderCount;
  const currentSize = listing?.entries.reduce((sum, entry) => sum + (entry.size || 0), 0) || 0;
  const usedPercent = listing?.storage.total ? Math.min(100, listing.storage.used / listing.storage.total * 100) : 0;
  const crumbs = path.split('/').filter(Boolean);

  return <div className="app-shell" onDragEnter={(event) => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); dragDepth.current++; setDrag(true); } }} onDragOver={(event) => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); }} onDragLeave={(event) => { event.preventDefault(); if (--dragDepth.current <= 0) setDrag(false); }} onDrop={drop}>
    {sidebar && <button className="sidebar-backdrop" aria-label="메뉴 닫기" onClick={() => setSidebar(false)} />}
    <aside className={`sidebar ${sidebar ? 'open' : ''}`}><div className="sidebar-brand"><Brand /><span className="private-label">PERSONAL STORAGE</span></div>
      <div className="workspace-label">MY WORKSPACE</div><nav className="category-nav" aria-label="파일 종류">{categories.map(({ key, label, icon: Icon }) => <button key={key} className={category === key ? 'active' : ''} onClick={() => { setCategory(key); setSidebar(false); if (key === 'all') navigate(''); }}><Icon size={19} strokeWidth={1.7} /><span>{label}</span>{key === 'all' && <span className="nav-count">{listing?.entries.length || 0}</span>}</button>)}</nav>
      <div className="sidebar-note"><div className="note-icon"><ShieldCheck size={21} strokeWidth={1.5} /></div><p>작지만 든든한<br /><strong>나만의 파일 보관함</strong></p><span>사진, 문서, 코드까지<br />필요할 때 언제든 꺼내보세요.</span></div>
      <div className="sidebar-bottom"><div className="storage-title"><HardDrive size={17} /><span>저장 공간</span><span>{Math.round(usedPercent)}%</span></div><div className="storage-bar"><span style={{ width: `${usedPercent}%` }} /></div><div className="storage-numbers">{listing ? <><strong>{bytes(listing.storage.free)}</strong> 사용 가능</> : '저장소 확인 중'}</div><div className="storage-caption">호스트 디스크 전체 기준</div><div className="owner-profile"><div className="avatar">{session.username.slice(0, 1).toUpperCase()}</div><div><strong>{session.username}</strong><span>개인 계정</span></div><button className="icon-button" aria-label="로그아웃" title="로그아웃" onClick={logout}><LogOut size={18} /></button></div></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="메뉴 열기" onClick={() => setSidebar(true)}><Menu size={23} /></button><span className="topbar-label">나의 작은 저장소</span></div><div className="topbar-right"><span className="private-badge"><span />개인 저장소</span><button className="icon-button refresh-button" onClick={() => void refresh()} aria-label="새로고침" disabled={loading}><RefreshCw size={18} className={loading ? 'spinning' : ''} /></button></div></header>
      <main className="main-content"><div className="page-heading"><div><div className="eyebrow">YOUR FILES, YOUR SPACE</div><h1>내 파일<span aria-hidden="true" className="heading-dot">.</span></h1><p>필요한 파일을 모으고, 편하게 꺼내보세요.</p></div><div className="page-actions"><button className="button secondary" aria-label="현재 폴더 ZIP 다운로드" title="현재 폴더 ZIP 다운로드" onClick={() => void downloadArchive(path).catch((reason) => setError(reason.message))}><FileArchive size={17} /><span>ZIP 다운로드</span></button><button className="button secondary" onClick={() => setAction({ type: 'folder' })}><FolderPlus size={17} />새 폴더</button><button className="button primary" onClick={() => input.current?.click()} disabled={uploading}><ArrowUpFromLine size={18} />업로드</button></div></div>
        <input ref={input} type="file" multiple className="hidden-file-input" aria-label="업로드할 파일 선택" onChange={(event) => { void startUpload(Array.from(event.target.files || [])); event.target.value = ''; }} />
        <section className="summary-cards" aria-label="현재 폴더 요약"><div className="summary-card"><span className="summary-icon green"><FolderClosed size={21} strokeWidth={1.5} /></span><div><span>현재 폴더의 파일</span><strong>{fileCount}<small>개</small></strong></div><span className="summary-decoration">FILES</span></div><div className="summary-card"><span className="summary-icon amber"><FolderPlus size={21} strokeWidth={1.5} /></span><div><span>하위 폴더</span><strong>{folderCount}<small>개</small></strong></div><span className="summary-decoration">FOLDERS</span></div><div className="summary-card"><span className="summary-icon blue"><HardDrive size={21} strokeWidth={1.5} /></span><div><span>현재 폴더의 파일 용량</span><strong className="size-value">{bytes(currentSize)}</strong></div><span className="summary-decoration">STORAGE</span></div></section>
        {error && <div className="error-banner" role="alert"><CircleAlert size={18} /><span>{error}</span><button className="icon-button" aria-label="오류 닫기" onClick={() => setError('')}><X size={16} /></button></div>}
        <section className="files-panel"><div className="files-toolbar"><div className="breadcrumbs" aria-label="현재 경로"><button onClick={() => navigate('')}>전체 파일</button>{crumbs.map((crumb, index) => <span key={index}><ChevronRight size={14} /><button onClick={() => navigate(crumbs.slice(0, index + 1).join('/'))}>{crumb}</button></span>)}</div><div className="file-controls"><div className="search-input"><Search size={17} /><input aria-label="현재 폴더 검색" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="현재 폴더에서 검색" />{search && <button className="icon-button" aria-label="검색 지우기" onClick={() => setSearch('')}><X size={14} /></button>}</div><select aria-label="정렬" value={sort} onChange={(event) => setSort(event.target.value)}><option value="name">이름순</option><option value="modified">최신순</option><option value="size">크기순</option></select><div className="view-toggle"><button className={layout === 'list' ? 'active' : ''} aria-label="목록 보기" aria-pressed={layout === 'list'} onClick={() => setLayout('list')}><List size={18} /></button><button className={layout === 'grid' ? 'active' : ''} aria-label="격자 보기" aria-pressed={layout === 'grid'} onClick={() => setLayout('grid')}><Grid2X2 size={17} /></button></div></div></div>
          {category !== 'all' && <div className="filter-note">{categories.find((item) => item.key === category)?.label} · 현재 폴더 기준<button onClick={() => setCategory('all')}>필터 해제 <X size={12} /></button></div>}
          {loading ? <div className="file-loading"><Spinner /><span>파일을 불러오고 있습니다</span></div> : entries.length === 0 ? <div className="empty-state"><span className="empty-symbol"><FolderClosed size={42} strokeWidth={1.15} /></span><h2>{search || category !== 'all' ? '찾는 파일이 없어요' : error ? '폴더를 열 수 없어요' : '첫 번째 파일을 담아보세요'}</h2><p>{search || category !== 'all' ? '검색어나 파일 종류를 바꿔보세요.' : error ? '경로와 접근 권한을 확인하거나 전체 파일로 돌아가세요.' : '파일을 이곳으로 끌어오거나 업로드 버튼을 눌러주세요.'}</p>{!search && category === 'all' && !error && <button className="button secondary" onClick={() => input.current?.click()} disabled={uploading}><ArrowUpFromLine size={17} />파일 업로드</button>}</div> : <div className={`file-list ${layout}`}>
            {layout === 'list' && <div className="file-table-heading"><span>이름</span><span>파일 크기</span><span>수정한 날짜</span><span /></div>}
            {entries.map((entry) => <div key={entry.path} className={`file-row ${menu === entry.path ? 'menu-open' : ''}`}>
              <button className="file-open" aria-label={`${entry.name} 열기`} onClick={() => entry.is_dir ? navigate(entry.path) : setViewer(entry)}><FileIcon kind={entry.kind} large={layout === 'grid'} /><span className="file-name"><strong>{entry.name}</strong><span>{kindLabel[entry.kind]}</span></span></button>
              <span className="file-size">{bytes(entry.size)}</span><span className="file-date">{new Date(entry.modified * 1000).toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' })}</span>
              <div className="file-menu"><button className="icon-button" aria-label={`${entry.name} 더 보기`} aria-expanded={menu === entry.path} onClick={() => setMenu(menu === entry.path ? null : entry.path)}><MoreHorizontal size={20} /></button>{menu === entry.path && <div className="file-popover">{entry.is_dir && <a href={archiveURL(entry.path)} download onClick={(event) => { event.preventDefault(); setMenu(null); void downloadArchive(entry.path).catch((reason) => setError(reason.message)); }}><FileArchive size={16} />ZIP 다운로드</a>}{!entry.is_dir && <a href={contentURL(entry.path, true)} download onClick={(event) => { event.preventDefault(); setMenu(null); void downloadFile(entry.path).catch((reason) => setError(reason.message)); }}><ArrowDownToLine size={16} />다운로드</a>}<button onClick={() => { setAction({ type: 'rename', entry }); setMenu(null); }}><Pencil size={16} />이름 변경</button><button onClick={() => { setAction({ type: 'move', entry }); setMenu(null); }}><MoveRight size={16} />이동</button><div className="menu-separator" /><button className="delete-action" onClick={() => { setAction({ type: 'delete', entry }); setMenu(null); }}><Trash2 size={16} />삭제</button></div>}</div>
            </div>)}
          </div>}
          <div className="files-footer"><span>{entries.length}개 항목{search ? ` · “${search}” 검색 결과` : ''}</span><span><UploadCloud size={14} />파일을 끌어다 놓아 업로드</span></div>
        </section>
        <footer className="workspace-footer"><span>조금 더 가볍게, 나만의 공간에.</span><span>moru · personal storage</span></footer>
      </main>
    </div>
    {drag && <div className="drop-overlay"><div><UploadCloud size={50} strokeWidth={1.2} /><h2>여기에 파일을 놓아주세요</h2><p>{path || '전체 파일'}에 업로드합니다</p></div></div>}
    {uploads.length > 0 && <section className="upload-panel" aria-label="업로드 상태" aria-live="polite"><div className="upload-heading"><span><UploadCloud size={18} />{uploading ? '파일을 올리고 있어요' : '업로드 결과'}</span><button className="icon-button" aria-label={uploading ? '업로드 취소' : '업로드 결과 닫기'} onClick={() => uploading ? uploadController.current?.abort() : setUploads([])}><X size={18} /></button></div><div className="upload-items">{uploads.map((item, index) => <div className={`upload-item ${item.status}`} key={index}><span className="upload-status-icon">{item.status === 'done' ? <Check size={17} /> : item.status === 'failed' ? <CircleAlert size={17} /> : <ArrowUpFromLine size={17} />}</span><div><strong>{item.name}</strong><span>{item.status === 'failed' ? item.error : item.status === 'done' ? '업로드 완료' : item.status === 'waiting' ? '대기 중' : item.progress === 100 ? '파일 저장 중…' : `${item.progress}%`}</span>{item.status === 'uploading' && <progress max={100} value={item.progress} />}</div></div>)}</div></section>}
    {viewer && <Suspense fallback={<div className="viewer-opening"><Spinner /></div>}><Viewer entry={viewer} onClose={() => setViewer(null)} /></Suspense>}
    {action && <ActionDialog key={action.type + ('entry' in action ? action.entry.path : '')} action={action} path={path} onClose={() => setAction(null)} onDone={() => { setAction(null); void refresh(); }} />}
  </div>;
}
