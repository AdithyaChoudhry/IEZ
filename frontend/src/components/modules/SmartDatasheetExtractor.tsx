import { useState, useCallback, useEffect, useRef } from 'react';
import {
  ScanSearch, Upload, FileSpreadsheet, Download, Zap,
  CheckCircle2, AlertCircle, FileText, Brain, Cpu,
  BarChart3, Tag, Activity, Clock, Sparkles, X,
  Eye, ListChecks, Layers, ChevronDown, ChevronUp,
} from 'lucide-react';
import api from '@/services/api';

/* ─────────── Types ─────────── */
interface ExtractedSpec {
  raw_label: string;
  value: string;
  values: string[];
  canonical_field: string | null;
  match_score: number;
  confidence: number;
  page: number;
  source?: string;
}

interface InstrumentSection {
  heading: string;
  instrument_type: string;
  specs: ExtractedSpec[];
}

interface FileResult {
  fileName: string;
  sections: InstrumentSection[];
  pageCount: number;
  instrumentType: string; // comma-joined summary
}

interface ExtractionResponse {
  sections: InstrumentSection[];
  page_count: number;
  message: string;
  instrument_type: string;
}

interface GenerateResponse {
  specs: ExtractedSpec[];
  page_count: number;
  mapping_log: Array<{
    heading: string;
    canonical_field: string | null;
    score: number;
    value: string;
    status: 'MATCHED' | 'UNMATCHED';
  }>;
  filename: string;
  message: string;
  instrument_type: string;
}

/* A single confirmed section (post-review) ready for template assignment */
interface ConfirmedSection {
  heading: string;
  instrument_type: string;
  specs: ExtractedSpec[];
  fileName: string;
}

interface SpecSel {
  include: boolean;
  valueIdx: number;
}

const POLL_MS = 1500;
const MAX_POLLS = 300;
const SESSION_KEY = 'sdie_results_v3';
const STEP_DELAY_MS = 600;

type Step = 'idle' | 'template_prompt' | 'uploading' | 'ocr' | 'ai' | 'mapping' | 'review' | 'template_assign' | 'done' | 'error';

function formatTime(secs: number) {
  return `${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(secs % 60).padStart(2, '0')}`;
}

const DISCOVERY_LABELS = [
  'Tag Number', 'Instrument Type', 'Service Description', 'Line Size',
  'Nominal Diameter', 'Process Connection', 'Design Pressure', 'Operating Pressure',
  'Operating Temperature', 'Design Temperature', 'Fluid / Medium', 'Flow Rate',
  'Signal Output', 'Power Supply', 'Accuracy Class', 'IP Protection',
  'Calibration Range', 'Material of Construction', 'Ambient Temperature',
  'Area Classification', 'Manufacturer', 'Model Number', 'Process Fluid',
  'Wetted Material', 'Housing Material', 'Connection Standard', 'Certificate',
  'Transmitter Range', 'Sensor Element', 'Beam Angle', 'Frequency',
];

/* ─────────── Confidence bar ─────────── */
function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-amber-400' : 'bg-red-400';
  const textColor = value >= 80 ? 'text-emerald-600' : value >= 60 ? 'text-amber-600' : 'text-red-500';
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className={`text-xs font-bold tabular-nums ${textColor}`}>{value.toFixed(0)}%</span>
    </div>
  );
}

