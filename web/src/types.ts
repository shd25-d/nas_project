export type FileKind = 'folder' | 'pdf' | 'docx' | 'text' | 'image' | 'video' | 'audio' | 'other';
export interface Entry { name: string; path: string; is_dir: boolean; size: number | null; modified: number; kind: FileKind }
export interface Listing { path: string; entries: Entry[]; storage: { total: number; used: number; free: number }; max_upload_bytes: number }
export interface Session { username: string; csrf: string }
export type Preview = { kind: 'text'; text: string } | { kind: 'docx'; html: string };
export type Category = 'all' | 'image' | 'document' | 'video' | 'code';
