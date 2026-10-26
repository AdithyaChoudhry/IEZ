export type LoopConfig = Record<string, any>;

export interface SourceField { value: string; source: string; label: string; available: boolean; resolved_by?: string }
export interface Conflict {
  field: string; label: string; severity: 'error' | 'warning'; iodb: string; io: string; decision?: 'iodb' | 'io' | null;
}
export interface Suggestion { iodb_tag: string; method: string; score: number }
export interface MatchItem {
  tag: string; loop: string; status: string; method: string; in_iodb: boolean; in_io: boolean; signals: number;
  io_tag: string; conflicts: Conflict[]; suggestions: Suggestion[];
}
export interface MatchSummary {
  iodb_tags: number; io_assignment_tags: number; matched: number; not_matched: number; conflicts: number;
  duplicates: number; review_required: number; warnings: number; by_status: Record<string, number>;
}
export interface IoSignal {
  io_type: string; rack: string; slot: string; module: string; channel: string; plc: string; terminal_strip: string;
  terminal_cmn: string; terminal_signal: string; terminal_zero: string; description: string; sheet: string; row: number;
}
export interface TagDetail {
  tag: string; status: string; method: string; loop: string; fields: Record<string, SourceField>; signals: IoSignal[];
  conflicts: Conflict[]; suggestions: Suggestion[]; saved_config: LoopConfig | null; suggested_loop_type: string;
}
export interface Check { id: string; label: string; status: 'PASS' | 'WARNING' | 'ERROR'; detail: string }
export interface Validation {
  checks: Check[]; errors: number; warnings: number; passed: number; total: number; can_generate: boolean;
}
export interface LoopTypeDef {
  id: string; label: string; category: string; signal_type: string | null; status: string; wires: string[]; components: string[];
}
export interface TemplateDef { id: string; name: string; description?: string; loop_type: string; builtin?: boolean; db_id?: number; config?: LoopConfig; params?: Record<string, any> }
export interface Library {
  loop_types: Record<string, LoopTypeDef>;
  components: Record<string, { label: string; group: string }>;
  wire_roles: Record<string, string>;
  shield_types: Record<string, string>;
  shield_terminations: Record<string, string>;
  flow_directions: Record<string, string>;
  motor_starters: Record<string, { label: string; signals: { id: string; name: string; signal_type: string }[] }>;
  valve_types: Record<string, { label: string; signals: { id: string; name: string; signal_type: string }[] }>;
  builtin_templates: Record<string, TemplateDef>;
  saved_templates: TemplateDef[];
}
export interface IoMapping { [field: string]: { header: string; column: string; sheet: string } }
export interface IoInfo {
  file_name: string; rows: number; tag_rows: number; tags: number; mapping: IoMapping; headers: { sheet: string; column: string; header: string }[];
  sheets: { sheet: string; header_row: number; rows: number }[]; warnings: string[]; unmapped_required: string[]; confirmed?: boolean;
}
export interface IodbInfo { file_name: string; rows: number; fields_resolved: Record<string, string>; fields_unavailable: string[] }

export const IO_FIELD_LABELS: Record<string, string> = {
  TAG_NO: 'Tag number', LOOP_NO: 'Loop number', SERVICE: 'Service', DESCRIPTION: 'Description', STATUS: 'Status',
  SIGNAL_TYPE_TEXT: 'Type of signal', WIRE_TYPE: 'Wire type', IO_TYPE: 'I/O type', JB_NO: 'Junction box',
  JB_TB1: 'JB TB1', JB_TB2: 'JB TB2', JB_TB3: 'JB TB3', JB_PAIR: 'JB pair', PLC: 'PLC / DCS', RACK: 'Rack / node',
  SLOT: 'Slot', MODULE: 'Module', CHANNEL: 'Channel', TERMINAL_STRIP: 'Terminal strip', TERMINAL: 'Terminal',
  TERMINAL_CMN: 'Terminal CMN', TERMINAL_SIGNAL: 'Terminal signal', TERMINAL_ZERO: 'Terminal zero', ADDRESS: 'Address',
  REMARKS: 'Remarks',
};

export const STATUS_STYLE: Record<string, { bg: string; fg: string }> = {
  'MATCHED': { bg: 'rgba(74,222,128,0.12)', fg: '#4ade80' },
  'IO NOT FOUND': { bg: 'rgba(248,113,113,0.12)', fg: 'var(--rose)' },
  'IODB NOT FOUND': { bg: 'rgba(248,113,113,0.12)', fg: 'var(--rose)' },
  'CONFLICT': { bg: 'rgba(245,158,11,0.15)', fg: 'var(--gold)' },
  'DUPLICATE': { bg: 'rgba(245,158,11,0.15)', fg: 'var(--gold)' },
  'REVIEW REQUIRED': { bg: 'rgba(96,165,250,0.15)', fg: '#60a5fa' },
};
export const SOURCE_STYLE: Record<string, string> = { 'IODB': '#60a5fa', 'I/O ASSIGNMENT': '#34d399', 'USER CONFIGURATION': '#f59e0b' };
