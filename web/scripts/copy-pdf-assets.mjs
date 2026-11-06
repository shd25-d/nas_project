import { cp, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

for (const name of ['cmaps', 'standard_fonts', 'wasm']) {
  const source = fileURLToPath(new URL(`../node_modules/pdfjs-dist/${name}`, import.meta.url));
  const destination = fileURLToPath(new URL(`../public/pdfjs/${name}`, import.meta.url));
  await mkdir(destination, { recursive: true });
  await cp(source, destination, { recursive: true });
}
