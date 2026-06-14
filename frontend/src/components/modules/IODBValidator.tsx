/**
 * IODB Validator Component
 * Full-featured validation with dynamic rules management
 */
import { useState } from 'react';
import {
  CheckCircle2,
  FileText,
  Download,
  FileCheck,
  Settings
} from 'lucide-react';
import api from '@/services/api';
import DynamicRulesManager from './DynamicRulesManager';
import PageHeader from '../ui/PageHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

interface ValidationError {
  row: number;
  sno: string;
  tag: string;
  column: string;
  cell: string;
  message: string;
  rule: number | string;
  rule_name?: string;
  rule_type?: string;
  source?: string;
}

interface ValidationResult {
  errors: ValidationError[];
  error_count: number;
  has_error_log: boolean;
  has_highlighted: boolean;
  has_tba: boolean;
  message?: string;
}

export default function IODBValidator() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [autoCorrect, setAutoCorrect] = useState(false);
  const [validating, setValidating] = useState(false);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [showRulesManager, setShowRulesManager] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setResult(null); // Clear previous results
      setError(null);
    }
  };

  const handleValidate = async () => {
    if (!selectedFile) return;

    setValidating(true);
    setError(null);
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('auto_correct_spelling', autoCorrect.toString());

    try {
      const response = await api.post<ValidationResult>('/validator/validate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Validation failed');
    } finally {
      setValidating(false);
    }
  };

  const handleDownload = async (type: 'error-log' | 'highlighted' | 'tba') => {
    setDownloading(type);
    setError(null);
    try {
      const response = await api.get(`/validator/download/${type}`, {
        responseType: 'blob',
      });

      const filename =
        type === 'error-log' ? 'IODB_Validation_Report.xlsx' :
        type === 'highlighted' ? 'IODB_Highlighted.xlsx' :
        'TBA_details.xlsx';

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Download failed');
    } finally {
      setDownloading(null);
    }
  };

  // Group errors by row
  const errorsByRow = result?.errors.reduce((acc, error) => {
    if (!acc[error.row]) {
      acc[error.row] = [];
    }
    acc[error.row].push(error);
    return acc;
  }, {} as Record<number, ValidationError[]>);

  // Calculate metrics
  const predefinedErrors = result?.errors.filter(e => e.source !== 'dynamic') || [];
  const dynamicErrors = result?.errors.filter(e => e.source === 'dynamic') || [];
  const emptyErrors = predefinedErrors.filter(e => e.rule === 1);
  const logicErrors = predefinedErrors.filter(e => typeof e.rule === 'number' && e.rule >= 2 && e.rule <= 10);
  const orderErrors = predefinedErrors.filter(e => e.rule === 11);
  const spellingErrors = predefinedErrors.filter(e => e.rule === 12);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={CheckCircle2}
        iconClassName="text-blue-500"
        title="IODB Validator"
        description="Upload your IODB Excel file to run validation rules and generate detailed error reports."
      />

      {error && <Alert variant="error" title="Error">{error}</Alert>}

      {/* Rules Manager Toggle */}
      <Card className="bg-blue-50 border-blue-200">
        <button
          onClick={() => setShowRulesManager(!showRulesManager)}
          className="flex items-center gap-2 text-primary-700 font-medium hover:text-primary-900"
        >
          <Settings className="w-5 h-5" />
          {showRulesManager ? 'Hide' : 'Show'} Dynamic Rules Manager
        </button>
      </Card>

      {/* Dynamic Rules Manager */}
      {showRulesManager && (
        <div className="border border-gray-200 rounded-lg p-6 bg-gray-50">
          <DynamicRulesManager />
        </div>
      )}

      {/* File Upload Section */}
      <Card title="Upload IODB File" icon={FileText}>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select IODB Excel File (.xlsx, .xls)
            </label>
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none file:mr-4 file:py-2 file:px-4 file:border-0 file:bg-primary-50 file:text-primary-700 file:font-medium"
            />
            {selectedFile && (
              <p className="mt-2 text-sm text-green-600">
                ✓ Selected: <strong>{selectedFile.name}</strong>
              </p>
            )}
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="autoCorrect"
              checked={autoCorrect}
              onChange={(e) => setAutoCorrect(e.target.checked)}
              className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
            />
            <label htmlFor="autoCorrect" className="ml-2 text-sm text-gray-700">
              Auto-correct spelling in highlighted output
            </label>
          </div>

          <Button
            onClick={handleValidate}
            disabled={!selectedFile}
            loading={validating}
            size="lg"
            fullWidth
          >
            <FileCheck className="w-5 h-5" />
            {validating ? 'Validating...' : 'Run Validation'}
          </Button>
        </div>
      </Card>

      {/* Results Section */}
      {result && (
        <>
          {/* Metrics */}
          {result.error_count === 0 ? (
            <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
              <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto mb-3" />
              <h3 className="text-xl font-bold text-green-800">No Errors Found!</h3>
              <p className="text-green-700 mt-2">Your IODB file passed all validation checks.</p>
            </div>
          ) : (
            <>
              <Card title="Validation Results">

                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                  <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
                    <div className="text-3xl font-bold text-red-600">{result.error_count}</div>
                    <div className="text-sm text-red-700 mt-1">Total Errors</div>
                  </div>
                  <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 text-center">
                    <div className="text-3xl font-bold text-orange-600">{emptyErrors.length}</div>
                    <div className="text-sm text-orange-700 mt-1">Empty Cells</div>
                  </div>
                  <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-center">
                    <div className="text-3xl font-bold text-yellow-600">{logicErrors.length}</div>
                    <div className="text-sm text-yellow-700 mt-1">Logic Errors</div>
                  </div>
                  <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 text-center">
                    <div className="text-3xl font-bold text-purple-600">{orderErrors.length}</div>
                    <div className="text-sm text-purple-700 mt-1">Order Errors</div>
                  </div>
                  <div className="bg-pink-50 border border-pink-200 rounded-lg p-4 text-center">
                    <div className="text-3xl font-bold text-pink-600">{spellingErrors.length}</div>
                    <div className="text-sm text-pink-700 mt-1">Spelling</div>
                  </div>
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-center">
                    <div className="text-3xl font-bold text-blue-600">{dynamicErrors.length}</div>
                    <div className="text-sm text-blue-700 mt-1">Dynamic Rules</div>
                  </div>
                </div>
              </Card>

              {/* Errors by Row */}
              <Card title={`Errors by Row (${Object.keys(errorsByRow || {}).length} rows affected)`}>
                <div className="space-y-3 max-h-96 overflow-y-auto">
                  {Object.entries(errorsByRow || {})
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([row, errors]) => {
                      const firstError = errors[0];
                      const hasDynamic = errors.some(e => e.source === 'dynamic');
                      
                      return (
                        <details key={row} className="border border-gray-200 rounded-lg">
                          <summary className="cursor-pointer p-4 bg-gray-50 hover:bg-gray-100 rounded-lg font-medium">
                            <span className="text-red-600">Row {row}</span>
                            <span className="text-gray-600 ml-2">| S.NO: {firstError.sno}</span>
                            <span className="text-gray-600 ml-2">| TAG: {firstError.tag}</span>
                            <span className="text-gray-600 ml-2">| {errors.length} error(s)</span>
                            {hasDynamic && <span className="ml-2 text-blue-500">🟡</span>}
                          </summary>
                          
                          <div className="p-4 space-y-2">
                            {errors.map((error, idx) => (
                              <div key={idx} className="bg-red-50 border-l-4 border-red-500 p-3 rounded">
                                {error.source === 'dynamic' && (
                                  <div className="mb-2">
                                    <span className="inline-block bg-green-100 text-green-800 text-xs px-2 py-1 rounded mr-2">
                                      {error.rule_type}
                                    </span>
                                    <span className="inline-block bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded">
                                      Dynamic Rule
                                    </span>
                                  </div>
                                )}
                                <div className="text-sm text-gray-700 font-mono mb-2">
                                  Column: <strong>{error.column}</strong> | Cell: <strong>{error.cell}</strong>
                                </div>
                                <div className="text-red-700 font-medium text-center">
                                  → {error.message}
                                </div>
                              </div>
                            ))}
                          </div>
                        </details>
                      );
                    })}
                </div>
              </Card>
            </>
          )}

          {/* Download Buttons */}
          <Card title="Download Reports">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {result.has_error_log && (
                <Button
                  onClick={() => handleDownload('error-log')}
                  loading={downloading === 'error-log'}
                  variant="danger"
                  size="lg"
                >
                  <Download className="w-5 h-5" />
                  Error Log (Excel)
                </Button>
              )}

              {result.has_highlighted && (
                <Button
                  onClick={() => handleDownload('highlighted')}
                  loading={downloading === 'highlighted'}
                  size="lg"
                  className="bg-orange-600 hover:bg-orange-700"
                >
                  <Download className="w-5 h-5" />
                  Highlighted IODB
                </Button>
              )}

              {result.has_tba && (
                <Button
                  onClick={() => handleDownload('tba')}
                  loading={downloading === 'tba'}
                  size="lg"
                  className="bg-blue-600 hover:bg-blue-700"
                >
                  <Download className="w-5 h-5" />
                  TBA Details
                </Button>
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
