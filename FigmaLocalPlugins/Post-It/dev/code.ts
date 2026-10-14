const KEY = 'postit';
const FONT = 'Noto Sans JP';
const PLACEHOLDER = 'Enter Text...';
const DEFAULT_LABEL = 'memo';

// miro の付箋カラーを参考にしたプリセット。先頭が初期値。
const PRESETS = [
  { name: 'Yellow', hex: 'FCFF9E' },
  { name: 'Orange', hex: 'FF9D48' },
  { name: 'Green', hex: 'D5F692' },
  { name: 'Cyan', hex: '67C6C0' },
  { name: 'Blue', hex: 'A6CCF5' },
  { name: 'Violet', hex: 'C6A2D2' },
  { name: 'Pink', hex: 'FFCEE0' },
  { name: 'Red', hex: 'F0939D' },
];
const PRESET_HEXES = PRESETS.map((p) => p.hex);

function solid(hex: string): SolidPaint {
  const n = parseInt(hex, 16);
  return { type: 'SOLID', color: { r: (n >> 16) / 255, g: ((n >> 8) & 255) / 255, b: (n & 255) / 255 } };
}

function toHex(paint: Paint | undefined): string | null {
  if (!paint || paint.type !== 'SOLID') return null;
  const { r, g, b } = paint.color;
  return [r, g, b].map((v) => Math.round(v * 255).toString(16).padStart(2, '0')).join('').toUpperCase();
}

function today(): string {
  const d = new Date();
  const pad = (v: number) => String(v).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function text(name: string, chars: string, size: number, color: string, style = 'Regular'): TextNode {
  const t = figma.createText();
  t.name = name;
  t.fontName = { family: FONT, style };
  t.characters = chars;
  t.fontSize = size;
  t.fills = [solid(color)];
  t.lineHeight = { unit: 'AUTO' };
  t.letterSpacing = { unit: 'PERCENT', value: 0 };
  t.textAlignHorizontal = 'LEFT';
  t.textAlignVertical = 'TOP';
  return t;
}

function hugFrame(name: string, mode: 'HORIZONTAL' | 'VERTICAL'): FrameNode {
  const f = figma.createFrame();
  f.name = name;
  f.layoutMode = mode;
  f.primaryAxisSizingMode = 'AUTO';
  f.counterAxisSizingMode = 'AUTO';
  f.fills = [];
  f.clipsContent = false;
  return f;
}

async function avatarFill(): Promise<Paint> {
  const url = figma.currentUser?.photoUrl;
  if (url) {
    try {
      const img = await figma.createImageAsync(url);
      return { type: 'IMAGE', imageHash: img.hash, scaleMode: 'FILL' };
    } catch {
      // 取得できなければグレーの丸で代替
    }
  }
  return solid('DDDDDD');
}

async function create(label: string, body: string, hex: string) {
  const postit = hugFrame('post-it', 'VERTICAL');
  postit.primaryAxisAlignItems = 'SPACE_BETWEEN';
  postit.paddingLeft = 24;
  postit.paddingTop = 40;
  postit.paddingRight = 24;
  postit.paddingBottom = 24;
  postit.resize(320, 160);
  postit.layoutSizingHorizontal = 'FIXED';
  postit.layoutSizingVertical = 'HUG';
  postit.minWidth = 320;
  postit.minHeight = 160;
  postit.fills = [solid(hex)];
  postit.effects = [
    { type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.15 }, offset: { x: 0, y: 2 }, radius: 6, spread: 0, visible: true, blendMode: 'NORMAL' },
  ];
  postit.setPluginData(KEY, '1');

  const variant = hugFrame('variant', 'HORIZONTAL');
  variant.paddingLeft = variant.paddingRight = 12;
  variant.paddingTop = variant.paddingBottom = 4;
  variant.cornerRadius = 12;
  variant.fills = [solid('000000')];
  variant.appendChild(text('label', label || DEFAULT_LABEL, 12, 'FFFFFF', 'Bold'));
  postit.appendChild(variant);
  variant.layoutPositioning = 'ABSOLUTE';
  variant.constraints = { horizontal: 'MIN', vertical: 'MIN' };
  variant.x = 24;
  variant.y = -11;

  const note = text('note', body || PLACEHOLDER, 16, '000000');
  postit.appendChild(note);
  note.layoutSizingHorizontal = 'FILL';
  note.textAutoResize = 'HEIGHT';

  const info = hugFrame('info', 'HORIZONTAL');
  info.primaryAxisAlignItems = 'SPACE_BETWEEN';
  info.counterAxisAlignItems = 'CENTER';
  postit.appendChild(info);
  info.layoutSizingHorizontal = 'FILL';
  info.appendChild(text('date', today(), 12, '666666'));

  const account = hugFrame('AccountInfo', 'HORIZONTAL');
  account.itemSpacing = 8;
  account.counterAxisAlignItems = 'CENTER';
  const icon = figma.createEllipse();
  icon.name = 'accountIcon';
  icon.resize(32, 32);
  icon.fills = [await avatarFill()];
  account.appendChild(icon);
  account.appendChild(text('accountName', figma.currentUser?.name ?? 'Unknown', 12, '666666'));
  info.appendChild(account);

  const c = figma.viewport.center;
  postit.x = Math.round(c.x - postit.width / 2);
  postit.y = Math.round(c.y - postit.height / 2);
  figma.currentPage.appendChild(postit);
  figma.currentPage.selection = [postit];
}

function selectedPostIts(): FrameNode[] {
  const found = new Set<FrameNode>();
  for (const n of figma.currentPage.selection) {
    let cur: BaseNode | null = n;
    while (cur && cur.type !== 'PAGE') {
      if (cur.type === 'FRAME' && cur.getPluginData(KEY) === '1') {
        found.add(cur);
        break;
      }
      cur = cur.parent;
    }
  }
  return [...found];
}

function onSelection() {
  const postits = selectedPostIts();
  const colors = new Set(postits.map((p) => (p.fills !== figma.mixed ? toHex(p.fills[0]) : null)));
  figma.ui.postMessage({ type: 'selection', count: postits.length, color: colors.size === 1 ? [...colors][0] : null });
}

figma.showUI(__html__, { width: 280, height: 420, themeColors: true });
figma.ui.postMessage({ type: 'init', presets: PRESETS });

figma.ui.onmessage = async (msg: { type: string; label?: string; body?: string; color: string }) => {
  if (!PRESET_HEXES.includes(msg.color)) return; // プリセット以外の色は受け付けない
  if (msg.type === 'create') {
    await Promise.all(['Regular', 'Bold'].map((style) => figma.loadFontAsync({ family: FONT, style })));
    await create((msg.label ?? '').trim(), msg.body ?? '', msg.color);
  } else if (msg.type === 'recolor') {
    for (const p of selectedPostIts()) p.fills = [solid(msg.color)];
  }
  onSelection();
};

figma.on('selectionchange', onSelection);
onSelection();
