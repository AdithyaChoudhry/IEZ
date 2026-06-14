/**
 * Interactive cover sheet preview: renders the filled-in grid (mirroring
 * the Excel template's fonts/borders/merges/alignment), lets the user
 * tweak alignment/font formatting per cell, and reposition/resize image
 * overlays (logos, signatures) before final generation.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { AlignLeft, AlignCenter, AlignRight, AlignStartVertical, AlignCenterVertical, AlignEndVertical, Bold, Italic, Underline, WrapText, Shrink, ArrowUp, ArrowDown, ArrowLeft, ArrowRight } from 'lucide-react';
import type { CoverSheetLayout, ImagePlacement, ImageKey, CellOverride, LayoutCell } from './types';
import { styleToCss } from './styleUtils';
import ImageOverlay from './ImageOverlay';

const SCALE = 0.62;

const IMAGE_LABELS: Record<ImageKey, string> = {
  client_logo: 'Client Logo',
  pmc_logo: 'PMC Logo',
  wabag_logo: 'WABAG Logo',
  prepared_signature: 'Prepared By Signature',
  checked_signature: 'Checked By Signature',
  approved_signature: 'Approved By Signature',
};

interface PlacementState {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Props {
  layout: CoverSheetLayout;
  images: Partial<Record<ImageKey, ImagePlacement>>;
  cellOverrides: Record<string, CellOverride>;
  onCellOverridesChange: (overrides: Record<string, CellOverride>) => void;
  imagePlacements: Partial<Record<ImageKey, PlacementState>>;
  onImagePlacementsChange: (placements: Partial<Record<ImageKey, PlacementState>>) => void;
}

export default function CoverSheetPreview({
  layout,
  images,
  cellOverrides,
  onCellOverridesChange,
  imagePlacements,
  onImagePlacementsChange,
}: Props) {
  const [selectedCell, setSelectedCell] = useState<LayoutCell | null>(null);
  const [selectedImage, setSelectedImage] = useState<ImageKey | null>(null);
  const [aspectLocks, setAspectLocks] = useState<Partial<Record<ImageKey, boolean>>>({});
  const initializedKeys = useRef<Set<string>>(new Set());

  // Initialize placements for newly-seen images, preserving any
  // user-adjusted placements for images we've already initialized.
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
    if (changed) {
      onImagePlacementsChange({ ...imagePlacements, ...additions });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [images]);

  // Build a grid map for rendering: cellGrid[row][col] = LayoutCell | 'covered' | undefined
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

  const handleCellClick = (cell: LayoutCell) => {
    setSelectedCell(cell);
    setSelectedImage(null);
  };

  const updateCellOverride = (coord: string, update: CellOverride) => {
    const current = cellOverrides[coord] || {};
    const next: CellOverride = {
      alignment: { ...current.alignment, ...update.alignment },
      font: { ...current.font, ...update.font },
    };
    onCellOverridesChange({ ...cellOverrides, [coord]: next });
  };

  const updateImagePlacement = (key: ImageKey, next: PlacementState) => {
    onImagePlacementsChange({ ...imagePlacements, [key]: next });
  };

  const toggleAspectLock = (key: ImageKey) => {
    setAspectLocks((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const nudge = (key: ImageKey, dx: number, dy: number) => {
    const p = imagePlacements[key];
    if (!p) return;
    updateImagePlacement(key, { ...p, x: p.x + dx, y: p.y + dy });
  };

  const canvasWidth = layout.width * SCALE;
  const canvasHeight = layout.height * SCALE;

  const selectedOverride = selectedCell ? cellOverrides[selectedCell.coord] : undefined;
  const effectiveAlignment = selectedCell
    ? { ...selectedCell.style.alignment, ...(selectedOverride?.alignment || {}) }
    : null;
  const effectiveFont = selectedCell
    ? { ...selectedCell.style.font, ...(selectedOverride?.font || {}) }
    : null;

  return (
    <div className="flex flex-col lg:flex-row gap-4">
      {/* Canvas */}
      <div className="flex-1 overflow-auto border border-gray-200 rounded-lg bg-gray-50 p-4">
        <div
          style={{
            position: 'relative',
            width: canvasWidth,
            height: canvasHeight,
          }}
        >
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: layout.width,
              height: layout.height,
              transform: `scale(${SCALE})`,
              transformOrigin: 'top left',
            }}
          >
            <table style={{ borderCollapse: 'collapse', width: layout.width, tableLayout: 'fixed' }}>
              <colgroup>
                {layout.cols.map((w, i) => (
                  <col key={i} style={{ width: `${w}px` }} />
                ))}
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
                        return (
                          <td
                            key={c}
                            rowSpan={cell.rowspan}
                            colSpan={cell.colspan}
                            onClick={() => handleCellClick(cell)}
                            style={{
                              ...styleToCss(cell.style, override),
                              cursor: 'pointer',
                              outline: selectedCell?.coord === cell.coord ? '2px solid #2563eb' : undefined,
                            }}
                          >
                            {cell.value}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Image overlays */}
            {Object.entries(images).map(([key, img]) => {
              if (!img?.data) return null;
              const placement = imagePlacements[key as ImageKey];
              if (!placement) return null;
              const ratio = placement.width / placement.height;
              return (
                <ImageOverlay
                  key={key}
                  x={placement.x}
                  y={placement.y}
                  width={placement.width}
                  height={placement.height}
                  data={img.data}
                  scale={SCALE}
                  selected={selectedImage === key}
                  lockAspect={aspectLocks[key as ImageKey] ? ratio : null}
                  onSelect={() => {
                    setSelectedImage(key as ImageKey);
                    setSelectedCell(null);
                  }}
                  onChange={(next) => updateImagePlacement(key as ImageKey, next)}
                />
              );
            })}
          </div>
        </div>
      </div>

      {/* Side panel */}
      <div className="w-full lg:w-80 space-y-4">
        {/* Cell formatting */}
        {selectedCell && effectiveAlignment && effectiveFont && (
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <h4 className="font-semibold text-gray-800 mb-1">Cell {selectedCell.coord}</h4>
            <p className="text-xs text-gray-500 mb-3 truncate">{selectedCell.value || '(empty)'}</p>

            <p className="text-xs font-medium text-gray-600 mb-1">Horizontal Alignment</p>
            <div className="flex gap-1 mb-3">
              {[
                { v: 'left', icon: AlignLeft },
                { v: 'center', icon: AlignCenter },
                { v: 'right', icon: AlignRight },
              ].map(({ v, icon: Icon }) => (
                <button
                  key={v}
                  onClick={() => updateCellOverride(selectedCell.coord, { alignment: { horizontal: v } })}
                  className={`p-2 rounded border ${effectiveAlignment.horizontal === v ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600'}`}
                >
                  <Icon className="w-4 h-4" />
                </button>
              ))}
            </div>

            <p className="text-xs font-medium text-gray-600 mb-1">Vertical Alignment</p>
            <div className="flex gap-1 mb-3">
              {[
                { v: 'top', icon: AlignStartVertical },
                { v: 'center', icon: AlignCenterVertical },
                { v: 'bottom', icon: AlignEndVertical },
              ].map(({ v, icon: Icon }) => (
                <button
                  key={v}
                  onClick={() => updateCellOverride(selectedCell.coord, { alignment: { vertical: v } })}
                  className={`p-2 rounded border ${effectiveAlignment.vertical === v ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600'}`}
                >
                  <Icon className="w-4 h-4" />
                </button>
              ))}
            </div>

            <div className="flex gap-1 mb-3">
              <button
                onClick={() => updateCellOverride(selectedCell.coord, { alignment: { wrapText: !effectiveAlignment.wrapText } })}
                className={`flex items-center gap-1 px-2 py-1.5 rounded border text-xs ${effectiveAlignment.wrapText ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600'}`}
              >
                <WrapText className="w-4 h-4" /> Wrap
              </button>
              <button
                onClick={() => updateCellOverride(selectedCell.coord, { alignment: { shrinkToFit: !effectiveAlignment.shrinkToFit } })}
                className={`flex items-center gap-1 px-2 py-1.5 rounded border text-xs ${effectiveAlignment.shrinkToFit ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600'}`}
              >
                <Shrink className="w-4 h-4" /> Shrink
              </button>
            </div>

            <p className="text-xs font-medium text-gray-600 mb-1">Font</p>
            <div className="flex items-center gap-2 mb-2">
              <input
                type="number"
                min={6}
                max={72}
                value={effectiveFont.size || 10}
                onChange={(e) => updateCellOverride(selectedCell.coord, { font: { size: parseFloat(e.target.value) || 10 } })}
                className="w-20 border border-gray-300 rounded px-2 py-1 text-sm"
              />
              <span className="text-xs text-gray-500">pt</span>
            </div>
            <div className="flex gap-1">
              <button
                onClick={() => updateCellOverride(selectedCell.coord, { font: { bold: !effectiveFont.bold } })}
                className={`p-2 rounded border ${effectiveFont.bold ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600'}`}
              >
                <Bold className="w-4 h-4" />
              </button>
              <button
                onClick={() => updateCellOverride(selectedCell.coord, { font: { italic: !effectiveFont.italic } })}
                className={`p-2 rounded border ${effectiveFont.italic ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600'}`}
              >
                <Italic className="w-4 h-4" />
              </button>
              <button
                onClick={() => updateCellOverride(selectedCell.coord, { font: { underline: !effectiveFont.underline } })}
                className={`p-2 rounded border ${effectiveFont.underline ? 'bg-primary-600 text-white border-primary-600' : 'border-gray-300 text-gray-600'}`}
              >
                <Underline className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Image placement controls */}
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h4 className="font-semibold text-gray-800 mb-3">Images</h4>
          <div className="space-y-3">
            {(Object.keys(IMAGE_LABELS) as ImageKey[]).map((key) => {
              const img = images[key];
              const placement = imagePlacements[key];
              if (!img?.data || !placement) return null;
              return (
                <div
                  key={key}
                  className={`border rounded-lg p-3 cursor-pointer ${selectedImage === key ? 'border-primary-500 bg-primary-50' : 'border-gray-200'}`}
                  onClick={() => {
                    setSelectedImage(key);
                    setSelectedCell(null);
                  }}
                >
                  <p className="text-sm font-medium text-gray-700 mb-2">{IMAGE_LABELS[key]}</p>
                  <div className="grid grid-cols-2 gap-2 mb-2">
                    <label className="text-xs text-gray-500">
                      X
                      <input
                        type="number"
                        value={Math.round(placement.x)}
                        onChange={(e) => updateImagePlacement(key, { ...placement, x: parseFloat(e.target.value) || 0 })}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm mt-0.5"
                      />
                    </label>
                    <label className="text-xs text-gray-500">
                      Y
                      <input
                        type="number"
                        value={Math.round(placement.y)}
                        onChange={(e) => updateImagePlacement(key, { ...placement, y: parseFloat(e.target.value) || 0 })}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm mt-0.5"
                      />
                    </label>
                    <label className="text-xs text-gray-500">
                      Width
                      <input
                        type="number"
                        value={Math.round(placement.width)}
                        onChange={(e) => {
                          const width = parseFloat(e.target.value) || 1;
                          const height = aspectLocks[key] ? width / (placement.width / placement.height) : placement.height;
                          updateImagePlacement(key, { ...placement, width, height });
                        }}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm mt-0.5"
                      />
                    </label>
                    <label className="text-xs text-gray-500">
                      Height
                      <input
                        type="number"
                        value={Math.round(placement.height)}
                        onChange={(e) => {
                          const height = parseFloat(e.target.value) || 1;
                          const width = aspectLocks[key] ? height * (placement.width / placement.height) : placement.width;
                          updateImagePlacement(key, { ...placement, width, height });
                        }}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm mt-0.5"
                      />
                    </label>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex gap-1">
                      <button onClick={(e) => { e.stopPropagation(); nudge(key, -5, 0); }} className="p-1.5 border border-gray-300 rounded text-gray-600"><ArrowLeft className="w-3.5 h-3.5" /></button>
                      <button onClick={(e) => { e.stopPropagation(); nudge(key, 5, 0); }} className="p-1.5 border border-gray-300 rounded text-gray-600"><ArrowRight className="w-3.5 h-3.5" /></button>
                      <button onClick={(e) => { e.stopPropagation(); nudge(key, 0, -5); }} className="p-1.5 border border-gray-300 rounded text-gray-600"><ArrowUp className="w-3.5 h-3.5" /></button>
                      <button onClick={(e) => { e.stopPropagation(); nudge(key, 0, 5); }} className="p-1.5 border border-gray-300 rounded text-gray-600"><ArrowDown className="w-3.5 h-3.5" /></button>
                    </div>
                    <label className="flex items-center gap-1 text-xs text-gray-500">
                      <input
                        type="checkbox"
                        checked={!!aspectLocks[key]}
                        onChange={() => toggleAspectLock(key)}
                      />
                      Lock ratio
                    </label>
                  </div>
                </div>
              );
            })}
            {Object.values(images).every((img) => !img?.data) && (
              <p className="text-sm text-gray-500">
                Upload logos/signatures in the form above to position them here.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
