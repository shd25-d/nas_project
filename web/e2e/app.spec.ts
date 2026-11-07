import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

async function login(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByLabel('사용자 이름').fill('owner');
  await page.getByLabel('비밀번호', { exact: true }).fill('browser test password');
  await page.getByRole('button', { name: '로그인', exact: true }).click();
  await expect(page.getByRole('heading', { name: '내 파일', exact: true })).toBeVisible();
}

test('file lifecycle and previews on desktop', async ({ page }) => {
  await login(page);
  await page.getByRole('button', { name: 'welcome.py 열기' }).click();
  await expect(page.getByRole('dialog')).toContainText('Hello NAS');
  await page.getByRole('button', { name: '미리보기 닫기' }).click();
  await page.getByRole('button', { name: '새 폴더', exact: true }).click();
  await page.getByLabel('폴더 이름').fill('테스트 폴더');
  await page.getByRole('button', { name: '만들기', exact: true }).click();
  await page.getByRole('button', { name: '테스트 폴더 열기' }).click();
  await page.locator('input[type=file]').setInputFiles({ name: 'hello.txt', mimeType: 'text/plain', buffer: Buffer.from('휴대폰에서도 읽어요') });
  await expect(page.getByRole('button', { name: 'hello.txt 열기' })).toBeVisible();
  await page.getByRole('button', { name: 'hello.txt 열기' }).click();
  await expect(page.getByRole('dialog')).toContainText('휴대폰에서도 읽어요');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('link', { name: '원본 다운로드' }).click();
  expect((await downloadEvent).suggestedFilename()).toBe('hello.txt');
  await page.getByRole('button', { name: '미리보기 닫기' }).click();
  await page.getByRole('button', { name: 'hello.txt 더 보기' }).click();
  await page.getByRole('button', { name: '이름 변경', exact: true }).click();
  await page.getByLabel('새 이름').fill('renamed.txt');
  await page.getByRole('button', { name: '저장', exact: true }).click();
  await expect(page.getByRole('button', { name: 'renamed.txt 열기' })).toBeVisible();
  await page.getByRole('button', { name: 'renamed.txt 더 보기' }).click();
  await page.getByRole('button', { name: '이동', exact: true }).click();
  await page.getByLabel('대상 폴더 경로').fill('');
  await page.getByRole('button', { name: '이동하기', exact: true }).click();
  await page.getByRole('button', { name: '전체 파일', exact: true }).first().click();
  await expect(page.getByRole('button', { name: 'renamed.txt 열기' })).toBeVisible();
  await page.getByRole('button', { name: 'renamed.txt 더 보기' }).click();
  await page.getByRole('button', { name: '삭제', exact: true }).click();
  await page.getByRole('button', { name: '영구 삭제', exact: true }).click();
  await expect(page.getByRole('button', { name: 'renamed.txt 열기' })).toHaveCount(0);
  await page.getByRole('button', { name: '로그아웃' }).click();
  await expect(page.getByRole('button', { name: '로그인', exact: true })).toBeVisible();
});

test('mobile layout and unsupported preview', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '../artifacts/mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'unknown.bin 열기' }).click();
  await expect(page.getByRole('dialog')).toContainText('미리보기를 지원하지 않는 파일');
  await expect(page.getByRole('link', { name: '원본 다운로드' })).toBeVisible();
});

test('expired session returns to login', async ({ page }) => {
  await login(page);
  await page.context().clearCookies();
  await page.getByRole('button', { name: '새로고침' }).click();
  await expect(page.getByRole('button', { name: '로그인', exact: true })).toBeVisible();
});

test('expired session before download returns to login', async ({ page }) => {
  await login(page);
  await page.getByRole('button', { name: 'welcome.py 열기' }).click();
  await expect(page.getByRole('dialog')).toContainText('Hello NAS');
  await page.context().clearCookies();
  await page.getByRole('link', { name: '원본 다운로드' }).click();
  await expect(page.getByRole('button', { name: '로그인', exact: true })).toBeVisible();
});

