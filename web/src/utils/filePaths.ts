/**
 * 从文本中提取文件路径（匹配 Mac/iOS 端的 3 策略检测）
 */

const IMAGE_EXTENSIONS = new Set([
  'png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg', 'webp', 'ico', 'tiff', 'tif', 'heic', 'heif',
]);

export function extractFilePaths(text: string): string[] {
  const found = new Set<string>();

  // Strategy 1: 行级检测（允许空格）
  const lineRegex = /(?:^|\n)\s*(?:`{1,3})?\s*(\/[^\n]*?\/[^\n]*?\.[a-zA-Z0-9]{1,10})\s*(?:`{1,3})?\s*(?:\n|$)/g;
  let m: RegExpExecArray | null;
  while ((m = lineRegex.exec(text)) !== null) {
    const p = m[1].trim();
    if (validateFilePath(p)) found.add(p);
  }

  // Strategy 2: 内联路径（不含空格）
  const inlineRegex = /(?:^|[\s,;:'"(])(\/[^\s,;:'"()[\]{}]+\/[^\s,;:'"()[\]{}]+\.[a-zA-Z0-9]{1,10})(?=[\s,;:'")\].]|$)/gm;
  while ((m = inlineRegex.exec(text)) !== null) {
    const p = m[1].trim();
    if (validateFilePath(p)) found.add(p);
  }

  // Strategy 3: 反引号内路径（允许空格）
  const backtickRegex = /`(\/[^`\n]+\/[^`\n]+\.[a-zA-Z0-9]{1,10})`/g;
  while ((m = backtickRegex.exec(text)) !== null) {
    const p = m[1].trim();
    if (validateFilePath(p)) found.add(p);
  }

  return Array.from(found);
}

export function validateFilePath(path: string): boolean {
  if (!path.startsWith('/')) return false;
  const components = path.split('/').filter(Boolean);
  if (components.length < 2) return false;
  const lastDot = path.lastIndexOf('.');
  if (lastDot < 0) return false;
  const ext = path.slice(lastDot + 1).toLowerCase();
  if (!ext || ext.length > 10) return false;
  if (IMAGE_EXTENSIONS.has(ext)) return false;
  if (path.includes('://')) return false;
  if (/[[\]()]/.test(path)) return false;
  return true;
}

/**
 * 格式化文件大小
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/**
 * 根据扩展名返回图标 Emoji
 */
export function getFileIcon(ext: string): string {
  const map: Record<string, string> = {
    pdf: '📕', doc: '📘', docx: '📘', txt: '📄', md: '📝',
    xls: '📊', xlsx: '📊', csv: '📊',
    ppt: '📙', pptx: '📙',
    zip: '📦', rar: '📦', '7z': '📦', tar: '📦', gz: '📦',
    py: '🐍', js: '🟨', ts: '🔷', jsx: '⚛️', tsx: '⚛️',
    swift: '🍊', java: '☕', cpp: '⚙️', c: '⚙️', go: '🔵', rs: '🦀',
    html: '🌐', css: '🎨', json: '📋', xml: '📋', yaml: '📋', yml: '📋',
    mp3: '🎵', wav: '🎵', mp4: '🎬', mov: '🎬', avi: '🎬',
    sh: '💻', bash: '💻', zsh: '💻',
    sql: '🗃️', db: '🗃️', sqlite: '🗃️',
    log: '📜', env: '🔐', key: '🔑', pem: '🔑',
  };
  return map[ext.toLowerCase()] ?? '📄';
}
