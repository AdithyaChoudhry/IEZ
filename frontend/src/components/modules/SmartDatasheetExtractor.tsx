import { useState, useCallback } from 'react';
import {
  ScanSearch, Upload, FileSpreadsheet, Download, Zap,
  CheckCircle2, AlertCircle, FileText, Brain, Cpu, ChevronRight,
  BarChart3, Tag, Activity
} from 'lucide-react';
import api from '@/services/api';

interface ExtractedSpec {
  raw_label: string;
  value: string;
  canonical_field: string | null;
  match_score: number;
  confidence: number;
  page: number;
  source?: string;
}

interface ExtractionResponse {
  specs: ExtractedSpec[];
  page_count: number;
  message: string;
}

interface GenerateResponse extends ExtractionResponse {
  mapping_log: Array<{
    heading: string;
    canonical_field: string | null;
    score: number;
    value: string;
    status: 'MATCHED' | 'UNMATCHED';
  }>;
  filename: string;
}

const POLL_MS = 3000;
const MAX_POLLS = 200;

type Step = 'idle' | 'uploading' | 'ocr' | 'ai' | 'mapping' | 'done' | 'error';

const STEPS = [
  { key: 'ocr',     icon: Cpu,   label: 'OCR Scanning',    desc: 'Extracting text from document' },
  { key: 'ai',      icon: Brain, label: 'AI Analysis',     desc: 'Llama 3.3 reading specifications' },
  { key: 'mapping', icon: Tag,   label: 'Field Mapping',   desc: 'Mapping to WABAG standard fields' },
  { key: 'done',    icon: CheckCircle2, label: 'Complete', desc: 'Extraction successful' },
];

function ConfidenceBar({ value, source }: { value: number; source?: string }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-amber-400' : 'bg-red-400';
  const textColor = value >= 80 ? 'text-emerald-600' : value >= 60 ? 'text-amber-600' : 'text-red-500';
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className={`text-xs font-bold tabular-nums ${textColor}`}>{value.toFixed(0)}%</span>
      {source === 'ai' && (
        <span className="text-[9px] font-bold px-1 py-0.5 bg-violet-100 text-violet-600 rounded border border-violet-200">AI</span>
      )}
    </div>
  );
}