/* ─────────── Multi-file drop zone ─────────── */
function MultiDropZone({ files, onFilesChange, disabled }: {
  files: File[]; onFilesChange: (f: File[]) => void; disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);

  const addFiles = useCallback((incoming: File[]) => {
    const exts = ['.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'];
    const valid = incoming.filter(f => exts.some(e => f.name.toLowerCase().endsWith(e)));
    if (!valid.length) return;
    onFilesChange([...files, ...valid].filter((f, i, arr) => arr.findIndex(x => x.name === f.name) === i));
  }, [files, onFilesChange]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    if (!disabled) addFiles(Array.from(e.dataTransfer.files));
  }, [addFiles, disabled]);

  const browse = () => {
    if (disabled) return;
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = '.pdf,.jpg,.jpeg,.png,.tif,.tiff'; inp.multiple = true;
    inp.onchange = e => { const fs = (e.target as HTMLInputElement).files; if (fs) addFiles(Array.from(fs)); };
    inp.click();
  };

  return (
    <div className="space-y-2">
      <div
        onDragOver={e => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop} onClick={browse}
        className={`relative border-2 border-dashed rounded-2xl p-5 text-center transition-all duration-300 cursor-pointer group
          ${dragging ? 'border-blue-400 bg-blue-50 scale-[1.01]' :
            files.length ? 'border-blue-200 bg-blue-50/40' :
            disabled ? 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed' :
            'border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/30'}`}
      >
        <div className={`w-10 h-10 rounded-xl mx-auto mb-2 flex items-center justify-center transition-all ${files.length ? 'bg-blue-100' : 'bg-blue-50 group-hover:bg-blue-100'}`}>
          <Upload className="w-5 h-5 text-blue-500 group-hover:scale-110 transition-transform" />
        </div>
        <p className="text-sm font-semibold text-gray-700">
          {files.length ? `${files.length} file${files.length > 1 ? 's' : ''} queued` : 'Drop files here'}
        </p>
        <p className="text-xs text-gray-400 mt-0.5">
          {files.length ? 'Drop more to add · ' : ''}
          <span className="text-blue-500 font-medium">Browse</span> · PDF, JPG, PNG, TIFF · Multiple OK
        </p>
      </div>
      {files.length > 0 && (
        <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
          {files.map((f, i) => (
            <div key={i} className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 hover:bg-red-50/40 rounded-xl border border-gray-100 group transition-colors">
              <FileText className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
              <span className="text-xs font-medium text-gray-700 flex-1 truncate">{f.name}</span>
              <span className="text-[10px] text-gray-400">{(f.size / 1024).toFixed(0)} KB</span>
              {!disabled && (
                <button onClick={e => { e.stopPropagation(); onFilesChange(files.filter((_, j) => j !== i)); }}
                  className="w-4 h-4 rounded-full bg-gray-200 hover:bg-red-100 text-gray-400 hover:text-red-500 flex items-center justify-center transition-colors flex-shrink-0">
                  <X className="w-2.5 h-2.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─────────── Template upload popup ─────────── */
function TemplatePrompt({ onConfirm, onSkip }: {
  onConfirm: (f: File) => void; onSkip: () => void;
}) {
  const [dragging, setDragging] = useState(false);

  const pick = (f: File) => {
    const ok = ['.xlsx', '.xlsm', '.xls'].some(e => f.name.toLowerCase().endsWith(e));
    if (ok) onConfirm(f);
  };
  const browse = () => {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = '.xlsx,.xlsm,.xls';
    inp.onchange = e => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) pick(f); };
    inp.click();
  };

  return (
    <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md p-7 animate-fade-in-up">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-200">
            <FileSpreadsheet className="w-5 h-5 text-white" />
          </div>
          <div>
            <h3 className="text-base font-black text-gray-900">Upload WABAG Template</h3>
            <p className="text-xs text-gray-500">Optional — enables template-aware field targeting</p>
          </div>
        </div>
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) pick(f); }}
          onClick={browse}
          className={`border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all duration-300 mb-4
            ${dragging ? 'border-violet-400 bg-violet-50' : 'border-gray-200 hover:border-violet-300 hover:bg-violet-50/30'}`}
        >
          <FileSpreadsheet className="w-8 h-8 text-violet-400 mx-auto mb-2" />
          <p className="text-sm font-semibold text-gray-700">Drop template here</p>
          <p className="text-xs text-gray-400 mt-0.5">or <span className="text-violet-500 font-medium">browse</span> · .xlsx / .xlsm / .xls</p>
        </div>
        <div className="bg-blue-50 rounded-xl p-3 mb-5 flex gap-2">
          <Sparkles className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-blue-700 font-medium leading-relaxed">
            AI reads fields from sheet 2/3 and extracts ONLY those specific values from your tender document — much more accurate.
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={onSkip}
            className="flex-1 py-2.5 px-4 rounded-xl border-2 border-gray-200 text-sm font-bold text-gray-600 hover:border-gray-300 hover:bg-gray-50 transition-all">
            Skip — Extract All Fields
          </button>
          <button onClick={browse}
            className="flex-1 py-2.5 px-4 rounded-xl bg-gradient-to-r from-violet-600 to-purple-700 text-white text-sm font-bold shadow-lg shadow-violet-200 hover:shadow-xl hover:-translate-y-0.5 transition-all">
            Upload Template
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────── Processing visualizer ─────────── */
function ProcessingVisualizer({ step, fileCount, currentFileIdx, fileName, elapsed }: {
  step: Step; fileCount: number; currentFileIdx: number; fileName: string; elapsed: number;
}) {
  const [discoveries, setDiscoveries] = useState<string[]>([]);
  const intRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setDiscoveries([]);
    if (!['ocr', 'ai', 'mapping'].includes(step)) return;
    const pool = [...DISCOVERY_LABELS].sort(() => Math.random() - 0.5);
    let idx = 0;
    intRef.current = setInterval(() => {
      if (idx < pool.length) setDiscoveries(prev => [pool[idx++], ...prev.slice(0, 9)]);
    }, 600);
    return () => { if (intRef.current) clearInterval(intRef.current); };
  }, [step, currentFileIdx]);

  const stepOrder: Step[] = ['uploading', 'ocr', 'ai', 'mapping', 'review', 'done'];
  const cur = stepOrder.indexOf(step);
  const progress = step === 'uploading' ? 8 : step === 'ocr' ? 30 : step === 'ai' ? 62 : 88;

  const stages = [
    { key: 'ocr' as Step, label: 'OCR Scan', icon: Cpu },
    { key: 'ai' as Step, label: 'AI Analysis', icon: Brain },
    { key: 'mapping' as Step, label: 'Mapping', icon: Tag },
    { key: 'review' as Step, label: 'Review', icon: Eye },
  ];

  return (
    <div className="card-premium overflow-hidden animate-fade-in-up">
      <div className="flex items-center justify-between px-5 py-3 bg-gradient-to-r from-slate-50 to-blue-50 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="flex gap-1 items-center">
            {Array.from({ length: fileCount }).map((_, i) => (
              <div key={i} className={`rounded-full transition-all duration-500 ${
                i < currentFileIdx ? 'w-5 h-2 bg-emerald-400' :
                i === currentFileIdx ? 'w-7 h-2 bg-blue-500 animate-pulse' : 'w-5 h-2 bg-gray-200'
              }`} />
            ))}
          </div>
          <span className="text-xs font-bold text-gray-600">File {currentFileIdx + 1} / {fileCount}</span>
          <span className="text-xs text-gray-400 truncate max-w-[200px]">{fileName}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-mono font-semibold text-gray-600">
          <Clock className="w-3.5 h-3.5 text-blue-400" /> {formatTime(elapsed)}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-5 p-5">
        <div className="space-y-2">
          <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-1.5"><Cpu className="w-3 h-3" /> OCR Engine</p>
          <div className={`relative rounded-2xl overflow-hidden h-40 p-4 border-2 transition-all duration-500 ${step === 'ocr' ? 'border-blue-300 bg-blue-50/30 shadow-lg shadow-blue-100' : 'border-gray-100 bg-white'}`}>
            <div className="space-y-2 mt-1">
              {[88, 72, 92, 58, 80, 66, 76, 84, 60].map((w, i) => (
                <div key={i} className={`h-1.5 rounded-full transition-all duration-700 ${step === 'ocr' ? 'bg-blue-200' : cur > 1 ? 'bg-emerald-200' : 'bg-gray-100'}`} style={{ width: `${w}%` }} />
              ))}
            </div>
            {step === 'ocr' && <div className="animate-scan-beam absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-blue-500 to-transparent shadow-sm shadow-blue-400/60" />}
            {cur > 1 && (
              <div className="absolute inset-0 bg-emerald-50/60 flex items-center justify-center rounded-2xl">
                <div className="flex flex-col items-center gap-1"><CheckCircle2 className="w-7 h-7 text-emerald-500" /><span className="text-[10px] font-bold text-emerald-600">Text Extracted</span></div>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-1.5"><Brain className="w-3 h-3" /> Llama 3.3 70B</p>
          <div className={`relative rounded-2xl overflow-hidden h-40 flex items-center justify-center border-2 transition-all duration-500 ${step === 'ai' ? 'border-violet-300 bg-violet-50/30 shadow-lg shadow-violet-100' : 'border-gray-100 bg-white'}`}>
            {step === 'ai' ? (
              <div className="relative flex items-center justify-center w-24 h-24">
                <div className="absolute inset-0 rounded-full border border-violet-200 animate-ping opacity-20" />
                <div className="absolute inset-2 rounded-full border border-violet-300 animate-ping opacity-30" style={{ animationDelay: '0.4s' }} />
                {[0, 51, 102, 153, 204, 255, 306].map((deg, i) => (
                  <div key={i} className="absolute w-2 h-2 rounded-full" style={{
                    background: `hsl(${260 + i * 10}, 80%, 65%)`,
                    top: `calc(50% + ${Math.sin(deg * Math.PI / 180) * 36}px - 4px)`,
                    left: `calc(50% + ${Math.cos(deg * Math.PI / 180) * 36}px - 4px)`,
                    animation: `spin-slow ${3 + i * 0.2}s linear infinite ${i % 2 ? 'reverse' : ''}`,
                  }} />
                ))}
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-xl shadow-violet-300 z-10">
                  <Brain className="w-6 h-6 text-white" />
                </div>
              </div>
            ) : (step === 'ocr' || step === 'uploading') ? (
              <div className="flex flex-col items-center gap-2 opacity-25"><Brain className="w-9 h-9 text-gray-400" /><span className="text-[10px] text-gray-400 font-medium">Waiting for OCR…</span></div>
            ) : (
              <div className="flex flex-col items-center gap-1.5"><CheckCircle2 className="w-7 h-7 text-emerald-500" /><span className="text-[10px] font-bold text-emerald-600">Analysis Complete</span></div>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center gap-1.5"><Sparkles className="w-3 h-3" /> Live Discoveries</p>
          <div className={`relative rounded-2xl overflow-hidden h-40 border-2 transition-all duration-500 ${step === 'mapping' ? 'border-emerald-300 bg-emerald-50/20 shadow-lg shadow-emerald-100' : 'border-gray-100 bg-white'}`}>
            <div className="absolute inset-0 p-3 overflow-hidden flex flex-col gap-1">
              {discoveries.length === 0 ? (
                <div className="h-full flex items-center justify-center"><p className="text-[10px] text-gray-300 font-medium">Scanning document…</p></div>
              ) : discoveries.map((label, i) => (
                <div key={`${label}-${i}`}
                  className={`flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[10px] font-semibold transition-all animate-discovery ${i === 0 ? 'bg-emerald-100 text-emerald-700 border border-emerald-200' : i <= 2 ? 'bg-blue-50 text-blue-600' : 'text-gray-400'}`}
                  style={{ opacity: Math.max(0.08, 1 - i * 0.11) }}
                >
                  {i === 0 && <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse flex-shrink-0" />}
                  <span className="truncate">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="px-5 pb-5 space-y-3">
        <div className="flex items-center">
          {stages.map((s, i) => {
            const sIdx = stepOrder.indexOf(s.key);
            const done = cur > sIdx; const active = cur === sIdx;
            const Icon = s.icon;
            return (
              <div key={s.key} className="flex items-center flex-1">
                <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold whitespace-nowrap transition-all duration-500 ${done ? 'bg-emerald-100 text-emerald-700 border border-emerald-200' : active ? 'bg-blue-600 text-white shadow-md shadow-blue-200 animate-pulse' : 'bg-gray-100 text-gray-400'}`}>
                  <Icon className="w-3 h-3" /><span className="hidden sm:inline">{s.label}</span>
                </div>
                {i < stages.length - 1 && <div className={`flex-1 h-px mx-1 rounded transition-all duration-700 ${done ? 'bg-emerald-300' : 'bg-gray-200'}`} />}
              </div>
            );
          })}
        </div>
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full bg-gradient-to-r from-blue-500 via-violet-500 to-emerald-500 rounded-full transition-all duration-1000" style={{ width: `${progress}%` }} />
        </div>
      </div>
    </div>
  );
}

/* ─────────── Section-aware Review Panel ─────────── */
function ReviewPanel({ fileResults, onConfirm, onBack }: {
  fileResults: FileResult[];
  onConfirm: (sections: ConfirmedSection[]) => void;
  onBack: () => void;
}) {
  // Key: "${fi}-${si}-${pi}" = file index, section index, spec index
  const [selections, setSelections] = useState<Record<string, SpecSel>>(() => {
    const init: Record<string, SpecSel> = {};
    fileResults.forEach((fr, fi) => {
      fr.sections.forEach((sec, si) => {
        sec.specs.forEach((_spec, pi) => {
          init[`${fi}-${si}-${pi}`] = { include: true, valueIdx: 0 };
        });
      });
    });
    return init;
  });

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggleAll = (include: boolean) =>
    setSelections(prev => Object.fromEntries(Object.entries(prev).map(([k, v]) => [k, { ...v, include }])));

  const selectedCount = Object.values(selections).filter(s => s.include).length;
  const totalCount = Object.keys(selections).length;

  const handleConfirm = () => {
    const confirmed: ConfirmedSection[] = [];
    fileResults.forEach((fr, fi) => {
      fr.sections.forEach((sec, si) => {
        const confirmedSpecs = sec.specs
          .filter((_spec, pi) => selections[`${fi}-${si}-${pi}`]?.include !== false)
          .map((spec, pi) => {
            const sel = selections[`${fi}-${si}-${pi}`] ?? { include: true, valueIdx: 0 };
            const chosen = spec.values?.[sel.valueIdx] ?? spec.value;
            return { ...spec, value: chosen };
          });
        if (confirmedSpecs.length > 0) {
          confirmed.push({
            heading: sec.heading,
            instrument_type: sec.instrument_type,
            specs: confirmedSpecs,
            fileName: fr.fileName,
          });
        }
      });
    });
    onConfirm(confirmed);
  };

  return (
    <div className="space-y-4 animate-fade-in-up">
      {/* Header bar */}
      <div className="card-premium p-5">
        <div className="flex items-start gap-4">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-200 animate-float flex-shrink-0">
            <ListChecks className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-black text-gray-900">Review Extracted Specifications</h2>
            <p className="text-xs text-gray-500 mt-0.5">Specs grouped by instrument section · Select values · Uncheck to exclude</p>
          </div>
        </div>
        <div className="flex items-center gap-3 mt-4">
          <span className="text-xs font-semibold text-gray-500">{selectedCount} of {totalCount} fields selected</span>
          <button onClick={() => toggleAll(true)} className="text-xs font-bold text-blue-600 hover:underline">Select All</button>
          <button onClick={() => toggleAll(false)} className="text-xs font-bold text-gray-400 hover:underline">Deselect All</button>
          <div className="ml-auto flex gap-2">
            <button onClick={onBack} className="px-4 py-2 rounded-xl border-2 border-gray-200 text-xs font-bold text-gray-600 hover:border-gray-300 transition-all">
              ← New Upload
            </button>
            <button
              onClick={handleConfirm}
              disabled={selectedCount === 0}
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-700 text-white text-xs font-bold shadow-lg shadow-emerald-200 hover:shadow-xl hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:transform-none"
            >
              <CheckCircle2 className="w-3.5 h-3.5" /> Confirm &amp; Assign Templates ({selectedCount})
            </button>
          </div>
        </div>
      </div>

      {/* Sections per file */}
      {fileResults.map((fr, fi) => (
        <div key={fi} className="space-y-3">
          {fileResults.length > 1 && (
            <div className="flex items-center gap-2 px-1">
              <FileText className="w-3.5 h-3.5 text-blue-500" />
              <span className="text-xs font-bold text-blue-700">{fr.fileName}</span>
              <span className="text-[10px] text-blue-400">{fr.pageCount} pages</span>
            </div>
          )}

          {fr.sections.map((sec, si) => {
            const sectionKey = `${fi}-${si}`;
            const isCollapsed = collapsed[sectionKey];
            const sectionSelected = sec.specs.filter((_s, pi) => selections[`${fi}-${si}-${pi}`]?.include !== false).length;

            return (
              <div key={si} className="card-premium overflow-hidden">
                {/* Section header */}
                <button
                  onClick={() => setCollapsed(prev => ({ ...prev, [sectionKey]: !prev[sectionKey] }))}
                  className="w-full flex items-center gap-3 px-5 py-3.5 bg-gradient-to-r from-slate-50 to-blue-50 border-b border-gray-100 hover:from-blue-50 hover:to-violet-50 transition-colors"
                >
                  <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                    <Layers className="w-4 h-4 text-white" />
                  </div>
                  <div className="flex-1 text-left">
                    <p className="text-sm font-black text-gray-900">{sec.heading}</p>
                    <p className="text-[10px] text-gray-500">{sec.instrument_type} · {sectionSelected}/{sec.specs.length} fields selected</p>
                  </div>
                  <span className="px-2.5 py-1 bg-blue-100 text-blue-700 rounded-full text-[10px] font-bold">
                    {sec.specs.length} fields
                  </span>
                  {isCollapsed ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronUp className="w-4 h-4 text-gray-400" />}
                </button>

                {!isCollapsed && (
                  <div className="overflow-auto max-h-[400px]">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 sticky top-0 z-10">
                        <tr>
                          <th className="px-3 py-2.5 text-left font-bold text-gray-500 w-8">✓</th>
                          <th className="px-4 py-2.5 text-left font-bold text-gray-600">Field</th>
                          <th className="px-4 py-2.5 text-left font-bold text-gray-600">Extracted Values — pick one</th>
                          <th className="px-4 py-2.5 text-left font-bold text-gray-600 whitespace-nowrap">Confidence</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {sec.specs.map((spec, pi) => {
                          const key = `${fi}-${si}-${pi}`;
                          const sel = selections[key] ?? { include: true, valueIdx: 0 };
                          const allVals = spec.values?.length ? spec.values : [spec.value];
                          return (
                            <tr key={pi} className={`transition-colors ${sel.include ? 'hover:bg-blue-50/30' : 'opacity-40 bg-gray-50/50'}`}>
                              <td className="px-3 py-3 text-center">
                                <input
                                  type="checkbox"
                                  checked={sel.include}
                                  onChange={e => setSelections(prev => ({ ...prev, [key]: { ...sel, include: e.target.checked } }))}
                                  className="w-3.5 h-3.5 rounded text-blue-600 cursor-pointer"
                                />
                              </td>
                              <td className="px-4 py-3 font-semibold text-gray-800 whitespace-nowrap max-w-[160px] truncate" title={spec.raw_label}>
                                {spec.raw_label}
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex flex-wrap gap-1.5">
                                  {allVals.map((v, vi) => (
                                    <button
                                      key={vi}
                                      onClick={() => setSelections(prev => ({ ...prev, [key]: { ...sel, valueIdx: vi } }))}
                                      className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all duration-200 ${
                                        sel.valueIdx === vi && sel.include
                                          ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                                          : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300 hover:bg-blue-50'
                                      }`}
                                    >
                                      {allVals.length > 1 && (
                                        <span className={`text-[9px] font-bold ${sel.valueIdx === vi && sel.include ? 'text-blue-200' : 'text-gray-400'}`}>
                                          {vi + 1}
                                        </span>
                                      )}
                                      {v}
                                    </button>
                                  ))}
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <ConfidenceBar value={spec.confidence} />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

/* ─────────── Per-section Template Assignment ─────────── */
function TemplateAssignment({ sections, onDone }: {
  sections: ConfirmedSection[];
  onDone: () => void;
}) {
  const [templates, setTemplates] = useState<Record<number, File>>({});
  const [generating, setGenerating] = useState<Record<number, boolean>>({});
  const [generated, setGenerated] = useState<Record<number, boolean>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});

  const pickTemplate = (idx: number) => {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = '.xlsx,.xlsm,.xls';
    inp.onchange = e => {
      const f = (e.target as HTMLInputElement).files?.[0];
      if (f) setTemplates(prev => ({ ...prev, [idx]: f }));
    };
    inp.click();
  };

  const generateForSection = async (idx: number) => {
    const section = sections[idx];
    const tmpl = templates[idx];
    if (!tmpl) return;

    setGenerating(prev => ({ ...prev, [idx]: true }));
    setErrors(prev => { const n = { ...prev }; delete n[idx]; return n; });

    try {
      const formData = new FormData();
      formData.append('specs', JSON.stringify(section.specs));
      formData.append('template_file', tmpl);
      formData.append('heading', section.heading);

      const res = await api.post('/sdie/map-to-template', formData, {
        responseType: 'blob',
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      const safe = section.heading.replace(/[^a-zA-Z0-9]/g, '_').replace(/_+/g, '_').slice(0, 30);
      a.download = `Datasheet_${safe}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);

      setGenerated(prev => ({ ...prev, [idx]: true }));
    } catch (err: any) {
      const msg = err.response?.data ? 'Template mapping failed' : (err.message || 'Error');
      setErrors(prev => ({ ...prev, [idx]: msg }));
    } finally {
      setGenerating(prev => ({ ...prev, [idx]: false }));
    }
  };

  return (
    <div className="space-y-4 animate-fade-in-up">
      <div className="card-premium p-5">
        <div className="flex items-start gap-4">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-200 animate-float flex-shrink-0">
            <FileSpreadsheet className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-black text-gray-900">Map to WABAG Datasheets</h2>
            <p className="text-xs text-gray-500 mt-0.5">Upload one SOP datasheet template per instrument type · Download populated Excel for each</p>
          </div>
          <button onClick={onDone} className="px-4 py-2 rounded-xl border-2 border-gray-200 text-xs font-bold text-gray-600 hover:border-blue-300 transition-all flex-shrink-0">
            Skip → View Results
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {sections.map((section, idx) => (
          <div key={idx} className="card-premium overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-100">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                <Layers className="w-4 h-4 text-white" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-black text-gray-900">{section.heading}</p>
                <p className="text-[10px] text-gray-500">{section.instrument_type} · {section.specs.length} confirmed fields · from {section.fileName}</p>
              </div>
              {generated[idx] && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-full">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  <span className="text-[10px] font-bold text-emerald-600">Downloaded</span>
                </div>
              )}
            </div>

            <div className="p-5 flex items-center gap-4">
              {/* Template dropzone */}
              <div
                onClick={() => pickTemplate(idx)}
                className={`flex-1 flex items-center gap-3 px-4 py-3.5 rounded-2xl border-2 border-dashed cursor-pointer transition-all duration-300
                  ${templates[idx] ? 'border-emerald-300 bg-emerald-50/40' : 'border-gray-200 hover:border-violet-300 hover:bg-violet-50/30'}`}
              >
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ${templates[idx] ? 'bg-emerald-100' : 'bg-violet-50'}`}>
                  {templates[idx] ? <CheckCircle2 className="w-4.5 h-4.5 text-emerald-500" /> : <FileSpreadsheet className="w-4.5 h-4.5 text-violet-400" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-bold text-gray-700 truncate">
                    {templates[idx] ? templates[idx].name : 'Upload SOP Template'}
                  </p>
                  <p className="text-[10px] text-gray-400">{templates[idx] ? 'Click to change' : '.xlsx / .xlsm / .xls'}</p>
                </div>
              </div>

              {/* Generate button */}
              <button
                onClick={() => generateForSection(idx)}
                disabled={!templates[idx] || generating[idx]}
                className={`flex items-center gap-2 px-5 py-3 rounded-xl font-bold text-sm transition-all flex-shrink-0 ${
                  generated[idx]
                    ? 'bg-emerald-50 text-emerald-700 border-2 border-emerald-200 hover:bg-emerald-100'
                    : 'bg-gradient-to-r from-violet-600 to-purple-700 text-white shadow-lg shadow-violet-200 hover:shadow-xl hover:-translate-y-0.5 disabled:opacity-50 disabled:transform-none disabled:shadow-none'
                }`}
              >
                {generating[idx]
                  ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Generating…</>
                  : generated[idx]
                  ? <><Download className="w-4 h-4" />Re-download</>
                  : <><Download className="w-4 h-4" />Generate Excel</>
                }
              </button>
            </div>

            {errors[idx] && (
              <div className="mx-5 mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-xl flex items-center gap-2">
                <AlertCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />
                <p className="text-xs text-red-600">{errors[idx]}</p>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="flex justify-center">
        <button
          onClick={onDone}
          className="flex items-center gap-2 px-8 py-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-700 text-white font-bold text-sm shadow-lg shadow-emerald-200 hover:shadow-xl hover:-translate-y-0.5 transition-all"
        >
          <CheckCircle2 className="w-4 h-4" /> Done — View Summary
        </button>
      </div>
    </div>
  );
}

/* ─────────── Main component ─────────── */
export default function SmartDatasheetExtractor() {
  const [files, setFiles] = useState<File[]>([]);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [showTemplatePrompt, setShowTemplatePrompt] = useState(false);
  const [step, setStep] = useState<Step>('idle');
  const [currentFileIdx, setCurrentFileIdx] = useState(0);
  const [fileResults, setFileResults] = useState<FileResult[]>([]);
  const [pendingResults, setPendingResults] = useState<FileResult[]>([]);
  const [confirmedSections, setConfirmedSections] = useState<ConfirmedSection[]>([]);
  const [generateResult, setGenerateResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'specs' | 'mapping'>('specs');
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Restore from sessionStorage on mount
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(SESSION_KEY);
      if (!saved) return;
      const { fileResults: fr, confirmedSections: cs, generateResult: gr, elapsed: el, savedAt } = JSON.parse(saved);
      if (Date.now() - savedAt > 60 * 60 * 1000) { sessionStorage.removeItem(SESSION_KEY); return; }
      setFileResults(fr ?? []);
      setConfirmedSections(cs ?? []);
      setGenerateResult(gr ?? null);
      setElapsed(el ?? 0);
      setStep('done');
      setActiveTab(gr ? 'mapping' : 'specs');
    } catch { sessionStorage.removeItem(SESSION_KEY); }
  }, []);

  useEffect(() => {
    if (step === 'done' && (fileResults.length > 0 || confirmedSections.length > 0)) {
      try {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify({ fileResults, confirmedSections, generateResult, elapsed, savedAt: Date.now() }));
      } catch { /* storage full */ }
    }
  }, [step, fileResults, confirmedSections, generateResult, elapsed]);

  const startTimer = () => { setElapsed(0); timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000); };
  const stopTimer = () => { if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; } };
  useEffect(() => () => stopTimer(), []);

  const reset = () => {
    setFileResults([]); setPendingResults([]); setConfirmedSections([]);
    setGenerateResult(null); setError(null);
    setStep('idle'); setCurrentFileIdx(0); stopTimer(); setElapsed(0);
    setShowTemplatePrompt(false);
    sessionStorage.removeItem(SESSION_KEY);
  };

  const pollJob = async (endpoint: string, jobId: string): Promise<any> => {
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise(r => setTimeout(r, POLL_MS));
      const res = await api.get<any>(`${endpoint}/${jobId}`);
      if (res.data.status === 'done') return res.data.result;
      if (res.data.status === 'error') throw new Error(res.data.error || 'Job failed');
    }
    throw new Error('Timeout');
  };

  const startExtract = () => {
    if (!files.length) return;
    if (!templateFile) { setShowTemplatePrompt(true); } else { runExtract(); }
  };

  const runExtract = async (tmpl?: File | null) => {
    const tFile = tmpl ?? templateFile;
    setShowTemplatePrompt(false);
    reset();
    startTimer();
    setStep('uploading');

    const results: FileResult[] = [];

    for (let i = 0; i < files.length; i++) {
      setCurrentFileIdx(i);
      const formData = new FormData();
      formData.append('file', files[i]);
      if (tFile) formData.append('template_file', tFile);

      try {
        const kickoff = await api.post<{ job_id: string }>('/sdie/extract', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        setStep('ocr');
        await new Promise(r => setTimeout(r, STEP_DELAY_MS));
        setStep('ai');
        await new Promise(r => setTimeout(r, STEP_DELAY_MS));
        setStep('mapping');

        const result: ExtractionResponse = await pollJob('/sdie/extract/status', kickoff.data.job_id);
        results.push({
          fileName: files[i].name,
          sections: result.sections ?? [],
          pageCount: result.page_count,
          instrumentType: result.instrument_type,
        });
      } catch (err: any) {
        setError(`"${files[i].name}": ${err.response?.data?.detail || err.message}`);
        setStep('error');
        stopTimer();
        return;
      }
    }

    setPendingResults(results);
    setStep('review');
    stopTimer();
  };

  const handleGenerate = async () => {
    if (!files.length || !templateFile) return;
    reset();
    startTimer();
    setStep('uploading');
    setCurrentFileIdx(0);

    const formData = new FormData();
    formData.append('file', files[0]);
    formData.append('template_file', templateFile);

    try {
      const kickoff = await api.post<{ job_id: string }>('/sdie/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setStep('ocr');
      await new Promise(r => setTimeout(r, STEP_DELAY_MS));
      setStep('ai');
      await new Promise(r => setTimeout(r, STEP_DELAY_MS));
      setStep('mapping');

      const result: GenerateResponse = await pollJob('/sdie/generate/status', kickoff.data.job_id);
      setGenerateResult(result);
      // Wrap flat specs into a single-section FileResult for the review panel
      setPendingResults([{
        fileName: files[0].name,
        sections: [{
          heading: result.instrument_type || 'Extracted Specifications',
          instrument_type: result.instrument_type || '',
          specs: result.specs,
        }],
        pageCount: result.page_count,
        instrumentType: result.instrument_type,
      }]);
      setStep('review');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Generation failed');
      setStep('error');
    } finally {
      stopTimer();
    }
  };

  const handleReviewConfirm = (sections: ConfirmedSection[]) => {
    setConfirmedSections(sections);
    // Build fileResults for display (flatten back to per-file for legacy display)
    const byFile: Record<string, FileResult> = {};
    sections.forEach(sec => {
      if (!byFile[sec.fileName]) {
        const orig = pendingResults.find(r => r.fileName === sec.fileName);
        byFile[sec.fileName] = {
          fileName: sec.fileName,
          sections: [],
          pageCount: orig?.pageCount ?? 1,
          instrumentType: orig?.instrumentType ?? sec.instrument_type,
        };
      }
      byFile[sec.fileName].sections.push({
        heading: sec.heading,
        instrument_type: sec.instrument_type,
        specs: sec.specs,
      });
    });
    setFileResults(Object.values(byFile));
    setStep('template_assign');
  };

  const downloadBlob = async (endpoint: string, name: string) => {
    const res = await api.get(endpoint, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement('a'); a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  };

  const isProcessing = ['uploading', 'ocr', 'ai', 'mapping'].includes(step);
  const allSpecs = confirmedSections.flatMap(s => s.specs);
  const avgConf = allSpecs.length ? Math.round(allSpecs.reduce((a, s) => a + s.confidence, 0) / allSpecs.length) : 0;
  const instrumentTypes = [...new Set(confirmedSections.map(s => s.instrument_type).filter(Boolean))];

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Template popup */}
      {showTemplatePrompt && (
        <TemplatePrompt
          onConfirm={f => { setTemplateFile(f); runExtract(f); }}
          onSkip={() => runExtract(null)}
        />
      )}

      {/* Header */}
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center shadow-lg shadow-violet-200 animate-float flex-shrink-0">
          <ScanSearch className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-black text-gray-900 leading-tight">
            Smart <span className="text-gradient">Specification</span> Extraction
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            OCR → Llama 3.3 70B → Section-aware extraction → Review → Datasheet
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full flex-shrink-0">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs font-semibold text-green-700">AI Online</span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-2xl animate-fade-in-up">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1"><p className="text-sm font-semibold text-red-700">Extraction Failed</p><p className="text-xs text-red-500 mt-0.5">{error}</p></div>
          <button onClick={() => setError(null)}><X className="w-4 h-4 text-red-400 hover:text-red-600" /></button>
        </div>
      )}

      {/* Upload cards — only show when not in review / template_assign / done */}
      {!['review', 'template_assign', 'done'].includes(step) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card-premium p-5 space-y-4">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-500" />
              <span className="text-sm font-bold text-gray-800">Tender / Vendor Documents</span>
              <span className="text-[10px] px-2 py-0.5 bg-blue-100 text-blue-600 rounded-full font-bold">BATCH</span>
            </div>
            <MultiDropZone files={files} onFilesChange={f => { setFiles(f); if (step !== 'idle') reset(); }} disabled={isProcessing} />
            <button
              onClick={startExtract}
              disabled={!files.length || isProcessing}
              className="w-full py-3 px-4 rounded-xl font-bold text-sm transition-all duration-200 flex items-center justify-center gap-2
                bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-200
                hover:from-blue-700 hover:to-blue-800 hover:shadow-xl hover:-translate-y-0.5
                disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
            >
              {isProcessing
                ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Processing file {currentFileIdx + 1} of {files.length}…</>
                : <><ScanSearch className="w-4 h-4" />{files.length > 1 ? `Extract All (${files.length} files)` : 'Extract Specifications'}</>}
            </button>
          </div>

          <div className="card-premium p-5 space-y-4">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4 text-violet-500" />
              <span className="text-sm font-bold text-gray-800">WABAG Template</span>
              <span className="text-[10px] text-gray-400 font-medium">optional — enables targeted extraction</span>
            </div>
            <div
              className={`relative border-2 border-dashed rounded-2xl p-5 text-center cursor-pointer group transition-all duration-300
                ${templateFile ? 'border-emerald-300 bg-emerald-50/40' :
                  isProcessing ? 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed' :
                  'border-gray-200 bg-white hover:border-violet-300 hover:bg-violet-50/30'}`}
              onClick={() => {
                if (isProcessing) return;
                const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.xlsx,.xlsm,.xls';
                inp.onchange = e => { const f = (e.target as HTMLInputElement).files?.[0]; if (f) setTemplateFile(f); };
                inp.click();
              }}
            >
              <div className={`w-10 h-10 rounded-xl mx-auto mb-2 flex items-center justify-center transition-all ${templateFile ? 'bg-emerald-100' : 'bg-violet-50 group-hover:bg-violet-100'}`}>
                {templateFile ? <CheckCircle2 className="w-5 h-5 text-emerald-500" /> : <FileSpreadsheet className="w-5 h-5 text-violet-400" />}
              </div>
              <p className="text-sm font-semibold text-gray-700 truncate max-w-[200px] mx-auto">{templateFile ? templateFile.name : 'Upload Template'}</p>
              {!templateFile && <p className="text-xs text-gray-400 mt-0.5">Drop or <span className="text-violet-500 font-medium">browse</span> · .xlsx / .xlsm / .xls</p>}
              {templateFile && !isProcessing && (
                <button onClick={e => { e.stopPropagation(); setTemplateFile(null); }}
                  className="absolute top-2 right-2 w-6 h-6 rounded-full bg-gray-100 hover:bg-red-100 text-gray-400 hover:text-red-500 flex items-center justify-center transition-colors">
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
            <button
              onClick={handleGenerate}
              disabled={!files.length || !templateFile || isProcessing}
              className="w-full py-3 px-4 rounded-xl font-bold text-sm transition-all duration-200 flex items-center justify-center gap-2
                bg-gradient-to-r from-violet-600 to-purple-700 text-white shadow-lg shadow-violet-200
                hover:from-violet-700 hover:to-purple-800 hover:shadow-xl hover:-translate-y-0.5
                disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
            >
              {isProcessing
                ? <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />Processing…</>
                : <><Zap className="w-4 h-4" />Extract + Populate Template</>}
            </button>
          </div>
        </div>
      )}

      {/* Processing visualizer */}
      {isProcessing && (
        <ProcessingVisualizer
          step={step} fileCount={files.length} currentFileIdx={currentFileIdx}
          fileName={files[currentFileIdx]?.name ?? ''} elapsed={elapsed}
        />
      )}

      {/* Review step */}
      {step === 'review' && pendingResults.length > 0 && (
        <ReviewPanel
          fileResults={pendingResults}
          onConfirm={handleReviewConfirm}
          onBack={reset}
        />
      )}

      {/* Template assignment step */}
      {step === 'template_assign' && confirmedSections.length > 0 && (
        <TemplateAssignment
          sections={confirmedSections}
          onDone={() => { setStep('done'); setActiveTab(generateResult ? 'mapping' : 'specs'); }}
        />
      )}

      {/* Done — results */}
      {step === 'done' && allSpecs.length > 0 && (
        <div className="space-y-4 animate-fade-in-up">
          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { icon: Activity,  label: 'Confirmed Fields', value: allSpecs.length, color: 'blue' },
              { icon: Brain,     label: 'AI Confidence',    value: `${avgConf}%`,   color: 'violet' },
              { icon: Layers,    label: 'Instrument Sections', value: confirmedSections.length, color: 'cyan' },
              { icon: BarChart3, label: 'Pages Scanned',    value: fileResults.reduce((a, r) => a + r.pageCount, 0), color: 'emerald' },
            ].map((stat, i) => {
              const Icon = stat.icon;
              return (
                <div key={i} className={`card-premium p-4 animate-fade-in-up animation-delay-${(i + 1) * 100}`}>
                  <div className={`w-8 h-8 rounded-xl mb-2 flex items-center justify-center bg-${stat.color}-100`}>
                    <Icon className={`w-4 h-4 text-${stat.color}-600`} />
                  </div>
                  <p className="text-2xl font-black text-gray-900">{stat.value}</p>
                  <p className="text-xs text-gray-500 font-medium">{stat.label}</p>
                </div>
              );
            })}
          </div>

          {/* Instrument types + action row */}
          <div className="flex items-center gap-3 flex-wrap">
            {instrumentTypes.map((t, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-2 bg-violet-50 border border-violet-200 rounded-xl">
                <Layers className="w-3.5 h-3.5 text-violet-500" />
                <span className="text-xs font-bold text-violet-700">{t}</span>
              </div>
            ))}
            <div className="flex items-center gap-2 px-3 py-2 bg-emerald-50 border border-emerald-200 rounded-xl">
              <Clock className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-xs font-semibold text-emerald-700">Completed in {formatTime(elapsed)}</span>
            </div>
            <button onClick={reset} className="ml-auto px-4 py-2 rounded-xl border-2 border-gray-200 text-xs font-bold text-gray-600 hover:border-blue-300 hover:text-blue-600 transition-all">
              ← New Upload
            </button>
          </div>

          {/* Sections table */}
          <div className="card-premium overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
              <div className="flex gap-1">
                {(['specs', 'mapping'] as const)
                  .filter(t => t === 'specs' || !!generateResult)
                  .map(tab => (
                    <button key={tab} onClick={() => setActiveTab(tab)}
                      className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${activeTab === tab ? 'bg-blue-600 text-white shadow-md' : 'text-gray-500 hover:bg-gray-100'}`}>
                      {tab === 'specs' ? `Specifications (${allSpecs.length})` : `Mapping (${generateResult?.mapping_log.length ?? 0})`}
                    </button>
                  ))}
              </div>
              <div className="flex gap-2">
                <button onClick={() => downloadBlob('/sdie/extract/download', 'Extracted_Specs.xlsx')}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 transition-colors">
                  <Download className="w-3.5 h-3.5" /> Export Excel
                </button>
                {generateResult && (
                  <button onClick={() => downloadBlob('/sdie/download', generateResult.filename)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white rounded-lg text-xs font-bold hover:bg-violet-700 transition-colors">
                    <Download className="w-3.5 h-3.5" /> Download Datasheet
                  </button>
                )}
              </div>
            </div>

            {activeTab === 'specs' && (
              <div className="overflow-auto max-h-[600px]">
                {confirmedSections.map((sec, si) => (
                  <div key={si}>
                    <div className="px-5 py-2.5 bg-gradient-to-r from-slate-50 to-blue-50 border-b border-gray-100 flex items-center gap-2 sticky top-0 z-10">
                      <Layers className="w-3.5 h-3.5 text-blue-500" />
                      <span className="text-xs font-black text-blue-800">{sec.heading}</span>
                      {sec.instrument_type && (
                        <span className="px-2 py-0.5 bg-violet-100 text-violet-700 rounded-full text-[10px] font-bold">{sec.instrument_type}</span>
                      )}
                      <span className="text-[10px] text-gray-400 ml-auto">{sec.specs.length} fields · {sec.fileName}</span>
                    </div>
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50 sticky top-[37px]">
                        <tr>{['Field', 'Value', 'Confidence'].map(h => <th key={h} className="px-4 py-2.5 text-left font-bold text-gray-600 whitespace-nowrap">{h}</th>)}</tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {sec.specs.map((spec, i) => (
                          <tr key={i} className="hover:bg-blue-50/40 transition-colors animate-fade-in">
                            <td className="px-4 py-2.5 font-semibold text-gray-800 whitespace-nowrap">{spec.raw_label}</td>
                            <td className="px-4 py-2.5 text-gray-700 max-w-[200px] truncate" title={spec.value}>{spec.value}</td>
                            <td className="px-4 py-2.5"><ConfidenceBar value={spec.confidence} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'mapping' && generateResult && (
              <div className="overflow-auto max-h-[500px]">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>{['Template Field', 'Mapped To', 'Match Score', 'Value', 'Status'].map(h => <th key={h} className="px-4 py-2.5 text-left font-bold text-gray-600 whitespace-nowrap">{h}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {generateResult.mapping_log.map((entry, i) => (
                      <tr key={i} className="hover:bg-violet-50/40 transition-colors">
                        <td className="px-4 py-2.5 font-semibold text-gray-800 whitespace-nowrap">{entry.heading}</td>
                        <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">{entry.canonical_field ?? <span className="italic text-gray-300">—</span>}</td>
                        <td className="px-4 py-2.5"><ConfidenceBar value={entry.score} /></td>
                        <td className="px-4 py-2.5 text-gray-700 max-w-[180px] truncate" title={entry.value}>{entry.value || <span className="italic text-gray-300">—</span>}</td>
                        <td className="px-4 py-2.5">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${entry.status === 'MATCHED' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-gray-50 text-gray-400 border-gray-200'}`}>{entry.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {step === 'done' && allSpecs.length === 0 && (
        <div className="card-premium p-12 text-center animate-fade-in-up">
          <div className="w-16 h-16 rounded-2xl bg-yellow-50 flex items-center justify-center mx-auto mb-4"><AlertCircle className="w-8 h-8 text-yellow-400" /></div>
          <p className="text-gray-600 font-semibold">No specifications found</p>
          <p className="text-sm text-gray-400 mt-1">Try a clearer scan or different document format</p>
          <button onClick={reset} className="mt-4 px-4 py-2 rounded-xl border-2 border-gray-200 text-xs font-bold text-gray-600 hover:border-blue-300 transition-all">Try Again</button>
        </div>
      )}
    </div>
  );
}
