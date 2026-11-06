import { useEffect, useId, useRef, type ReactNode } from 'react';
import { File, FileCode2, FileImage, FileText, Folder, Film, Music2, X } from 'lucide-react';
import type { FileKind } from './types';

export function Brand({ small = false }: { small?: boolean }) {
  return <div className={`brand ${small ? 'small' : ''}`}><span className="brand-symbol" aria-hidden="true"><svg viewBox="0 0 48 48"><path d="M10 34V20a7 7 0 0 1 14 0v8-8a7 7 0 0 1 14 0v14" /></svg></span><span>moru<span className="brand-dot">.</span></span></div>;
}

export function FileIcon({ kind, large = false }: { kind: FileKind; large?: boolean }) {
  const Icon = { folder: Folder, pdf: FileText, docx: FileText, text: FileCode2, image: FileImage, video: Film, audio: Music2, other: File }[kind];
  return <span className={`file-icon kind-${kind} ${large ? 'large' : ''}`}><Icon size={large ? 30 : 21} strokeWidth={1.65} /></span>;
}

export function Dialog({ title, children, onClose, className = '', busy = false }: { title: string; children: ReactNode; onClose: () => void; className?: string; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => { dialog.close(); };
  }, []);
  return <dialog ref={ref} className={`dialog ${className}`} aria-labelledby={id}
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}
    onClick={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div className="dialog-heading"><h2 id={id}>{title}</h2><button className="icon-button" disabled={busy} onClick={onClose} aria-label={className.includes('viewer') ? '미리보기 닫기' : '닫기'}><X size={21} /></button></div>
    {children}
  </dialog>;
}

export function Spinner() { return <span className="spinner" aria-label="불러오는 중" />; }
