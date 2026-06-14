/**
 * A draggable + resizable image overlay positioned absolutely within a
 * scaled canvas. Coordinates are in canvas (unscaled) pixels; `scale`
 * converts pointer movement back into canvas pixels.
 */
import { useRef } from 'react';

interface Props {
  x: number;
  y: number;
  width: number;
  height: number;
  data: string; // base64 image data
  scale: number;
  selected: boolean;
  lockAspect?: number | null; // width/height ratio to maintain, if set
  onSelect: () => void;
  onChange: (next: { x: number; y: number; width: number; height: number }) => void;
}

export default function ImageOverlay({ x, y, width, height, data, scale, selected, lockAspect, onSelect, onChange }: Props) {
  const dragState = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const resizeState = useRef<{ startX: number; startY: number; origW: number; origH: number } | null>(null);

  const handleDragStart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onSelect();
    dragState.current = { startX: e.clientX, startY: e.clientY, origX: x, origY: y };

    const onMove = (ev: MouseEvent) => {
      if (!dragState.current) return;
      const dx = (ev.clientX - dragState.current.startX) / scale;
      const dy = (ev.clientY - dragState.current.startY) / scale;
      onChange({ x: dragState.current.origX + dx, y: dragState.current.origY + dy, width, height });
    };
    const onUp = () => {
      dragState.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onSelect();
    resizeState.current = { startX: e.clientX, startY: e.clientY, origW: width, origH: height };

    const onMove = (ev: MouseEvent) => {
      if (!resizeState.current) return;
      const dx = (ev.clientX - resizeState.current.startX) / scale;
      const dy = (ev.clientY - resizeState.current.startY) / scale;
      const newWidth = Math.max(10, resizeState.current.origW + dx);
      const newHeight = lockAspect
        ? Math.max(10, newWidth / lockAspect)
        : Math.max(10, resizeState.current.origH + dy);
      onChange({ x, y, width: newWidth, height: newHeight });
    };
    const onUp = () => {
      resizeState.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  return (
    <div
      onMouseDown={handleDragStart}
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width,
        height,
        cursor: 'move',
        border: selected ? '2px solid #2563eb' : '1px dashed rgba(37,99,235,0.4)',
        boxSizing: 'border-box',
      }}
    >
      <img
        src={`data:image/png;base64,${data}`}
        alt=""
        draggable={false}
        style={{ width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'none' }}
      />
      {selected && (
        <div
          onMouseDown={handleResizeStart}
          style={{
            position: 'absolute',
            right: -6,
            bottom: -6,
            width: 12,
            height: 12,
            background: '#2563eb',
            borderRadius: 2,
            cursor: 'nwse-resize',
          }}
        />
      )}
    </div>
  );
}