test('folder menu downloads a ZIP including nested contents on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  const session = await (await page.request.get('/api/session')).json();
  const headers = { 'X-CSRF-Token': session.csrf };
  await page.request.post('/api/folders', { headers, data: { path: '', name: 'ZIP 자료' } });
  await page.request.post('/api/folders', { headers, data: { path: 'ZIP 자료', name: '하위' } });
  await page.request.post('/api/upload?path=ZIP%20%EC%9E%90%EB%A3%8C%2F%ED%95%98%EC%9C%84&name=hello.txt', { headers, data: 'nested ZIP content' });
  await page.getByRole('button', { name: '새로고침' }).click();
  await page.getByRole('button', { name: 'ZIP 자료 더 보기' }).click();
  const event = page.waitForEvent('download');
  await page.getByRole('link', { name: 'ZIP 다운로드', exact: true }).click();
  const download = await event;
  expect(download.suggestedFilename()).toBe('ZIP 자료.zip');
  expect(await download.failure()).toBeNull();
  const result = await readFile((await download.path())!);
  expect(result.subarray(0, 2).toString()).toBe('PK');
  expect(result.includes(Buffer.from('ZIP 자료/하위/hello.txt'))).toBe(true);
});

test('expired session before folder ZIP returns to login', async ({ page }) => {
  await login(page);
  await page.context().clearCookies();
  await page.getByRole('button', { name: '현재 폴더 ZIP 다운로드' }).click();
  await expect(page.getByRole('button', { name: '로그인', exact: true })).toBeVisible();
});

test('PDF, DOCX, image and audio render with local resources', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await login(page);
  await page.getByRole('button', { name: 'sample.pdf 열기' }).click();
  await expect(page.locator('canvas')).toBeVisible();
  await expect.poll(() => page.locator('canvas').evaluate((canvas: HTMLCanvasElement) => canvas.width)).toBeGreaterThan(100);
  await expect(page.getByRole('dialog')).toContainText('1 / 1');
  await page.getByRole('button', { name: '미리보기 닫기' }).click();
  await page.getByRole('button', { name: 'document.docx 열기' }).click();
  await expect(page.getByRole('dialog')).toContainText('Hello document');
  await page.getByRole('button', { name: '미리보기 닫기' }).click();
  await page.getByRole('button', { name: 'photo.png 열기' }).click();
  await expect.poll(() => page.getByRole('img', { name: 'photo.png' }).evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1);
  await page.getByRole('button', { name: '미리보기 닫기' }).click();
  await page.getByRole('button', { name: 'tone.wav 열기' }).click();
  await expect.poll(() => page.locator('audio').evaluate((audio: HTMLAudioElement) => audio.readyState)).toBeGreaterThanOrEqual(1);
  expect(errors).toEqual([]);
});

test('desktop layout', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  await expect(page.getByRole('button', { name: 'welcome.py 열기' })).toBeVisible();
  await page.screenshot({ path: '../artifacts/desktop.png', fullPage: true });
});

test('uploaded MP4 is seekable in the browser', async ({ page }) => {
  await login(page);
  await page.evaluate(async () => {
    const canvas = document.createElement('canvas'); canvas.width = 160; canvas.height = 90;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#234d3d'; ctx.fillRect(0, 0, 160, 90);
    const stream = canvas.captureStream(10);
    const recorder = new MediaRecorder(stream, { mimeType: 'video/mp4' });
    const chunks: BlobPart[] = [];
    const done = new Promise<Blob>((resolve) => { recorder.ondataavailable = (e) => chunks.push(e.data); recorder.onstop = () => resolve(new Blob(chunks, { type: 'video/mp4' })); });
    recorder.start();
    for (let i = 0; i < 5; i++) { ctx.fillRect(i, i, 20, 20); await new Promise((resolve) => setTimeout(resolve, 100)); }
    recorder.stop();
    const video = await done;
    stream.getTracks().forEach((track) => track.stop());
    const session = await (await fetch('/api/session')).json();
    const response = await fetch('/api/upload?name=clip.mp4', { method: 'POST', headers: { 'X-CSRF-Token': session.csrf }, body: video });
    if (!response.ok) throw new Error('Fixture video upload failed');
  });
  await page.getByRole('button', { name: '새로고침' }).click();
  await page.getByRole('button', { name: 'clip.mp4 열기' }).click();
  await expect.poll(() => page.locator('video').evaluate((video: HTMLVideoElement) => video.readyState)).toBeGreaterThanOrEqual(1);
  expect(await page.locator('video').evaluate((video: HTMLVideoElement) => video.duration)).toBeGreaterThan(0);
});
