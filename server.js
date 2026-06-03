import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const app = express();
const port = process.env.PORT || 3000;
const distDir = path.join(__dirname, 'dist');

app.disable('x-powered-by');
app.use(express.static(distDir, {
  etag: true,
  maxAge: '1h',
  setHeaders(res, filePath) {
    if (filePath.endsWith('index.html')) {
      res.setHeader('Cache-Control', 'no-store');
    }
  }
}));

app.get('/health', (_req, res) => {
  res.status(200).json({ ok: true, service: 'delta-agent' });
});

app.get('*', (_req, res) => {
  res.sendFile(path.join(distDir, 'index.html'));
});

app.listen(port, () => {
  console.log(`Delta Agent server listening on port ${port}`);
});
