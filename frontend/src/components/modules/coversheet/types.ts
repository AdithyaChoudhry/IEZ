export interface CellStyle {
  font: {
    name: string | null;
    size: number | null;
    bold: boolean;
    italic: boolean;
    underline: boolean;
    color: string | null;
  };
  alignment: {
    horizontal: string | null;
    vertical: string | null;
    wrapText: boolean;
    shrinkToFit: boolean;
  };
  fill: string | null;
  border: {
    top: { style: string; color: string } | null;
    right: { style: string; color: string } | null;
    bottom: { style: string; color: string } | null;
    left: { style: string; color: string } | null;
  };
}

export interface LayoutCell {
  row: number;
  col: number;
  coord: string;
  value: string;
  rowspan: number;
  colspan: number;
  style: CellStyle;
}

export interface CoverSheetLayout {
  cols: number[];
  rows: number[];
  width: number;
  height: number;
  cells: LayoutCell[];
}

export interface ImagePlacement {
  x: number;
  y: number;
  width: number;
  height: number;
  data?: string;
}

export type ImageKey =
  | 'client_logo'
  | 'pmc_logo'
  | 'wabag_logo'
  | 'prepared_signature'
  | 'checked_signature'
  | 'approved_signature';

export interface CellOverride {
  value?: string;
  alignment?: Partial<{
    horizontal: string;
    vertical: string;
    wrapText: boolean;
    shrinkToFit: boolean;
  }>;
  font?: Partial<{
    name: string;
    size: number;
    bold: boolean;
    italic: boolean;
    underline: boolean;
  }>;
}

// Custom image uploaded by user
export interface CustomImageSlot {
  id: string;
  label: string;
  file: File;
  dataUrl: string;
  placement: { x: number; y: number; width: number; height: number };
}

// Cell merge override (frontend creates, backend applies)
export interface MergeRange {
  id: string;
  minRow: number;
  maxRow: number;
  minCol: number;
  maxCol: number;
}
