import { useEffect, useState, type FormEvent } from 'react';
import { ArrowRight, Folder, FileText, Image, Film, LockKeyhole, Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { api, setCSRF } from './api';
import { Brand, Spinner } from './components';
import Explorer from './Explorer';
import type { Session } from './types';

function Login({ onLogin, expired }: { onLogin: (session: Session) => void; expired: boolean }) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<{ configured: boolean }>('/status').then((value) => setConfigured(value.configured)).catch(() => setError('서버에 연결할 수 없습니다. 연결을 확인해 주세요.')); }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true);
    try { onLogin(await api<Session>('/login', { method: 'POST', body: JSON.stringify({ username, password }) })); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="login-layout"><section className="login-story"><Brand /><div className="story-content"><div className="eyebrow">A LITTLE SPACE, ALL YOURS</div><h1>당신의 파일에,<br />당신만의 공간을.</h1><p>일상의 기록부터 소중한 순간까지.<br />나의 작은 저장소, 모루에 담아두세요.</p><div className="file-art" aria-hidden="true"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-file art-doc"><FileText size={30} /><span>나의 기록.docx</span><i /><i /></div><div className="art-file art-photo"><Image size={42} /><span>소중한 순간.jpg</span></div><div className="art-folder"><Folder size={76} strokeWidth={1.1} /><span>my little space</span></div><div className="art-small"><Film size={25} /></div></div></div><div className="story-bottom"><span className="tiny-dot" />내가 보관하고, 내가 관리하는 파일</div></section>
    <main className="login-main"><div className="mobile-brand"><Brand /></div><form className="login-form" onSubmit={submit}><div className="login-lock"><LockKeyhole size={23} /></div><div className="eyebrow">WELCOME TO YOUR SPACE</div><h2>다시 만나 반가워요.</h2><p className="muted">로그인하고 나의 파일을 만나보세요.</p>
      {configured === false ? <div className="setup-notice"><h3>첫 계정을 만들어 주세요</h3><p>서버 터미널에서 다음 명령을 실행한 뒤 새로고침하세요.</p><code>docker compose exec nas python -m server.cli create-owner</code></div> : <>
        <label htmlFor="username">사용자 이름</label><input id="username" name="username" autoComplete="username" required maxLength={64} value={username} onChange={(e) => setUsername(e.target.value)} placeholder="사용자 이름을 입력하세요" />
        <label htmlFor="password">비밀번호</label><div className="password-input"><input id="password" name="password" type={visible ? 'text' : 'password'} autoComplete="current-password" required maxLength={1024} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="비밀번호를 입력하세요" /><button type="button" className="icon-button" aria-label={visible ? '비밀번호 숨기기' : '비밀번호 표시'} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>
        {(error || expired) && <p className="form-error" role="alert">{error || '로그인이 만료되었습니다. 다시 로그인하세요.'}</p>}
        <button className="button primary login-submit" disabled={busy || configured === null} type="submit">{busy ? <Spinner /> : <>로그인<ArrowRight size={18} /></>}</button>
      </>}
      <div className="login-footnote"><ShieldCheck size={17} /><span>개인 계정으로 사용하는 나만의 저장소</span></div></form><footer className="login-footer">moru · personal storage</footer></main>
  </div>;
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    api<Session>('/session').then((value) => { setCSRF(value.csrf); setSession(value); }).catch(() => {}).finally(() => setLoading(false));
    const unauthorized = () => { setSession((previous) => { if (previous) setExpired(true); return null; }); setCSRF(''); };
    window.addEventListener('nas:unauthorized', unauthorized);
    return () => window.removeEventListener('nas:unauthorized', unauthorized);
  }, []);
  if (loading) return <div className="app-loading"><Brand /><Spinner /></div>;
  return session ? <Explorer session={session} onLogout={() => { setSession(null); setCSRF(''); setExpired(false); }} /> : <Login expired={expired} onLogin={(value) => { setCSRF(value.csrf); setSession(value); setExpired(false); }} />;
}
