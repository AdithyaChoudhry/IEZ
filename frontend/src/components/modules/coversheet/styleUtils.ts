import type { CellStyle, CellOverride } from './types';

const BORDER_WIDTHS: Record<string, string> = {
  thin: '1px',
  medium: '2px',
  thick: '3px',
  hair: '1px',
  double: '3px',
};

function borderCss(side: { style: string; color: string } | null): string {
  if (!side) return 'none';
  const width = BORDER_WIDTHS[side.style] || '1px';
  const variant = side.style === 'double' ? 'double' : 'solid';
  return `${width} ${variant} ${side.color || '#000000'}`;
}

function verticalAlign(v: string | null): string {
  if (v === 'center') return 'middle';
  if (v === 'top') return 'top';
  if (v === 'bottom') return 'bottom';
  return 'middle';
}

/** Merge a cell's base style with any user-applied alignment/font overrides. */
export function mergeStyle(style: CellStyle, override?: CellOverride) {
  return {
    font: { ...style.font, ...(override?.font || {}) },
    alignment: { ...style.alignment, ...(override?.alignment || {}) },
    fill: style.fill,
    border: style.border,
  };
}

export function styleToCss(style: CellStyle, override?: CellOverride): React.CSSProperties {
  const merged = mergeStyle(style, override);
  const { font, alignment, fill, border } = merged;

  return {
    fontFamily: font.name || 'Arial',
    fontSize: `${font.size || 10}pt`,
    fontWeight: font.bold ? 'bold' : 'normal',
    fontStyle: font.italic ? 'italic' : 'normal',
    textDecoration: font.underline ? 'underline' : 'none',
    color: font.color || '#000000',
    textAlign: (alignment.horizontal as React.CSSProperties['textAlign']) || 'left',
    verticalAlign: verticalAlign(alignment.vertical),
    whiteSpace: alignment.wrapText ? 'pre-wrap' : 'pre',
    overflow: alignment.shrinkToFit ? 'hidden' : 'visible',
    backgroundColor: fill || 'transparent',
    borderTop: borderCss(border.top),
    borderRight: borderCss(border.right),
    borderBottom: borderCss(border.bottom),
    borderLeft: borderCss(border.left),
    padding: '2px',
    boxSizing: 'border-box',
    wordBreak: 'break-word',
  };
}
