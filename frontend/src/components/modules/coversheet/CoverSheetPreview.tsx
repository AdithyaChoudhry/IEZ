/**
 * Excel-like interactive cover sheet canvas.
 * - Column letter headers (A, B, C…) + row numbers (1, 2, 3…)
 * - Click to select a single cell → value editor + formatting in side panel
 * - Shift+click to extend selection to a rectangle
 * - Merge / Unmerge selected cells
 * - Drag & resize images (fixed slots + unlimited custom)
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlignLeft, AlignCenter, AlignRight,
  AlignStartVertical, AlignCenterVertical, AlignEndVertical,
  Bold, Italic, Underline, WrapText, Shrink,
  ArrowUp, ArrowDown, ArrowLeft, ArrowRight,
  Image as ImageIcon, X, Lock, Unlock, Merge, Scissors,
} from 'lucide-react';
import type {
  CoverSheetLayout, ImagePlacement, ImageKey,
  CellOverride, LayoutCell, CustomImageSlot, MergeRange,
} from './types';
import { styleToCss } from './styleUtils';
import ImageOverlay from './ImageOverlay';

const SCALE = 0.62;
const ROW_HDR_W = 32; // px (screen-space, outside scaled canvas)
const COL_HDR_H = 18; // px

const FONT_LIST = [
  'Calibri', 'Arial', 'Times New Roman', 'Courier New', 'Verdana',
  'Georgia', 'Tahoma', 'Trebuchet MS', 'Impact', 'Comic Sans MS',
];

const FIXED_IMAGE_LABELS: Record<ImageKey, string> = {
  client_logo: 'Client Logo',
  pmc_logo: 'PMC Logo',
  wabag_logo: 'WABAG Logo',
  prepared_signature: 'Prepared Sig.',
  checked_signature: 'Checked Sig.',
  approved_signature: 'Approved Sig.',
};

// ── Column letter from 1-based index (A, B, ..., Z, AA, AB, ...) ─────────────
export function colLetter(n: number): string {
  let result = '';
  while (n > 0) {
    n--;
    result = String.fromCharCode(65 + (n % 26)) + result;
    n = Math.floor(n / 26);
  }
  return result;
}

interface Selection { minRow: number; maxRow: number; minCol: number; maxCol: number; }
interface PlacementState { x: number; y: number; width: number; height: number; }

interface Props {
  layout: CoverSheetLayout;
  images: Partial<Record<ImageKey, ImagePlacement>>;
  cellOverrides: Record<string, CellOverride>;
  onCellOverridesChange: (o: Record<string, CellOverride>) => void;
  imagePlacements: Partial<Record<ImageKey, PlacementState>>;
  onImagePlacementsChange: (p: Partial<Record<ImageKey, PlacementState>>) => void;
  customImages: CustomImageSlot[];
  onCustomImagesChange: (imgs: CustomImageSlot[]) => void;
  mergeRanges: MergeRange[];
  onMergeRangesChange: (r: MergeRange[]) => void;
  unmergeCoords: string[];
  onUnmergeCoordsChange: (c: string[]) => void;
  // Column width overrides (1-based col index → px) and row height overrides (1-based → px)
  colOverrides: Record<number, number>;
  onColOverridesChange: (o: Record<number, number>) => void;
  rowOverrides: Record<number, number>;
  onRowOverridesChange: (o: Record<number, number>) => void;
}

type ImageSel = { kind: 'fixed'; key: ImageKey } | { kind: 'custom'; id: string };

export default function CoverSheetPreview({
  layout, images,
  cellOverrides, onCellOverridesChange,
  imagePlacements, onImagePlacementsChange,
  customImages, onCustomImagesChange,
  mergeRanges, onMergeRangesChange,
  unmergeCoords, onUnmergeCoordsChange,
  colOverrides, onColOverridesChange,
  rowOverrides, onRowOverridesChange,
}: Props) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const [anchor, setAnchor] = useState<{ row: number; col: number } | null>(null);
  const [imageSel, setImageSel] = useState<ImageSel | null>(null);
  const [aspectLocks, setAspectLocks] = useState<Record<string, boolean>>({});
  const initKeys = useRef<Set<string>>(new Set());

  // Sync fixed image placements from preview API defaults
  useEffect(() => {
    const additions: Partial<Record<ImageKey, PlacementState>> = {};
    let changed = false;
    for (const [key, img] of Object.entries(images)) {
      if (!img) continue;
      if (!initKeys.current.has(key)) {
        initKeys.current.add(key);
        additions[key as ImageKey] = { x: img.x, y: img.y, width: img.width, height: img.height };
        changed = true;
      }
    }
    if (changed) onImagePlacementsChange({ ...imagePlacements, ...additions });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [images]);

  // ── Effective cells (with merge overrides) ──────────────────────────────────
  const effectiveCells = useMemo<LayoutCell[]>(() => {
    let cells: LayoutCell[] = layout.cells.map(c => ({ ...c }));

    // Apply unmerges: split template-merged cells back to individual cells
    const unmergeSet = new Set(unmergeCoords.map(r => r.split(':')[0]));
    const afterUnmerge: LayoutCell[] = [];
    for (const cell of cells) {
      if (unmergeSet.has(cell.coord) && (cell.rowspan > 1 || cell.colspan > 1)) {
        for (let r = cell.row; r < cell.row + cell.rowspan; r++) {
          for (let c = cell.col; c < cell.col + cell.colspan; c++) {
            afterUnmerge.push({
              ...cell, row: r, col: c,
              coord: `${colLetter(c)}${r}`,
              rowspan: 1, colspan: 1,
              value: r === cell.row && c === cell.col ? cell.value : '',
            });
          }
        }
      } else {
        afterUnmerge.push(cell);
      }
    }
    cells = afterUnmerge;

    // Apply custom merges
    for (const mr of mergeRanges) {
      const inRange = cells.filter(c =>
        c.row >= mr.minRow && c.row <= mr.maxRow &&
        c.col >= mr.minCol && c.col <= mr.maxCol
      );
      if (inRange.length === 0) continue;
      const master = inRange.reduce((a, b) =>
        a.row < b.row || (a.row === b.row && a.col < b.col) ? a : b
      );
      const remaining = cells.filter(c =>
        !(c.row >= mr.minRow && c.row <= mr.maxRow &&
          c.col >= mr.minCol && c.col <= mr.maxCol)
      );
      remaining.push({
        ...master,
        row: mr.minRow, col: mr.minCol,
        coord: `${colLetter(mr.minCol)}${mr.minRow}`,
        rowspan: mr.maxRow - mr.minRow + 1,
        colspan: mr.maxCol - mr.minCol + 1,
      });
      cells = remaining;
    }

    return cells;
  }, [layout.cells, mergeRanges, unmergeCoords]);

  // Build rendered grid (handles covered cells from rowspan/colspan)
  const cellGrid = useMemo(() => {
    const rowCount = layout.rows.length;
    const colCount = layout.cols.length;
    const grid: (LayoutCell | 'covered' | undefined)[][] = Array.from(
      { length: rowCount + 1 }, () => []
    );
    for (const cell of effectiveCells) {
      if (cell.row > rowCount || cell.col > colCount) continue;
      grid[cell.row][cell.col] = cell;
      for (let r = cell.row; r < cell.row + cell.rowspan && r <= rowCount; r++) {
        for (let c = cell.col; c < cell.col + cell.colspan && c <= colCount; c++) {
          if (r === cell.row && c === cell.col) continue;
          if (!grid[r]) grid[r] = [];
          grid[r][c] = 'covered';
        }
      }
    }
    return grid;
  }, [effectiveCells, layout.rows.length, layout.cols.length]);

  // ── Selection helpers ───────────────────────────────────────────────────────
  const isCellSelected = (cell: LayoutCell): boolean => {
    if (!selection) return false;
    const er = cell.row + cell.rowspan - 1;
    const ec = cell.col + cell.colspan - 1;
    return cell.row <= selection.maxRow && er >= selection.minRow &&
           cell.col <= selection.maxCol && ec >= selection.minCol;
  };

  const singleCell = useMemo<LayoutCell | null>(() => {
    if (!selection) return null;
    const inSel = effectiveCells.filter(c =>
      c.row >= selection.minRow && c.row + c.rowspan - 1 <= selection.maxRow &&
      c.col >= selection.minCol && c.col + c.colspan - 1 <= selection.maxCol
    );
    return inSel.length === 1 ? inSel[0] : null;
  }, [selection, effectiveCells]);

  const selectionCellCount = useMemo(() => {
    if (!selection) return 0;
    return (selection.maxRow - selection.minRow + 1) * (selection.maxCol - selection.minCol + 1);
  }, [selection]);

  const selectedIsMerged = singleCell
    ? (singleCell.rowspan > 1 || singleCell.colspan > 1)
    : false;

  const handleCellClick = (cell: LayoutCell, e: React.MouseEvent) => {
    setImageSel(null);
    const cellMaxRow = cell.row + cell.rowspan - 1;
    const cellMaxCol = cell.col + cell.colspan - 1;
    if (e.shiftKey && anchor) {
      setSelection({
        minRow: Math.min(anchor.row, cell.row),
        maxRow: Math.max(anchor.row, cellMaxRow),
        minCol: Math.min(anchor.col, cell.col),
        maxCol: Math.max(anchor.col, cellMaxCol),
      });
    } else {
      setAnchor({ row: cell.row, col: cell.col });
      setSelection({ minRow: cell.row, maxRow: cellMaxRow, minCol: cell.col, maxCol: cellMaxCol });
    }
  };

  // ── Cell value / formatting ─────────────────────────────────────────────────
  const selOverride = singleCell ? (cellOverrides[singleCell.coord] || {}) : null;
  const effAlign = singleCell ? { ...singleCell.style.alignment, ...selOverride?.alignment } : null;
  const effFont = singleCell ? { ...singleCell.style.font, ...selOverride?.font } : null;

  const updateCellOverride = (coord: string, patch: CellOverride) => {
    const cur = cellOverrides[coord] || {};
    onCellOverridesChange({
      ...cellOverrides,
      [coord]: {
        value: patch.value !== undefined ? patch.value : cur.value,
        alignment: { ...cur.alignment, ...patch.alignment },
        font: { ...cur.font, ...patch.font },
      },
    });
  };

  // ── Merge / Unmerge ─────────────────────────────────────────────────────────
  const mergeSelected = () => {
    if (!selection || selectionCellCount < 2) return;
    const id = `merge_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    onMergeRangesChange([...mergeRanges, {
      id,
      minRow: selection.minRow, maxRow: selection.maxRow,
      minCol: selection.minCol, maxCol: selection.maxCol,
    }]);
    setSelection(null); setAnchor(null);
  };

  const unmergeSelected = () => {
    if (!singleCell || !selectedIsMerged) return;
    const cell = singleCell;
    const endColLetter = colLetter(cell.col + cell.colspan - 1);
    const rangeStr = `${cell.coord}:${endColLetter}${cell.row + cell.rowspan - 1}`;

    // If it was a custom merge, remove it; else add to unmerge list for backend
    const customIdx = mergeRanges.findIndex(mr =>
      mr.minRow === cell.row && mr.minCol === cell.col &&
      mr.maxRow === cell.row + cell.rowspan - 1 && mr.maxCol === cell.col + cell.colspan - 1
    );
    if (customIdx >= 0) {
      onMergeRangesChange(mergeRanges.filter((_, i) => i !== customIdx));
    } else {
      if (!unmergeCoords.includes(cell.coord)) {
        onUnmergeCoordsChange([...unmergeCoords, rangeStr]);
      }
    }
    setSelection(null); setAnchor(null);
  };

  // ── Image placement ─────────────────────────────────────────────────────────
  const updateFixedPlacement = (key: ImageKey, next: PlacementState) =>
    onImagePlacementsChange({ ...imagePlacements, [key]: next });

  const updateCustomPlacement = (id: string, next: PlacementState) =>
    onCustomImagesChange(customImages.map(ci => ci.id === id ? { ...ci, placement: next } : ci));

  const nudgeFixed = (key: ImageKey, dx: number, dy: number) => {
    const p = imagePlacements[key]; if (!p) return;
    updateFixedPlacement(key, { ...p, x: p.x + dx, y: p.y + dy });
  };
  const nudgeCustom = (id: string, dx: number, dy: number) => {
    const ci = customImages.find(c => c.id === id); if (!ci) return;
    updateCustomPlacement(id, { ...ci.placement, x: ci.placement.x + dx, y: ci.placement.y + dy });
  };

  const removeCustom = (id: string) => {
    onCustomImagesChange(customImages.filter(c => c.id !== id));
    if (imageSel?.kind === 'custom' && imageSel.id === id) setImageSel(null);
  };

  // Effective column widths and row heights (apply user overrides)
  const effCols = layout.cols.map((w, i) => colOverrides[i + 1] ?? w);
  const effRows = layout.rows.map((h, i) => rowOverrides[i + 1] ?? h);
  const canvasW = effCols.reduce((a, b) => a + b, 0) * SCALE;
  const canvasH = effRows.reduce((a, b) => a + b, 0) * SCALE;
  const colCount = layout.cols.length;

  const selFixedKey = imageSel?.kind === 'fixed' ? imageSel.key : null;
  const selFixedP = selFixedKey ? imagePlacements[selFixedKey] : null;
  const selCustom = imageSel?.kind === 'custom' ? customImages.find(c => c.id === imageSel.id) : null;

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex gap-4">

      {/* ── Spreadsheet canvas area ── */}
      <div className="flex-1 overflow-auto min-w-0 rounded-xl" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
        <div style={{ padding: '8px' }}>

          {/* Column letter header row */}
          <div className="flex" style={{ marginLeft: ROW_HDR_W + 8 }}>
            {effCols.map((w, i) => (
              <div key={i}
                style={{
                  width: w * SCALE,
                  minWidth: w * SCALE,
                  height: COL_HDR_H,
                  fontSize: 9,
                  fontWeight: 600,
                  textAlign: 'center',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                  background: 'var(--s4)',
                  color: 'var(--t2)',
                  border: '1px solid var(--b2)',
                  boxSizing: 'border-box',
                  userSelect: 'none',
                }}>
                {colLetter(i + 1)}
              </div>
            ))}
          </div>

          {/* Row numbers + canvas */}
          <div className="flex">
            {/* Row number column */}
            <div style={{ width: ROW_HDR_W, flexShrink: 0 }}>
              {effRows.map((h, i) => (
                <div key={i}
                  style={{
                    width: ROW_HDR_W, height: h * SCALE,
                    fontSize: 9, fontWeight: 600,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'var(--s4)', color: 'var(--t2)',
                    border: '1px solid var(--b2)', boxSizing: 'border-box',
                    userSelect: 'none',
                  }}>
                  {i + 1}
                </div>
              ))}
            </div>

            {/* Data canvas */}
            <div style={{ position: 'relative', width: canvasW, height: canvasH, flexShrink: 0 }}>
              <div style={{
                position: 'absolute', top: 0, left: 0,
                width: effCols.reduce((a, b) => a + b, 0),
                height: effRows.reduce((a, b) => a + b, 0),
                transform: `scale(${SCALE})`, transformOrigin: 'top left',
              }}>
                <table style={{ borderCollapse: 'collapse', width: effCols.reduce((a, b) => a + b, 0), tableLayout: 'fixed' }}>
                  <colgroup>
                    {effCols.map((w, i) => <col key={i} style={{ width: `${w}px` }} />)}
                  </colgroup>
                  <tbody>
                    {effRows.map((h, rIdx) => {
                      const r = rIdx + 1;
                      return (
                        <tr key={r} style={{ height: `${h}px` }}>
                          {Array.from({ length: colCount }, (_, cIdx) => {
                            const c = cIdx + 1;
                            const entry = cellGrid[r]?.[c];
                            if (entry === 'covered' || entry === undefined) return null;
                            const cell = entry as LayoutCell;
                            const override = cellOverrides[cell.coord];
                            const displayValue = override?.value !== undefined ? override.value : cell.value;
                            const inSel = isCellSelected(cell);
                            const isActive = singleCell?.coord === cell.coord;
                            return (
                              <td key={c}
                                rowSpan={cell.rowspan} colSpan={cell.colspan}
                                onClick={e => handleCellClick(cell, e)}
                                title={`${cell.coord}${cell.value ? ': ' + cell.value : ''}`}
                                style={{
                                  ...styleToCss(cell.style, override),
                                  cursor: 'pointer',
                                  outline: isActive ? '2px solid #3b82f6' : inSel ? '1.5px solid #93c5fd' : undefined,
                                  background: inSel && !isActive
                                    ? 'rgba(59,130,246,0.08)'
                                    : (styleToCss(cell.style, override).backgroundColor as string) || 'transparent',
                                  position: 'relative',
                                }}>
                                {/* Merge indicator badge */}
                                {(cell.rowspan > 1 || cell.colspan > 1) && (
                                  <span style={{
                                    position: 'absolute', top: 1, right: 2,
                                    fontSize: 7, opacity: 0.4, color: '#6b7280', pointerEvents: 'none',
                                  }}>⊞</span>
                                )}
                                {displayValue}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {/* Fixed image overlays */}
                {(Object.entries(images) as [ImageKey, ImagePlacement][]).map(([key, img]) => {
                  if (!img?.data) return null;
                  const placement = imagePlacements[key]; if (!placement) return null;
                  const ratio = placement.width / placement.height;
                  return (
                    <ImageOverlay key={key}
                      x={placement.x} y={placement.y} width={placement.width} height={placement.height}
                      data={img.data} scale={SCALE}
                      selected={selFixedKey === key}
                      lockAspect={aspectLocks[key] ? ratio : null}
                      onSelect={() => { setImageSel({ kind: 'fixed', key }); setSelection(null); }}
                      onChange={next => updateFixedPlacement(key, next)} />
                  );
                })}

                {/* Custom image overlays */}
                {customImages.map(ci => {
                  const p = ci.placement;
                  const ratio = p.width / p.height;
                  return (
                    <ImageOverlay key={ci.id}
                      x={p.x} y={p.y} width={p.width} height={p.height}
                      data={ci.dataUrl.replace(/^data:image\/\w+;base64,/, '')}
                      scale={SCALE}
                      selected={selCustom?.id === ci.id}
                      lockAspect={aspectLocks[ci.id] ? ratio : null}
                      onSelect={() => { setImageSel({ kind: 'custom', id: ci.id }); setSelection(null); }}
                      onChange={next => updateCustomPlacement(ci.id, next)} />
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Side panel ── */}
      <div className="w-72 flex-shrink-0 space-y-3">

        {/* Merge / multi-select toolbar */}
        {selection && (
          <div className="rounded-xl p-3 space-y-2" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
            <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--t2)' }}>
              {singleCell ? `Cell ${singleCell.coord}` : `${selectionCellCount} cells selected (${selection.minRow}:${selection.maxRow} × ${colLetter(selection.minCol)}:${colLetter(selection.maxCol)})`}
            </p>
            <div className="flex gap-2">
              {selectionCellCount > 1 && !selectedIsMerged && (
                <button onClick={mergeSelected}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-bold"
                  style={{ background: 'rgba(59,130,246,0.1)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.3)' }}>
                  <Merge className="w-3.5 h-3.5" /> Merge Cells
                </button>
              )}
              {singleCell && selectedIsMerged && (
                <button onClick={unmergeSelected}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-bold"
                  style={{ background: 'rgba(245,158,11,0.08)', color: 'var(--gold)', border: '1px solid rgba(245,158,11,0.3)' }}>
                  <Scissors className="w-3.5 h-3.5" /> Unmerge
                </button>
              )}
              <button onClick={() => { setSelection(null); setAnchor(null); }}
                className="px-2 py-2 rounded-lg"
                style={{ background: 'var(--s3)', color: 'var(--t2)', border: '1px solid var(--b2)' }}>
                <X className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}

        {/* Cell value + formatting editor */}
        {singleCell && effAlign && effFont && (
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
            <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--b1)' }}>
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold" style={{ color: 'var(--em-lt)' }}>
                  {singleCell.coord}
                  {selectedIsMerged && (
                    <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full"
                      style={{ background: 'rgba(245,158,11,0.12)', color: 'var(--gold)' }}>
                      Merged ({singleCell.rowspan}×{singleCell.colspan})
                    </span>
                  )}
                </p>
                <button onClick={() => setSelection(null)} style={{ color: 'var(--t2)' }}>
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              {singleCell.value && (
                <p className="text-[10px] mt-0.5 truncate" style={{ color: 'var(--t2)' }}>
                  Template: {singleCell.value}
                </p>
              )}
            </div>

            <div className="p-4 space-y-3">
              {/* Value */}
              <div>
                <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--t2)' }}>Value</label>
                <textarea rows={2}
                  value={selOverride?.value !== undefined ? selOverride.value : singleCell.value}
                  onChange={e => updateCellOverride(singleCell.coord, { value: e.target.value })}
                  placeholder="Type value…"
                  className="w-full resize-none rounded-lg px-2.5 py-2 text-xs"
                  style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                {selOverride?.value !== undefined && selOverride.value !== singleCell.value && (
                  <button onClick={() => updateCellOverride(singleCell.coord, { value: undefined })}
                    className="text-[10px] mt-0.5" style={{ color: 'var(--rose)' }}>↩ Reset</button>
                )}
              </div>

              {/* Horizontal align */}
              <div className="flex gap-1">
                {[{ v: 'left', I: AlignLeft }, { v: 'center', I: AlignCenter }, { v: 'right', I: AlignRight }].map(({ v, I }) => (
                  <button key={v} onClick={() => updateCellOverride(singleCell.coord, { alignment: { horizontal: v } })}
                    className="flex-1 py-1.5 rounded-lg"
                    style={{ background: effAlign.horizontal === v ? 'var(--em)' : 'var(--s3)', color: effAlign.horizontal === v ? '#fff' : 'var(--t1)', border: '1px solid var(--b2)' }}>
                    <I className="w-3.5 h-3.5 mx-auto" />
                  </button>
                ))}
                <div className="w-px mx-0.5" style={{ background: 'var(--b2)' }} />
                {[{ v: 'top', I: AlignStartVertical }, { v: 'center', I: AlignCenterVertical }, { v: 'bottom', I: AlignEndVertical }].map(({ v, I }) => (
                  <button key={v} onClick={() => updateCellOverride(singleCell.coord, { alignment: { vertical: v } })}
                    className="flex-1 py-1.5 rounded-lg"
                    style={{ background: effAlign.vertical === v ? 'var(--em)' : 'var(--s3)', color: effAlign.vertical === v ? '#fff' : 'var(--t1)', border: '1px solid var(--b2)' }}>
                    <I className="w-3.5 h-3.5 mx-auto" />
                  </button>
                ))}
              </div>

              {/* Font family */}
              <div>
                <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--t2)' }}>Font</label>
                <select
                  value={selOverride?.font?.name ?? effFont.name ?? 'Calibri'}
                  onChange={e => updateCellOverride(singleCell.coord, { font: { name: e.target.value } })}
                  className="w-full px-2 py-1.5 rounded-lg text-xs"
                  style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}>
                  {FONT_LIST.map(f => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>

              {/* Font size + style + wrap/shrink */}
              <div className="flex items-center gap-1.5">
                <input type="number" min={6} max={72} value={effFont.size || 10}
                  onChange={e => updateCellOverride(singleCell.coord, { font: { size: +e.target.value || 10 } })}
                  className="w-14 px-2 py-1.5 rounded-lg text-xs text-center"
                  style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                <span className="text-[10px]" style={{ color: 'var(--t2)' }}>pt</span>
                {[{ I: Bold, k: 'bold' as const }, { I: Italic, k: 'italic' as const }, { I: Underline, k: 'underline' as const }].map(({ I, k }) => (
                  <button key={k} onClick={() => updateCellOverride(singleCell.coord, { font: { [k]: !(effFont as any)[k] } })}
                    className="p-1.5 rounded-lg"
                    style={{ background: (effFont as any)[k] ? 'var(--em)' : 'var(--s3)', color: (effFont as any)[k] ? '#fff' : 'var(--t1)', border: '1px solid var(--b2)' }}>
                    <I className="w-3.5 h-3.5" />
                  </button>
                ))}
                <div className="w-px mx-0.5" style={{ background: 'var(--b2)' }} />
                {[{ label: 'Wrap', I: WrapText, k: 'wrapText' as const }, { label: 'Fit', I: Shrink, k: 'shrinkToFit' as const }].map(({ label, I, k }) => (
                  <button key={k} onClick={() => updateCellOverride(singleCell.coord, { alignment: { [k]: !(effAlign as any)[k] } })}
                    className="flex items-center gap-0.5 px-1.5 py-1.5 rounded-lg text-[10px]"
                    style={{ background: (effAlign as any)[k] ? 'var(--em)' : 'var(--s3)', color: (effAlign as any)[k] ? '#fff' : 'var(--t1)', border: '1px solid var(--b2)' }}>
                    <I className="w-3 h-3" />{label}
                  </button>
                ))}
              </div>

              {/* Column width + Row height */}
              <div className="grid grid-cols-2 gap-2 pt-1" style={{ borderTop: '1px solid var(--b1)' }}>
                <div>
                  <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--t2)' }}>
                    Col {colLetter(singleCell.col)} Width (px)
                  </label>
                  <input type="number" min={10} max={600}
                    value={Math.round(effCols[singleCell.col - 1] ?? layout.cols[singleCell.col - 1])}
                    onChange={e => {
                      const v = Math.max(10, +e.target.value || 10);
                      onColOverridesChange({ ...colOverrides, [singleCell.col]: v });
                    }}
                    className="w-full px-2 py-1.5 rounded-lg text-xs text-center"
                    style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                </div>
                <div>
                  <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--t2)' }}>
                    Row {singleCell.row} Height (px)
                  </label>
                  <input type="number" min={5} max={400}
                    value={Math.round(effRows[singleCell.row - 1] ?? layout.rows[singleCell.row - 1])}
                    onChange={e => {
                      const v = Math.max(5, +e.target.value || 5);
                      onRowOverridesChange({ ...rowOverrides, [singleCell.row]: v });
                    }}
                    className="w-full px-2 py-1.5 rounded-lg text-xs text-center"
                    style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Fixed image panel */}
        {selFixedKey && selFixedP && (
          <ImagePanel label={FIXED_IMAGE_LABELS[selFixedKey]} placement={selFixedP}
            locked={!!aspectLocks[selFixedKey]}
            onToggleLock={() => setAspectLocks(p => ({ ...p, [selFixedKey]: !p[selFixedKey] }))}
            onChange={p => updateFixedPlacement(selFixedKey, p)}
            onNudge={(dx, dy) => nudgeFixed(selFixedKey, dx, dy)}
            onClose={() => setImageSel(null)} />
        )}

        {/* Custom image panel */}
        {selCustom && (
          <ImagePanel label={selCustom.label} placement={selCustom.placement}
            locked={!!aspectLocks[selCustom.id]}
            onToggleLock={() => setAspectLocks(p => ({ ...p, [selCustom.id]: !p[selCustom.id] }))}
            onChange={p => updateCustomPlacement(selCustom.id, p)}
            onNudge={(dx, dy) => nudgeCustom(selCustom.id, dx, dy)}
            onClose={() => setImageSel(null)}
            onDelete={() => removeCustom(selCustom.id)} />
        )}

        {/* Image list */}
        {(Object.values(images).some(i => i?.data) || customImages.length > 0) && (
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
            <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--b1)' }}>
              <ImageIcon className="w-3.5 h-3.5" style={{ color: 'var(--gold)' }} />
              <span className="text-xs font-bold" style={{ color: 'var(--t0)' }}>Images</span>
            </div>
            <div className="p-2 space-y-1 max-h-48 overflow-y-auto">
              {(Object.keys(FIXED_IMAGE_LABELS) as ImageKey[]).map(key => {
                const img = images[key]; if (!img?.data) return null;
                return (
                  <button key={key} onClick={() => { setImageSel({ kind: 'fixed', key }); setSelection(null); }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-left"
                    style={{ background: selFixedKey === key ? 'var(--em-dim)' : 'var(--s3)', color: selFixedKey === key ? 'var(--em-lt)' : 'var(--t1)', border: '1px solid transparent' }}>
                    <img src={`data:image/png;base64,${img.data}`} alt="" className="w-8 h-5 object-contain rounded" style={{ background: '#fff' }} />
                    {FIXED_IMAGE_LABELS[key]}
                  </button>
                );
              })}
              {customImages.map(ci => (
                <button key={ci.id} onClick={() => { setImageSel({ kind: 'custom', id: ci.id }); setSelection(null); }}
                  className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-left"
                  style={{ background: selCustom?.id === ci.id ? 'rgba(245,158,11,0.08)' : 'var(--s3)', color: selCustom?.id === ci.id ? 'var(--gold)' : 'var(--t1)', border: '1px solid transparent' }}>
                  <img src={ci.dataUrl} alt="" className="w-8 h-5 object-contain rounded" style={{ background: '#fff' }} />
                  <span className="flex-1 truncate">{ci.label}</span>
                  <X className="w-3 h-3 opacity-50 hover:opacity-100"
                    style={{ color: 'var(--rose)' }}
                    onClick={e => { e.stopPropagation(); removeCustom(ci.id); }} />
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!selection && !imageSel && (
          <div className="rounded-xl p-4 text-center" style={{ background: 'var(--s2)', border: '1px dashed var(--b2)' }}>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--t2)' }}>
              <strong style={{ color: 'var(--t1)' }}>Click</strong> a cell to edit value, font, size & alignment<br />
              <strong style={{ color: 'var(--t1)' }}>Shift+Click</strong> to select a range<br />
              Select 2+ cells → <strong style={{ color: 'var(--em-lt)' }}>Merge</strong><br />
              Click merged cell → <strong style={{ color: 'var(--gold)' }}>Unmerge</strong><br />
              Cell panel → set <strong style={{ color: 'var(--t1)' }}>Column Width</strong> &amp; <strong style={{ color: 'var(--t1)' }}>Row Height</strong>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Image panel ───────────────────────────────────────────────────────────────
function ImagePanel({
  label, placement, locked, onToggleLock, onChange, onNudge, onClose, onDelete,
}: {
  label: string;
  placement: PlacementState;
  locked: boolean;
  onToggleLock: () => void;
  onChange: (p: PlacementState) => void;
  onNudge: (dx: number, dy: number) => void;
  onClose: () => void;
  onDelete?: () => void;
}) {
  const ratio = placement.width / placement.height;
  return (
    <div className="rounded-xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
      <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--b1)' }}>
        <ImageIcon className="w-3.5 h-3.5" style={{ color: 'var(--gold)' }} />
        <p className="text-xs font-bold truncate flex-1" style={{ color: 'var(--t0)' }}>{label}</p>
        {onDelete && (
          <button onClick={onDelete} className="opacity-50 hover:opacity-100 mr-1" style={{ color: 'var(--rose)' }}>
            <X className="w-3.5 h-3.5" />
          </button>
        )}
        <button onClick={onClose} className="opacity-50 hover:opacity-100" style={{ color: 'var(--t2)' }}>
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="p-4 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          {([['X', 'x'], ['Y', 'y'], ['Width', 'width'], ['Height', 'height']] as [string, keyof PlacementState][]).map(([lbl, key]) => (
            <label key={key}>
              <span className="block text-[10px] mb-0.5" style={{ color: 'var(--t2)' }}>{lbl}</span>
              <input type="number" value={Math.round(placement[key])}
                onChange={e => {
                  const v = parseFloat(e.target.value) || 0;
                  if (key === 'width' && locked) onChange({ ...placement, width: v, height: Math.max(1, v / ratio) });
                  else if (key === 'height' && locked) onChange({ ...placement, height: v, width: Math.max(1, v * ratio) });
                  else onChange({ ...placement, [key]: v });
                }}
                className="w-full px-2 py-1.5 rounded-lg text-xs text-center"
                style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </label>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          {([[-5, 0, ArrowLeft], [5, 0, ArrowRight], [0, -5, ArrowUp], [0, 5, ArrowDown]] as [number, number, React.ElementType][]).map(([dx, dy, Ic]) => (
            <button key={`${dx}${dy}`} onClick={() => onNudge(dx, dy)}
              className="p-1.5 rounded-lg"
              style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t1)' }}>
              <Ic className="w-3 h-3" />
            </button>
          ))}
          <button onClick={onToggleLock}
            className="ml-auto flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px]"
            style={{ background: locked ? 'var(--em-dim)' : 'var(--s3)', color: locked ? 'var(--em-lt)' : 'var(--t2)', border: `1px solid ${locked ? 'rgba(59,130,246,0.3)' : 'var(--b2)'}` }}>
            {locked ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
            {locked ? 'Locked' : 'Free'}
          </button>
        </div>
      </div>
    </div>
  );
}