function StepIndicator({ step }: { step: Step }) {
  const stepOrder: Step[] = ['uploading', 'ocr', 'ai', 'mapping', 'done'];
  const currentIdx = stepOrder.indexOf(step);

  return (
    <div className="flex items-center gap-2 py-4">
      {STEPS.map((s, i) => {
        const sIdx = i;
        const done = currentIdx > sIdx + 1;
        const active = currentIdx === sIdx + 1;
        const Icon = s.icon;
        return (
          <div key={s.key} className="flex items-center gap-2">
            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold transition-all duration-500 ${
              done   ? 'bg-emerald-100 text-emerald-700 border border-emerald-200' :
              active ? 'bg-blue-600 text-white shadow-lg shadow-blue-200 animate-pulse' :
                       'bg-gray-100 text-gray-400'
            }`}>
              <Icon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{s.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <ChevronRight className={`w-3 h-3 flex-shrink-0 ${done ? 'text-emerald-400' : 'text-gray-300'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function DropZone({
  title, icon: Icon, accept, file, onChange, hint, disabled
}: {
  title: string; icon: React.ElementType; accept: string;
  file: File | null; onChange: (f: File | null) => void;
  hint?: string; disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const f = e.dataTransfer.files[0];
    if (f) onChange(f);
  }, [onChange, disabled]);

  return (
    <div
      onDragOver={e => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`relative border-2 border-dashed rounded-2xl p-6 text-center transition-all duration-300 cursor-pointer group
        ${dragging ? 'border-blue-400 bg-blue-50 scale-[1.01]' :
          file ? 'border-emerald-300 bg-emerald-50/50' :
          disabled ? 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed' :
          'border-gray-200 bg-white hover:border-blue-300 hover:bg-blue-50/30'}`}
      onClick={() => {
        if (disabled) return;
        const input = document.createElement('input');
        input.type = 'file'; input.accept = accept;
        input.onchange = (e) => {
          const f = (e.target as HTMLInputElement).files?.[0];
          if (f) onChange(f);
        };
        input.click();
      }}
    >
      <div className={`w-12 h-12 rounded-2xl mx-auto mb-3 flex items-center justify-center transition-all duration-300
        ${file ? 'bg-emerald-100' : 'bg-blue-50 group-hover:bg-blue-100'}`}>
        {file
          ? <CheckCircle2 className="w-6 h-6 text-emerald-500" />
          : <Icon className="w-6 h-6 text-blue-400 group-hover:text-blue-600 group-hover:scale-110 transition-all" />
        }
      </div>
      <p className="text-sm font-semibold text-gray-700 mb-0.5">{title}</p>
      {file ? (
        <p className="text-xs text-emerald-600 font-medium truncate max-w-[180px] mx-auto">{file.name}</p>
      ) : (
        <p className="text-xs text-gray-400">Drop here or <span className="text-blue-500 font-medium">browse</span></p>
      )}
      {hint && !file && <p className="text-[10px] text-gray-400 mt-1 leading-tight">{hint}</p>}
      {file && (
        <button
          onClick={e => { e.stopPropagation(); onChange(null); }}
          className="absolute top-2 right-2 w-6 h-6 rounded-full bg-gray-100 hover:bg-red-100 hover:text-red-500 flex items-center justify-center text-gray-400 text-xs transition-colors"
        >✕</button>
      )}
    </div>
  );
}

export default function SmartDatasheetExtractor() {
  const [file, setFile] = useState<File | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [step, setStep] = useState<Step>('idle');
  const [result, setResult] = useState<ExtractionResponse | null>(null);
  const [generateResult, setGenerateResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'specs' | 'mapping'>('specs');

  const reset = () => { setResult(null); setGenerateResult(null); setError(null); setStep('idle'); };


  const handleExtract = async () => {
    if (!file) return;
    reset();
    setStep('uploading');
    const formData = new FormData();
    formData.append('file', file);
    try {
      const kickoff = await api.post<{ job_id: string }>('/sdie/extract', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setStep('ocr');
      await new Promise(r => setTimeout(r, 1200));
      setStep('ai');
      await new Promise(r => setTimeout(r, 1200));
      setStep('mapping');

      for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
        await new Promise(r => setTimeout(r, POLL_MS));
        const res = await api.get<any>(`/sdie/extract/status/${kickoff.data.job_id}`);
        if (res.data.status === 'done') {
          setResult(res.data.result);
          setStep('done');
          setActiveTab('specs');
          return;
        }
        if (res.data.status === 'error') throw new Error(res.data.error || 'Failed');
      }
      throw new Error('Timeout');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Extraction failed');
      setStep('error');
    }
  };

  const handleGenerate = async () => {
    if (!file || !templateFile) return;
    reset();
    setStep('uploading');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('template_file', templateFile);
    try {
      const kickoff = await api.post<{ job_id: string }>('/sdie/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setStep('ocr');
      await new Promise(r => setTimeout(r, 1200));
      setStep('ai');
      await new Promise(r => setTimeout(r, 1200));
      setStep('mapping');

      for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
        await new Promise(r => setTimeout(r, POLL_MS));
        const res = await api.get<any>(`/sdie/generate/status/${kickoff.data.job_id}`);
        if (res.data.status === 'done') {
          setGenerateResult(res.data.result);
          setStep('done');
          setActiveTab('mapping');
          return;
        }
        if (res.data.status === 'error') throw new Error(res.data.error || 'Failed');
      }
      throw new Error('Timeout');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Generation failed');
      setStep('error');
    }
  };

  const downloadBlob = async (endpoint: string, name: string) => {
    const res = await api.get(endpoint, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement('a'); a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  };

  const isProcessing = ['uploading', 'ocr', 'ai', 'mapping'].includes(step);
  const specs = result?.specs ?? generateResult?.specs ?? [];
  const aiCount = specs.filter(s => s.source === 'ai').length;
  const ocrCount = specs.filter(s => s.source !== 'ai').length;
  const avgConf = specs.length ? Math.round(specs.reduce((a, s) => a + s.confidence, 0) / specs.length) : 0;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Page Header */}
      <div className="flex items-start gap-4">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center shadow-lg shadow-violet-200 animate-float">
          <ScanSearch className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-black text-gray-900 leading-tight">
            Smart <span className="text-gradient">Specification</span> Extraction
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            AI-powered OCR → Llama 3.3 70B → WABAG field mapping
          </p>
        </div>
        <div className="ml-auto flex items-center gap-1.5 px-3 py-1.5 bg-green-50 border border-green-200 rounded-full">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          <span className="text-xs font-semibold text-green-700">AI Online</span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-200 rounded-2xl animate-fade-in-up">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-red-700">Extraction Failed</p>
            <p className="text-xs text-red-500 mt-0.5">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 text-lg leading-none">×</button>
        </div>
      )}

      {/* Upload Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card-premium p-5 space-y-4">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-blue-500" />
            <span className="text-sm font-bold text-gray-800">Tender / Vendor Document</span>
          </div>
          <DropZone
            title="Upload Document"
            icon={Upload}
            accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff"
            file={file}
            onChange={(f) => { setFile(f); reset(); }}
            hint="PDF, JPG, PNG, TIFF supported"
            disabled={isProcessing}
          />
          <button
            onClick={handleExtract}
            disabled={!file || isProcessing}
            className="w-full py-3 px-4 rounded-xl font-bold text-sm transition-all duration-200 flex items-center justify-center gap-2
              bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg shadow-blue-200
              hover:from-blue-700 hover:to-blue-800 hover:shadow-xl hover:-translate-y-0.5
              disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
          >
            {isProcessing && step !== 'mapping' ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <ScanSearch className="w-4 h-4" />
                Extract Specifications
              </>
            )}
          </button>
        </div>

        <div className="card-premium p-5 space-y-4">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-violet-500" />
            <span className="text-sm font-bold text-gray-800">WABAG Template (optional)</span>
          </div>
          <DropZone
            title="Upload Template"
            icon={FileSpreadsheet}
            accept=".xlsx,.xlsm"
            file={templateFile}
            onChange={(f) => { setTemplateFile(f); reset(); }}
            hint="Auto-fills 'Refer Annexure' placeholders"
            disabled={isProcessing}
          />
          <button
            onClick={handleGenerate}
            disabled={!file || !templateFile || isProcessing}
            className="w-full py-3 px-4 rounded-xl font-bold text-sm transition-all duration-200 flex items-center justify-center gap-2
              bg-gradient-to-r from-violet-600 to-purple-700 text-white shadow-lg shadow-violet-200
              hover:from-violet-700 hover:to-purple-800 hover:shadow-xl hover:-translate-y-0.5
              disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
          >
            {isProcessing ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Zap className="w-4 h-4" />
                Generate Populated Datasheet
              </>
            )}
          </button>
        </div>
      </div>

      {/* Step Indicator */}
      {isProcessing && (
        <div className="card-premium p-4 animate-fade-in-up">
          <StepIndicator step={step} />
          <div className="mt-2 h-1 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-violet-500 rounded-full transition-all duration-1000"
              style={{ width: step === 'ocr' ? '25%' : step === 'ai' ? '55%' : step === 'mapping' ? '80%' : '100%' }}
            />
          </div>
        </div>
      )}

      {/* Results */}
      {(step === 'done' || step === 'error') && specs.length > 0 && (
        <div className="space-y-4 animate-fade-in-up">
          {/* Stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { icon: Activity, label: 'Total Fields', value: specs.length, color: 'blue' },
              { icon: Brain, label: 'AI Extracted', value: aiCount, color: 'violet' },
              { icon: Cpu, label: 'OCR Extracted', value: ocrCount, color: 'cyan' },
              { icon: BarChart3, label: 'Avg Confidence', value: `${avgConf}%`, color: 'emerald' },
            ].map((stat, i) => {
              const Icon = stat.icon;
              return (
                <div key={i} className={`card-premium p-4 animate-fade-in-up animation-delay-${(i+1)*100}`}>
                  <div className={`w-8 h-8 rounded-xl mb-2 flex items-center justify-center bg-${stat.color}-100`}>
                    <Icon className={`w-4 h-4 text-${stat.color}-600`} />
                  </div>
                  <p className="text-2xl font-black text-gray-900">{stat.value}</p>
                  <p className="text-xs text-gray-500 font-medium">{stat.label}</p>
                </div>
              );
            })}
          </div>

          {/* Tabs + Download */}
          <div className="card-premium overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
              <div className="flex gap-1">
                {(['specs', 'mapping'] as const).filter(t => t === 'specs' || !!generateResult).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      activeTab === tab
                        ? 'bg-blue-600 text-white shadow-md'
                        : 'text-gray-500 hover:bg-gray-100'
                    }`}
                  >
                    {tab === 'specs' ? `Specifications (${specs.length})` : `Mapping (${generateResult?.mapping_log.length ?? 0})`}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                {result && (
                  <button
                    onClick={() => downloadBlob('/sdie/extract/download', 'Extracted_Specs.xlsx')}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" /> Export Excel
                  </button>
                )}
                {generateResult && (
                  <button
                    onClick={() => downloadBlob('/sdie/download', generateResult.filename)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white rounded-lg text-xs font-bold hover:bg-violet-700 transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" /> Download Datasheet
                  </button>
                )}
              </div>
            </div>

            {/* Specs Table */}
            {activeTab === 'specs' && (
              <div className="overflow-auto max-h-[460px]">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      {['Field', 'Value', 'Mapped To', 'Confidence', 'Page'].map(h => (
                        <th key={h} className="px-4 py-2.5 text-left font-bold text-gray-600 whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {specs.map((spec, i) => (
                      <tr key={i} className={`hover:bg-blue-50/40 transition-colors animate-fade-in animation-delay-${Math.min(i * 50, 500)}ms`}>
                        <td className="px-4 py-2.5 font-semibold text-gray-800 whitespace-nowrap">
                          {spec.raw_label}
                        </td>
                        <td className="px-4 py-2.5 text-gray-700 max-w-[200px] truncate" title={spec.value}>
                          {spec.value}
                        </td>
                        <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">
                          {spec.canonical_field ?? <span className="italic text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5">
                          <ConfidenceBar value={spec.confidence} source={spec.source} />
                        </td>
                        <td className="px-4 py-2.5 text-gray-400">{spec.page}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Mapping Table */}
            {activeTab === 'mapping' && generateResult && (
              <div className="overflow-auto max-h-[460px]">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      {['Template Field', 'Mapped To', 'Match', 'Value', 'Status'].map(h => (
                        <th key={h} className="px-4 py-2.5 text-left font-bold text-gray-600 whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {generateResult.mapping_log.map((entry, i) => (
                      <tr key={i} className="hover:bg-violet-50/40 transition-colors">
                        <td className="px-4 py-2.5 font-semibold text-gray-800 whitespace-nowrap">{entry.heading}</td>
                        <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">
                          {entry.canonical_field ?? <span className="italic text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5">
                          <ConfidenceBar value={entry.score} />
                        </td>
                        <td className="px-4 py-2.5 text-gray-700 max-w-[180px] truncate" title={entry.value}>
                          {entry.value || <span className="italic text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                            entry.status === 'MATCHED'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-gray-50 text-gray-400 border-gray-200'
                          }`}>
                            {entry.status}
                          </span>
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

      {/* Empty done state */}
      {step === 'done' && specs.length === 0 && (
        <div className="card-premium p-12 text-center animate-fade-in-up">
          <div className="w-16 h-16 rounded-2xl bg-yellow-50 flex items-center justify-center mx-auto mb-4">
            <AlertCircle className="w-8 h-8 text-yellow-400" />
          </div>
          <p className="text-gray-600 font-semibold">No specifications extracted</p>
          <p className="text-sm text-gray-400 mt-1">Try a clearer image or different document format</p>
        </div>
      )}
    </div>
  );
}
