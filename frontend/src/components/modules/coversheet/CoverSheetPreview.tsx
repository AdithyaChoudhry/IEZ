/**
 * Canvas-first interactive cover sheet preview.
 * – Click any cell to edit its value directly
 * – Alignment / font controls update in real time
 * – Fixed images (from preview API) + unlimited custom images can be dragged & resized
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlignLeft, AlignCenter, AlignRight,
  AlignStartVertical, AlignCenterVertical, AlignEndVertical,
  Bold, Italic, Underline, WrapText, Shrink,
  ArrowUp, ArrowDown, ArrowLeft, ArrowRight,
  Image as ImageIcon, X, Lock, Unlock,
} from 'lucide-react';
import type { CoverSheetLayout, ImagePlacement, ImageKey, CellOverride, LayoutCell, CustomImageSlot } from './types';
import { styleToCss } from './styleUtils';
import ImageOverlay from './ImageOverlay';

const SCALE = 0.62;

const FIXED_IMAGE_LABELS: Record<ImageKey, string> = {
  client_logo: 'Client Logo',
  pmc_logo: 'PMC Logo',
  wabag_logo: 'WABAG Logo',
  prepared_signature: 'Prepared Signature',
  checked_signature: 'Checked Signature',
  approved_signature: 'Approved Signature',
};

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
}

type SelectionKind = { kind: 'cell'; cell: LayoutCell } | { kind: 'fixed'; key: ImageKey } | { kind: 'custom'; id: string } | null;

export default function CoverSheetPreview({
  layout, images,
  cellOverrides, onCellOverridesChange,
  imagePlacements, onImagePlacementsChange,
  customImages, onCustomImagesChange,
}: Props) {
  const [selection, setSelection] = useState<SelectionKind>(null);
  const [aspectLocks, setAspectLocks] = useState<Record<string, boolean>>({});
  const initializedKeys = useRef<Set<string>>(new Set());

  // Initialize fixed image placements from preview API defaults
  useEffect(() => {
    const additions: Partial<Record<ImageKey, PlacementState>> = {};
    let changed = false;
    for (const [key, img] of Object.entries(images)) {
      if (!img) continue;
      if (!initializedKeys.current.has(key)) {
        initializedKeys.current.add(key);
        additions[key as ImageKey] = { x: img.x, y: img.y, width: img.width, height: img.height };
        changed = true;
      }
    }
    if (changed) onImagePlacementsChange({ ...imagePlacements, ...additions });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [images]);

  // Build cell grid (handles merges)
  const cellGrid = useMemo(() => {
    const grid: (LayoutCell | 'covered' | undefined)[][] = [];
    for (let r = 0; r <= layout.rows.length; r++) grid.push([]);
    for (const cell of layout.cells) {
      grid[cell.row][cell.col] = cell;
      for (let r = cell.row; r < cell.row + cell.rowspan; r++) {
        for (let c = cell.col; c < cell.col + cell.colspan; c++) {
          if (r === cell.row && c === cell.col) continue;
          if (!grid[r]) grid[r] = [];
          grid[r][c] = 'covered';
        }
      }
    }
    return grid;
  }, [layout]);

  // ── Helpers ────────────────────────────────────────────────────────────────
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
    if (selection?.kind === 'custom' && selection.id === id) setSelection(null);
  };

  const toggleAspect = (key: string) => setAspectLocks(prev => ({ ...prev, [key]: !prev[key] }));

  // ── Derived state ──────────────────────────────────────────────────────────
  const selCell = selection?.kind === 'cell' ? selection.cell : null;
  const selOverride = selCell ? (cellOverrides[selCell.coord] || {}) : null;
  const effAlign = selCell ? { ...selCell.style.alignment, ...selOverride?.alignment } : null;
  const effFont = selCell ? { ...selCell.style.font, ...selOverride?.font } : null;

  const selFixedKey = selection?.kind === 'fixed' ? selection.key : null;
  const selFixedPlacement = selFixedKey ? imagePlacements[selFixedKey] : null;

  const selCustom = selection?.kind === 'custom' ? customImages.find(c => c.id === selection.id) : null;

  const canvasW = layout.width * SCALE;
  const canvasH = layout.height * SCALE;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col lg:flex-row gap-4">

      {/* ── Canvas ── */}
      <div className="flex-1 overflow-auto rounded-xl p-3"
        style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
        <div style={{ position: 'relative', width: canvasW, height: canvasH }}>
          <div style={{
            position: 'absolute', top: 0, left: 0,
            width: layout.width, height: layout.height,
            transform: `scale(${SCALE})`, transformOrigin: 'top left',
          }}>
            {/* Grid */}
            <table style={{ borderCollapse: 'collapse', width: layout.width, tableLayout: 'fixed' }}>
              <colgroup>
                {layout.cols.map((w, i) => <col key={i} style={{ width: `${w}px` }} />)}
              </colgroup>
              <tbody>
                {layout.rows.map((h, rIdx) => {
                  const r = rIdx + 1;
                  return (
                    <tr key={r} style={{ height: `${h}px` }}>
                      {layout.cols.map((_, cIdx) => {
                        const c = cIdx + 1;
                        const entry = cellGrid[r]?.[c];
                        if (entry === 'covered' || entry === undefined) return null;
                        const cell = entry as LayoutCell;
                        const override = cellOverrides[cell.coord];
                        const displayValue = override?.value !== undefined ? override.value : cell.value;
                        const isSelected = selCell?.coord === cell.coord;
                        return (
                          <td
                            key={c}
                            rowSpan={cell.rowspan}
                            colSpan={cell.colspan}
                            onClick={() => setSelection({ kind: 'cell', cell })}
                            title={`Cell ${cell.coord}${cell.value ? ': ' + cell.value : ''}`}
                            style={{
                              ...styleToCss(cell.style, override),
                              cursor: 'pointer',
                              outline: isSelected ? '2px solid #3b82f6' : undefined,
                              position: 'relative',
                            }}
                          >
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
              const placement = imagePlacements[key];
              if (!placement) return null;
              const ratio = placement.width / placement.height;
              return (
                <ImageOverlay key={key}
                  x={placement.x} y={placement.y} width={placement.width} height={placement.height}
                  data={img.data} scale={SCALE}
                  selected={selFixedKey === key}
                  lockAspect={aspectLocks[key] ? ratio : null}
                  onSelect={() => setSelection({ kind: 'fixed', key })}
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
                  onSelect={() => setSelection({ kind: 'custom', id: ci.id })}
                  onChange={next => updateCustomPlacement(ci.id, next)} />
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Side Panel ── */}
      <div className="w-full lg:w-80 space-y-3 flex-shrink-0">

        {/* Hint when nothing selected */}
        {!selection && (
          <div className="rounded-xl p-4 text-center"
            style={{ background: 'var(--s3)', border: '1px dashed var(--b2)' }}>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>
              Click any cell to edit its value or formatting.<br />
              Click an image to reposition or resize it.
            </p>
          </div>
        )}

        {/* ── Cell editor ── */}
        {selCell && effAlign && effFont && (
          <div className="rounded-xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
            <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--b1)' }}>
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold" style={{ color: 'var(--em-lt)' }}>Cell {selCell.coord}</p>
                <button onClick={() => setSelection(null)} style={{ color: 'var(--t2)' }} className="opacity-60 hover:opacity-100">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              {selCell.value && <p className="text-[10px] mt-0.5 truncate" style={{ color: 'var(--t2)' }}>Template: {selCell.value}</p>}
            </div>

            <div className="p-4 space-y-4">
              {/* Value override */}
              <div>
                <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>
                  Cell Value
                </label>
                <textarea
                  rows={3}
                  value={selOverride?.value !== undefined ? selOverride.value : selCell.value}
                  onChange={e => updateCellOverride(selCell.coord, { value: e.target.value })}
                  placeholder="Type value here…"
                  className="w-full resize-none rounded-lg px-2.5 py-2 text-xs"
                  style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}
                />
                {selOverride?.value !== undefined && selOverride.value !== selCell.value && (
                  <button onClick={() => updateCellOverride(selCell.coord, { value: undefined })}
                    className="text-[10px] mt-1" style={{ color: 'var(--rose)' }}>
                    ↩ Reset to template value
                  </button>
                )}
              </div>

              {/* Horizontal alignment */}
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Horizontal</p>
                <div className="flex gap-1">
                  {[
                    { v: 'left', icon: AlignLeft },
                    { v: 'center', icon: AlignCenter },
                    { v: 'right', icon: AlignRight },
                  ].map(({ v, icon: Icon }) => (
                    <button key={v}
                      onClick={() => updateCellOverride(selCell.coord, { alignment: { horizontal: v } })}
                      className="p-2 rounded-lg flex-1"
                      style={{
                        background: effAlign.horizontal === v ? 'var(--em)' : 'var(--s3)',
                        color: effAlign.horizontal === v ? '#fff' : 'var(--t1)',
                        border: '1px solid var(--b2)',
                      }}>
                      <Icon className="w-3.5 h-3.5 mx-auto" />
                    </button>
                  ))}
                </div>
              </div>

              {/* Vertical alignment */}
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Vertical</p>
                <div className="flex gap-1">
                  {[
                    { v: 'top', icon: AlignStartVertical },
                    { v: 'center', icon: AlignCenterVertical },
                    { v: 'bottom', icon: AlignEndVertical },
                  ].map(({ v, icon: Icon }) => (
                    <button key={v}
                      onClick={() => updateCellOverride(selCell.coord, { alignment: { vertical: v } })}
                      className="p-2 rounded-lg flex-1"
                      style={{
                        background: effAlign.vertical === v ? 'var(--em)' : 'var(--s3)',
                        color: effAlign.vertical === v ? '#fff' : 'var(--t1)',
                        border: '1px solid var(--b2)',
                      }}>
                      <Icon className="w-3.5 h-3.5 mx-auto" />
                    </button>
                  ))}
                </div>
              </div>

              {/* Wrap / Shrink */}
              <div className="flex gap-1.5">
                {[
                  { label: 'Wrap', icon: WrapText, key: 'wrapText' as const },
                  { label: 'Shrink', icon: Shrink, key: 'shrinkToFit' as const },
                ].map(({ label, icon: Icon, key }) => (
                  <button key={key}
                    onClick={() => updateCellOverride(selCell.coord, { alignment: { [key]: !(effAlign as any)[key] } })}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium flex-1 justify-center"
                    style={{
                      background: (effAlign as any)[key] ? 'var(--em)' : 'var(--s3)',
                      color: (effAlign as any)[key] ? '#fff' : 'var(--t1)',
                      border: '1px solid var(--b2)',
                    }}>
                    <Icon className="w-3 h-3" />{label}
                  </button>
                ))}
              </div>

              {/* Font size */}
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Font Size</p>
                <div className="flex items-center gap-2">
                  <input type="number" min={6} max={72}
                    value={effFont.size || 10}
                    onChange={e => updateCellOverride(selCell.coord, { font: { size: +e.target.value || 10 } })}
                    className="w-20 px-2 py-1.5 rounded-lg text-xs text-center"
                    style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                  <span className="text-xs" style={{ color: 'var(--t2)' }}>pt</span>
                  <div className="flex gap-1 ml-auto">
                    {[
                      { icon: Bold, key: 'bold' as const },
                      { icon: Italic, key: 'italic' as const },
                      { icon: Underline, key: 'underline' as const },
                    ].map(({ icon: Icon, key }) => (
                      <button key={key}
                        onClick={() => updateCellOverride(selCell.coord, { font: { [key]: !(effFont as any)[key] } })}
                        className="p-2 rounded-lg"
                        style={{
                          background: (effFont as any)[key] ? 'var(--em)' : 'var(--s3)',
                          color: (effFont as any)[key] ? '#fff' : 'var(--t1)',
                          border: '1px solid var(--b2)',
                        }}>
                        <Icon className="w-3.5 h-3.5" />
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── Fixed image controls ── */}
        {selFixedKey && selFixedPlacement && (
          <ImagePanel
            label={FIXED_IMAGE_LABELS[selFixedKey]}
            placement={selFixedPlacement}
            locked={!!aspectLocks[selFixedKey]}
            onToggleLock={() => toggleAspect(selFixedKey)}
            onChange={p => updateFixedPlacement(selFixedKey, p)}
            onNudge={(dx, dy) => nudgeFixed(selFixedKey, dx, dy)}
            onClose={() => setSelection(null)}
          />
        )}

        {/* ── Custom image controls ── */}
        {selCustom && (
          <ImagePanel
            label={selCustom.label}
            placement={selCustom.placement}
            locked={!!aspectLocks[selCustom.id]}
            onToggleLock={() => toggleAspect(selCustom.id)}
            onChange={p => updateCustomPlacement(selCustom.id, p)}
            onNudge={(dx, dy) => nudgeCustom(selCustom.id, dx, dy)}
            onClose={() => setSelection(null)}
            onDelete={() => removeCustom(selCustom.id)}
          />
        )}

        {/* ── Image list (all) ── */}
        <div className="rounded-xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
          <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--b1)' }}>
            <ImageIcon className="w-3.5 h-3.5" style={{ color: 'var(--gold)' }} />
            <span className="text-xs font-bold" style={{ color: 'var(--t0)' }}>
              Images ({Object.values(images).filter(i => i?.data).length + customImages.length})
            </span>
          </div>
          <div className="p-3 space-y-1.5 max-h-56 overflow-y-auto">
            {/* Fixed images */}
            {(Object.keys(FIXED_IMAGE_LABELS) as ImageKey[]).map(key => {
              const img = images[key];
              if (!img?.data) return null;
              return (
                <button key={key}
                  onClick={() => setSelection({ kind: 'fixed', key })}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-all text-left"
                  style={{
                    background: selFixedKey === key ? 'var(--em-dim)' : 'var(--s3)',
                    border: `1px solid ${selFixedKey === key ? 'rgba(59,130,246,0.4)' : 'transparent'}`,
                    color: selFixedKey === key ? 'var(--em-lt)' : 'var(--t1)',
                  }}>
                  <img src={`data:image/png;base64,${img.data}`} alt="" className="w-8 h-5 object-contain rounded flex-shrink-0"
                    style={{ background: '#fff' }} />
                  <span className="truncate">{FIXED_IMAGE_LABELS[key]}</span>
                </button>
              );
            })}
            {/* Custom images */}
            {customImages.map(ci => (
              <button key={ci.id}
                onClick={() => setSelection({ kind: 'custom', id: ci.id })}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-all text-left"
                style={{
                  background: selCustom?.id === ci.id ? 'rgba(245,158,11,0.08)' : 'var(--s3)',
                  border: `1px solid ${selCustom?.id === ci.id ? 'rgba(245,158,11,0.4)' : 'transparent'}`,
                  color: selCustom?.id === ci.id ? 'var(--gold)' : 'var(--t1)',
                }}>
                <img src={ci.dataUrl} alt="" className="w-8 h-5 object-contain rounded flex-shrink-0"
                  style={{ background: '#fff' }} />
                <span className="truncate flex-1">{ci.label}</span>
                <X className="w-3 h-3 flex-shrink-0 opacity-50 hover:opacity-100"
                  onClick={e => { e.stopPropagation(); removeCustom(ci.id); }}
                  style={{ color: 'var(--rose)' }} />
              </button>
            ))}
            {Object.values(images).every(i => !i?.data) && customImages.length === 0 && (
              <p className="text-xs py-2 text-center" style={{ color: 'var(--t2)' }}>No images uploaded yet</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Image placement panel ──────────────────────────────────────────────────────
function ImagePanel({
  label, placement, locked, onToggleLock, onChange, onNudge, onClose, onDelete,
}: {
  label: string;
  placement: { x: number; y: number; width: number; height: number };
  locked: boolean;
  onToggleLock: () => void;
  onChange: (p: { x: number; y: number; width: number; height: number }) => void;
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
        {/* X/Y/W/H */}
        <div className="grid grid-cols-2 gap-2">
          {([
            ['X', 'x'], ['Y', 'y'], ['Width', 'width'], ['Height', 'height'],
          ] as [string, keyof typeof placement][]).map(([lbl, key]) => (
            <label key={key}>
              <span className="block text-[10px] mb-0.5" style={{ color: 'var(--t2)' }}>{lbl}</span>
              <input type="number"
                value={Math.round(placement[key])}
                onChange={e => {
                  const v = parseFloat(e.target.value) || 0;
                  if (key === 'width' && locked) {
                    onChange({ ...placement, width: v, height: Math.max(1, v / ratio) });
                  } else if (key === 'height' && locked) {
                    onChange({ ...placement, height: v, width: Math.max(1, v * ratio) });
                  } else {
                    onChange({ ...placement, [key]: v });
                  }
                }}
                className="w-full px-2 py-1.5 rounded-lg text-xs text-center"
                style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </label>
          ))}
        </div>

        {/* Nudge + aspect lock */}
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {[
              { dx: -5, dy: 0, icon: ArrowLeft },
              { dx: 5, dy: 0, icon: ArrowRight },
              { dx: 0, dy: -5, icon: ArrowUp },
              { dx: 0, dy: 5, icon: ArrowDown },
            ].map(({ dx, dy, icon: Icon }) => (
              <button key={`${dx}${dy}`} onClick={() => onNudge(dx, dy)}
                className="p-1.5 rounded-lg"
                style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t1)' }}>
                <Icon className="w-3 h-3" />
              </button>
            ))}
          </div>
          <button onClick={onToggleLock}
            className="ml-auto flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px]"
            style={{
              background: locked ? 'var(--em-dim)' : 'var(--s3)',
              color: locked ? 'var(--em-lt)' : 'var(--t2)',
              border: `1px solid ${locked ? 'rgba(59,130,246,0.3)' : 'var(--b2)'}`,
            }}>
            {locked ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
            {locked ? 'Locked' : 'Free'}
          </button>
        </div>
      </div>
    </div>
  );
}
