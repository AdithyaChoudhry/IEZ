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
  data?: string; // base64, present when an image is loaded for that key
}

export type ImageKey =
  | 'client_logo'
  | 'pmc_logo'
  | 'wabag_logo'
  | 'prepared_signature'
  | 'checked_signature'
  | 'approved_signature';

export interface CellOverride {
  value?: string; // direct cell value override (shown in preview + written to Excel)
  alignment?: Partial<{
    horizontal: string;
    vertical: string;
    wrapText: boolean;
    shrinkToFit: boolean;
  }>;
  font?: Partial<{
    size: number;
    bold: boolean;
    italic: boolean;
    underline: boolean;
  }>;
}

// Custom image uploaded by user (unlimited, beyond the 6 fixed slots)
export interface CustomImageSlot {
  id: string;       // uuid-ish
  label: string;    // user-visible name
  file: File;
  dataUrl: string;  // for preview canvas
  placement: { x: number; y: number; width: number; height: number };
}
