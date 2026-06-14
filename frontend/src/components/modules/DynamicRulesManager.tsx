/**
 * Dynamic Rules Manager Component
 * CRUD operations for user-defined validation rules
 */
import { useState, useEffect } from 'react';
import { Plus, Trash2, Edit2, Save, X, Loader2 } from 'lucide-react';
import api from '@/services/api';

interface DynamicRule {
  id: string;
  name: string;
  rule_type: 'COLUMN' | 'ROW' | 'DUPLICATE';
  conditions: Array<{
    column: string;
    operator: string;
    value: string;
    logical_operator: string;
  }>;
  target_column?: string;
  error_message: string;
  case_sensitive: boolean;
  priority: number;
  is_active: boolean;
}

const RULE_TYPES = ['COLUMN', 'ROW', 'DUPLICATE'];
const OPERATORS = ['==', '!=', 'contains', '!contains', 'in', '!in', 'empty', '!empty'];
const OPERATOR_LABELS: Record<string, string> = {
  '==': 'equals',
  '!=': 'not equals',
  'contains': 'contains',
  '!contains': 'not contains',
  'in': 'in list',
  '!in': 'not in list',
  'empty': 'is empty',
  '!empty': 'is not empty',
};
const LOGICAL_OPERATORS = ['AND', 'OR'];

