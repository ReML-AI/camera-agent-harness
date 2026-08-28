import React, { useState, useEffect } from 'react';

interface Person {
  unique_id: string;
  camera_id: string;
  person_id: number;
  frame_idx: number;
  track_id: string;
  thumbnail_path: string;
  screen_time: number;
  num_appearances: number;
  avg_confidence: number;
}

interface Label {
  role: string;
  confidence: number;
  notes: string;
}

const ROLE_OPTIONS = [
  "Not Labeled",
  "Student Nurse (Primary)",
  "Supervising Nurse/Doctor",
  "Patient/Mannequin",
  "Observer/Other",
  "Background/False Detection"
];

const ROLE_COLORS: Record<string, string> = {
  "Not Labeled": "#666666",
  "Student Nurse (Primary)": "#2196F3",
  "Supervising Nurse/Doctor": "#4CAF50",
  "Patient/Mannequin": "#FF9800",
  "Observer/Other": "#9C27B0",
  "Background/False Detection": "#F44336"
};

export default function LabelingPage() {
  const [persons, setPersons] = useState<Person[]>([]);
  const [labels, setLabels] = useState<Record<string, Label>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      // Load persons from tracking data
      const personsRes = await fetch('/api/labeling/persons');
      const personsData = await personsRes.json();
      setPersons(personsData.persons || []);

      // Load existing labels
      const labelsRes = await fetch('/api/labeling/labels');
      const labelsData = await labelsRes.json();
      setLabels(labelsData.person_labels || {});
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  const saveLabels = async () => {
    setSaving(true);
    try {
      await fetch('/api/labeling/labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person_labels: labels })
      });
      alert('Labels saved successfully!');
    } catch (error) {
      console.error('Error saving labels:', error);
      alert('Error saving labels');
    } finally {
      setSaving(false);
    }
  };

  const updateLabel = (personId: string, field: keyof Label, value: string | number) => {
    setLabels(prev => ({
      ...prev,
      [personId]: {
        ...(prev[personId] || { role: 'Not Labeled', confidence: 3, notes: '' }),
        [field]: value
      }
    }));
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const labeledCount = Object.values(labels).filter(l => l.role !== 'Not Labeled').length;
  const cameraStats = persons.reduce((acc, p) => {
    acc[p.camera_id] = (acc[p.camera_id] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-xl">Loading person tracking data...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">👥 Person Role Labeling</h1>
          <p className="text-gray-600 mt-2">
            Label detected persons with their clinical roles (per-camera tracks)
          </p>
        </div>

        {/* Stats Bar */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-sm text-gray-600">Total Persons</div>
            <div className="text-2xl font-bold">{persons.length}</div>
          </div>
          <div className="bg-white p-4 rounded-lg shadow">
            <div className="text-sm text-gray-600">Labeled</div>
            <div className="text-2xl font-bold text-green-600">
              {labeledCount}/{persons.length}
            </div>
          </div>
          {Object.entries(cameraStats).map(([cam, count]) => (
            <div key={cam} className="bg-white p-4 rounded-lg shadow">
              <div className="text-sm text-gray-600">{cam}</div>
              <div className="text-2xl font-bold">{count}</div>
            </div>
          ))}
        </div>

        {/* Save Button */}
        <div className="mb-6 flex justify-end">
          <button
            onClick={saveLabels}
            disabled={saving}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
          >
            {saving ? 'Saving...' : 'Save All Labels'}
          </button>
        </div>

        {/* Person Cards */}
        <div className="grid grid-cols-3 gap-4">
          {persons.map((person) => {
            const label = labels[person.unique_id] || {
              role: 'Not Labeled',
              confidence: 3,
              notes: ''
            };

            return (
              <div
                key={person.unique_id}
                className="bg-white rounded-lg shadow overflow-hidden flex flex-col h-[480px]"
                style={{ borderTop: `4px solid ${ROLE_COLORS[label.role]}` }}
              >
                {/* Fixed-height thumbnail with the full image visible. */}
                <div className="h-48 bg-gray-100 flex-shrink-0 relative overflow-hidden">
                  {person.thumbnail_path ? (
                    <img
                      src={`/api/thumbnails/${person.thumbnail_path.split('/').pop()}`}
                      alt={`Person ${person.person_id} Frame ${person.frame_idx}`}
                      className="w-full h-full object-contain"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-gray-400">
                      No Image
                    </div>
                  )}
                  {/* Frame badge */}
                  <div className="absolute top-2 right-2 bg-black bg-opacity-70 text-white text-xs px-2 py-1 rounded">
                    Frame {person.frame_idx}
                  </div>
                </div>

                {/* Details - Scrollable content area */}
                <div className="flex-1 p-4 overflow-y-auto flex flex-col">
                  <div className="font-semibold text-sm mb-2">
                    {person.camera_id} - Person {person.person_id}
                  </div>

                  <div className="text-xs text-gray-600 mb-3 space-y-1">
                    <div>⏱ {formatTime(person.screen_time)}</div>
                    <div>👁 {person.num_appearances} appearances</div>
                    <div>🎯 {(person.avg_confidence * 100).toFixed(0)}%</div>
                  </div>

                  {/* Role Selection */}
                  <div className="mb-2">
                    <label className="block text-xs font-medium mb-1">Role</label>
                    <select
                      value={label.role}
                      onChange={(e) => updateLabel(person.unique_id, 'role', e.target.value)}
                      className="w-full border rounded px-2 py-1 text-sm"
                    >
                      {ROLE_OPTIONS.map(role => (
                        <option key={role} value={role}>{role}</option>
                      ))}
                    </select>
                  </div>

                  {/* Confidence */}
                  <div className="mb-2">
                    <label className="block text-xs font-medium mb-1">
                      Confidence: {label.confidence}/5
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="5"
                      value={label.confidence}
                      onChange={(e) => updateLabel(person.unique_id, 'confidence', parseInt(e.target.value))}
                      className="w-full"
                    />
                  </div>

                  {/* Notes */}
                  <div className="flex-1">
                    <label className="block text-xs font-medium mb-1">Notes</label>
                    <textarea
                      value={label.notes}
                      onChange={(e) => updateLabel(person.unique_id, 'notes', e.target.value)}
                      placeholder="Optional notes..."
                      className="w-full border rounded px-2 py-1 text-xs resize-none"
                      rows={2}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {persons.length === 0 && (
          <div className="text-center py-12 bg-white rounded-lg">
            <div className="text-xl text-gray-600 mb-2">No person tracking data found</div>
            <div className="text-gray-500">
              Run Stage 1 (person tracking) first to generate tracking data.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