export default function DynamicRulesManager() {
  const [rules, setRules] = useState<DynamicRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [formData, setFormData] = useState<Partial<DynamicRule>>({
    name: '',
    rule_type: 'COLUMN',
    conditions: [{ column: '', operator: '==', value: '', logical_operator: 'AND' }],
    error_message: '',
    case_sensitive: false,
    priority: 100,
    is_active: true,
  });

  useEffect(() => {
    loadRules();
  }, []);

  const loadRules = async () => {
    try {
      const response = await api.get<DynamicRule[]>('/validator/rules');
      setRules(response.data);
    } catch (error) {
      console.error('Failed to load rules:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddCondition = () => {
    setFormData({
      ...formData,
      conditions: [
        ...(formData.conditions || []),
        { column: '', operator: '==', value: '', logical_operator: 'AND' }
      ]
    });
  };

  const handleRemoveCondition = (index: number) => {
    setFormData({
      ...formData,
      conditions: formData.conditions?.filter((_, i) => i !== index)
    });
  };

  const handleConditionChange = (index: number, field: string, value: string) => {
    const newConditions = [...(formData.conditions || [])];
    newConditions[index] = { ...newConditions[index], [field]: value };
    setFormData({ ...formData, conditions: newConditions });
  };

  const handleSubmit = async () => {
    try {
      if (editing) {
        await api.put(`/api/validator/rules/${editing}`, formData);
      } else {
        await api.post('/validator/rules', formData);
      }
      await loadRules();
      resetForm();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to save rule');
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this rule?')) return;
    
    try {
      await api.delete(`/api/validator/rules/${id}`);
      await loadRules();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to delete rule');
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await api.patch(`/api/validator/rules/${id}/toggle`);
      await loadRules();
    } catch (error: any) {
      alert(error.response?.data?.detail || 'Failed to toggle rule');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      rule_type: 'COLUMN',
      conditions: [{ column: '', operator: '==', value: '', logical_operator: 'AND' }],
      error_message: '',
      case_sensitive: false,
      priority: 100,
      is_active: true,
    });
    setEditing(null);
    setShowAddForm(false);
  };

  const startEdit = (rule: DynamicRule) => {
    setFormData(rule);
    setEditing(rule.id);
    setShowAddForm(true);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-800">Dynamic Validation Rules</h3>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-2 bg-primary-600 text-white py-2 px-4 rounded-lg hover:bg-primary-700"
        >
          {showAddForm ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showAddForm ? 'Cancel' : 'Add Rule'}
        </button>
      </div>

      {/* Existing Rules */}
      {rules.length === 0 ? (
        <p className="text-gray-500 text-center py-4">No custom rules defined yet.</p>
      ) : (
        <div className="space-y-3">
          {rules.map((rule) => (
            <div key={rule.id} className="border border-gray-200 rounded-lg p-4 bg-white">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`px-2 py-1 text-xs rounded ${
                      rule.rule_type === 'ROW' ? 'bg-green-100 text-green-800' :
                      rule.rule_type === 'DUPLICATE' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-blue-100 text-blue-800'
                    }`}>
                      {rule.rule_type}
                    </span>
                    <span className="font-semibold text-gray-800">{rule.name}</span>
                  </div>
                  
                  <p className="text-sm text-gray-600 mb-2">
                    {rule.rule_type === 'DUPLICATE' 
                      ? `Check "${rule.conditions[0]?.column}" for duplicates`
                      : rule.conditions.map((c, i) => (
                          <span key={i}>
                            {i > 0 && ` ${c.logical_operator} `}
                            <code className="bg-gray-100 px-1">{c.column}</code>
                            {' '}{OPERATOR_LABELS[c.operator] || c.operator}{' '}
                            <code className="bg-gray-100 px-1">{c.value || '(empty)'}</code>
                          </span>
                        ))
                    }
                  </p>
                  
                  <p className="text-sm text-red-600">→ {rule.error_message}</p>
                  
                  <div className="text-xs text-gray-500 mt-2">
                    Priority: {rule.priority} | Case-sensitive: {rule.case_sensitive ? 'Yes' : 'No'}
                  </div>
                </div>
                
                <div className="flex items-center gap-2 ml-4">
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={rule.is_active}
                      onChange={() => handleToggle(rule.id)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
                  </label>
                  
                  <button
                    onClick={() => startEdit(rule)}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  
                  <button
                    onClick={() => handleDelete(rule.id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/Edit Form */}
      {showAddForm && (
        <div className="border border-primary-300 rounded-lg p-6 bg-primary-50">
          <h4 className="font-semibold text-gray-800 mb-4">
            {editing ? 'Edit Rule' : 'Add New Rule'}
          </h4>
          
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Rule Name *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  placeholder="e.g., Hazardous Area Power Check"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Rule Type *
                </label>
                <select
                  value={formData.rule_type}
                  onChange={(e) => setFormData({ ...formData, rule_type: e.target.value as any })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                >
                  {RULE_TYPES.map(type => (
                    <option key={type} value={type}>{type}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Conditions */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Conditions *
              </label>
              
              {formData.conditions?.map((condition, index) => (
                <div key={index} className="flex gap-2 mb-2">
                  {index > 0 && (
                    <select
                      value={condition.logical_operator}
                      onChange={(e) => handleConditionChange(index, 'logical_operator', e.target.value)}
                      className="w-20 px-2 py-2 border border-gray-300 rounded-lg"
                    >
                      {LOGICAL_OPERATORS.map(op => (
                        <option key={op} value={op}>{op}</option>
                      ))}
                    </select>
                  )}
                  
                  <input
                    type="text"
                    value={condition.column}
                    onChange={(e) => handleConditionChange(index, 'column', e.target.value)}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg"
                    placeholder="Column name"
                  />
                  
                  <select
                    value={condition.operator}
                    onChange={(e) => handleConditionChange(index, 'operator', e.target.value)}
                    className="w-32 px-2 py-2 border border-gray-300 rounded-lg"
                  >
                    {OPERATORS.map(op => (
                      <option key={op} value={op}>{OPERATOR_LABELS[op] || op}</option>
                    ))}
                  </select>
                  
                  <input
                    type="text"
                    value={condition.value}
                    onChange={(e) => handleConditionChange(index, 'value', e.target.value)}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg"
                    placeholder="Value"
                  />
                  
                  {formData.conditions!.length > 1 && (
                    <button
                      onClick={() => handleRemoveCondition(index)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  )}
                </div>
              ))}
              
              <button
                onClick={handleAddCondition}
                className="text-sm text-primary-600 hover:text-primary-800 flex items-center gap-1 mt-2"
              >
                <Plus className="w-4 h-4" /> Add Condition
              </button>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Error Message *
              </label>
              <input
                type="text"
                value={formData.error_message}
                onChange={(e) => setFormData({ ...formData, error_message: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                placeholder="Error message to display"
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              {formData.rule_type === 'ROW' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Target Column
                  </label>
                  <input
                    type="text"
                    value={formData.target_column || ''}
                    onChange={(e) => setFormData({ ...formData, target_column: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    placeholder="e.g., POWER SUPPLY"
                  />
                </div>
              )}
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Priority
                </label>
                <input
                  type="number"
                  value={formData.priority}
                  onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  min="1"
                  max="999"
                />
              </div>
              
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="caseSensitive"
                  checked={formData.case_sensitive}
                  onChange={(e) => setFormData({ ...formData, case_sensitive: e.target.checked })}
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded"
                />
                <label htmlFor="caseSensitive" className="ml-2 text-sm text-gray-700">
                  Case-sensitive
                </label>
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSubmit}
                className="flex items-center gap-2 bg-primary-600 text-white py-2 px-6 rounded-lg hover:bg-primary-700"
              >
                <Save className="w-4 h-4" />
                {editing ? 'Update Rule' : 'Save Rule'}
              </button>
              
              <button
                onClick={resetForm}
                className="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
