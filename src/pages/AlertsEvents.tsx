import { useState } from 'react';
import {
  AlertTriangle, CheckCircle, Info, Filter, MessageSquare, Check,
  XCircle, FlaskConical, ShieldAlert, GitBranch,
  ChevronDown, ChevronUp
} from 'lucide-react';
import { SourceBadge } from '../components/SourceBadge';
import type { Alert, AlertSeverity, AlertCategory, AlarmState, ExecutionTrace } from '../types';

interface Props {
  alerts: Alert[];
  onAcknowledge: (id: string, notes: string) => Promise<void>;
  onClear: (id: string, notes: string) => Promise<void>;
  onGetTrace?: (id: string) => Promise<ExecutionTrace>;
}

function SevIcon({ sev }: { sev: AlertSeverity }) {
  if (sev === 'critical') return <AlertTriangle size={16} className="sev-crit" />;
  if (sev === 'warning') return <AlertTriangle size={16} className="sev-warn" />;
  return <Info size={16} className="sev-info" />;
}

export function AlertsEvents({ alerts, onAcknowledge, onClear, onGetTrace }: Props) {
  const [catFilter, setCatFilter] = useState<AlertCategory | 'all'>('all');
  const [sevFilter, setSevFilter] = useState<AlertSeverity | 'all'>('all');
  const [stateFilter, setStateFilter] = useState<AlarmState | 'all'>('all');

  const [activeAckModal, setActiveAckModal] = useState<{ id: string; text: string } | null>(null);
  const [activeClearModal, setActiveClearModal] = useState<{ id: string; text: string } | null>(null);

  const [openTraceId, setOpenTraceId] = useState<string | null>(null);
  const [traceData, setTraceData] = useState<Record<string, ExecutionTrace>>({});
  const [loadingTrace, setLoadingTrace] = useState<string | null>(null);

  const toggleTrace = async (id: string) => {
    if (openTraceId === id) {
      setOpenTraceId(null);
      return;
    }
    setOpenTraceId(id);
    if (!traceData[id] && onGetTrace) {
      setLoadingTrace(id);
      try {
        const t = await onGetTrace(id);
        setTraceData(prev => ({ ...prev, [id]: t }));
      } finally {
        setLoadingTrace(null);
      }
    }
  };

  const getAlarmState = (a: Alert): AlarmState => {
    if (a.alarm_state) return a.alarm_state;
    if (!a.cleared && !a.acknowledged) return 'active_unack';
    if (!a.cleared && a.acknowledged) return 'active_ack';
    if (a.cleared && !a.acknowledged) return 'cleared_unack';
    return 'cleared_ack';
  };

  const filtered = alerts.filter(a => {
    if (catFilter !== 'all' && a.category !== catFilter) return false;
    if (sevFilter !== 'all' && a.severity !== sevFilter) return false;
    const st = getAlarmState(a);
    if (stateFilter !== 'all' && st !== stateFilter) return false;
    return true;
  });

  const sorted = [...filtered].sort((a, b) =>
    new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  const activeUnackCount = alerts.filter(a => getAlarmState(a) === 'active_unack').length;
  const activeAckCount = alerts.filter(a => getAlarmState(a) === 'active_ack').length;
  const clearedUnackCount = alerts.filter(a => getAlarmState(a) === 'cleared_unack').length;

  return (
    <div className="ss-page">
      <div className="ss-page-header">
        <div>
          <h1 className="ss-page-title">Alerts & Alarm Management</h1>
          <div className="ss-page-subtitle">
            ThingsBoard 4-state lifecycle: Active/Cleared states with independent operator acknowledgement
          </div>
        </div>
        <div className="ss-page-meta">
          <span className="ss-status-pill warn">{activeUnackCount} Active Unacked</span>
          <span className="ss-status-pill demo">{clearedUnackCount} Cleared Unacked</span>
          <span className="ss-text-muted ss-text-xs">{alerts.length} total</span>
        </div>
      </div>

      {/* Domain Separation Notice */}
      <div className="ss-exp-banner ss-exp-banner-info">
        <ShieldAlert size={18} />
        <div>
          <strong>ALARM ARCHITECTURE POLICY:</strong> Environmental alerts are deterministic rule-based triggers
          derived from calibrated SCD41 NDIR sensor readings. Acoustic alerts represent speculative ML predictions from
          an unvalidated bioacoustic model and must be independently verified by inspection before quarantine.
        </div>
      </div>

      {/* Filters */}
      <div className="ss-filter-bar">
        <div className="ss-filter-section">
          <div className="ss-filter-label"><Filter size={13} /> Category:</div>
          <div className="ss-filter-group">
            {(['all', 'environmental', 'acoustic', 'combined', 'system'] as const).map(c => (
              <button
                key={c}
                id={`filter-cat-${c}`}
                className={`ss-filter-btn ${catFilter === c ? 'active' : ''}`}
                onClick={() => setCatFilter(c)}
              >
                {c === 'all' ? 'All Categories' : c.charAt(0).toUpperCase() + c.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="ss-filter-section">
          <div className="ss-filter-label">Severity:</div>
          <div className="ss-filter-group">
            {(['all', 'critical', 'warning', 'info'] as const).map(s => (
              <button
                key={s}
                id={`filter-sev-${s}`}
                className={`ss-filter-btn ss-sev-btn sev-${s} ${sevFilter === s ? 'active' : ''}`}
                onClick={() => setSevFilter(s)}
              >
                {s.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* ThingsBoard 4-State Lifecycle Filter */}
        <div className="ss-filter-section">
          <div className="ss-filter-label">Lifecycle State:</div>
          <div className="ss-filter-group">
            <button
              id="filter-state-all"
              className={`ss-filter-btn ${stateFilter === 'all' ? 'active' : ''}`}
              onClick={() => setStateFilter('all')}
            >
              All States ({alerts.length})
            </button>
            <button
              id="filter-state-active-unack"
              className={`ss-filter-btn ss-state-btn state-active-unack ${stateFilter === 'active_unack' ? 'active' : ''}`}
              onClick={() => setStateFilter('active_unack')}
            >
              Active Unacked ({activeUnackCount})
            </button>
            <button
              id="filter-state-active-ack"
              className={`ss-filter-btn ss-state-btn state-active-ack ${stateFilter === 'active_ack' ? 'active' : ''}`}
              onClick={() => setStateFilter('active_ack')}
            >
              Active Acked ({activeAckCount})
            </button>
            <button
              id="filter-state-cleared-unack"
              className={`ss-filter-btn ss-state-btn state-cleared-unack ${stateFilter === 'cleared_unack' ? 'active' : ''}`}
              onClick={() => setStateFilter('cleared_unack')}
            >
              Cleared Unacked ({clearedUnackCount})
            </button>
            <button
              id="filter-state-cleared-ack"
              className={`ss-filter-btn ss-state-btn state-cleared-ack ${stateFilter === 'cleared_ack' ? 'active' : ''}`}
              onClick={() => setStateFilter('cleared_ack')}
            >
              Cleared Acked
            </button>
          </div>
        </div>
      </div>

      {/* Alert list */}
      {sorted.length === 0 ? (
        <div className="ss-empty ss-empty-ok">
          <CheckCircle size={22} />
          <span>No alarms match the selected filter combination</span>
        </div>
      ) : (
        <div className="ss-alert-cards">
          {sorted.map(a => {
            const st = getAlarmState(a);
            const isAcoustic = a.category === 'acoustic' || a.category === 'combined';

            return (
              <div
                key={a.id}
                id={`alert-card-${a.id}`}
                className={`ss-alert-card sev-${a.severity} state-${st}`}
              >
                <div className="ss-alert-card-header">
                  <div className="ss-alert-card-title">
                    <SevIcon sev={a.severity} />
                    <span>{a.title}</span>
                  </div>
                  <div className="ss-alert-card-meta">
                    {/* ThingsBoard 4-State Badge */}
                    <span className={`ss-alarm-state-tag state-${st}`}>
                      {st === 'active_unack' && 'Active · Unacknowledged'}
                      {st === 'active_ack' && 'Active · Acknowledged'}
                      {st === 'cleared_unack' && 'Cleared · Unacknowledged'}
                      {st === 'cleared_ack' && 'Cleared · Acknowledged'}
                    </span>
                    <span className={`ss-cat-badge cat-${a.category}`}>
                      {isAcoustic && <FlaskConical size={11} className="ss-inline-icon" />}
                      {a.category}
                    </span>
                    <SourceBadge source={a.source} />
                  </div>
                </div>

                <div className="ss-alert-card-msg">{a.message}</div>

                {/* Rule Evidence Pill */}
                {a.triggered_by.length > 0 && (
                  <div className="ss-alert-evidence-box">
                    <span className="ss-evidence-label">Trigger Rule Evidence:</span>
                    <div className="ss-evidence-tags">
                      {a.triggered_by.map(rule => (
                        <span key={rule} className="ss-rule-tag">
                          {rule}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="ss-alert-card-footer">
                  <span className="ss-alert-ts">Triggered: {new Date(a.timestamp).toLocaleString()}</span>
                  <span className="ss-alert-zone">Originator: {a.zone_id} {a.device_id ? `(${a.device_id})` : ''}</span>
                </div>

                {/* Audit & Notes Log */}
                {(a.acknowledged || a.cleared) && (
                  <div className="ss-alert-log-section">
                    {a.acknowledged && (
                      <div className="ss-alert-log-row">
                        <CheckCircle size={13} className="ss-color-green" />
                        <span>
                          <strong>Acknowledged</strong> by {a.acknowledged_by ?? 'Operator'} at{' '}
                          {a.acknowledged_at ? new Date(a.acknowledged_at).toLocaleString() : '—'}
                        </span>
                        {a.inspection_notes && (
                          <div className="ss-log-note">
                            <MessageSquare size={12} />
                            <em>"{a.inspection_notes}"</em>
                          </div>
                        )}
                      </div>
                    )}
                    {a.cleared && (
                      <div className="ss-alert-log-row">
                        <XCircle size={13} className="ss-color-blue" />
                        <span>
                          <strong>Cleared</strong> by {a.cleared_by ?? 'System'} at{' '}
                          {a.cleared_at ? new Date(a.cleared_at).toLocaleString() : '—'}
                        </span>
                        {a.clear_notes && (
                          <div className="ss-log-note">
                            <MessageSquare size={12} />
                            <em>"{a.clear_notes}"</em>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Operator Actions Bar */}
                <div className="ss-alert-action-bar">
                  {/* Acknowledge Action */}
                  {!a.acknowledged ? (
                    activeAckModal?.id === a.id ? (
                      <div className="ss-action-input-wrap">
                        <input
                          type="text"
                          className="ss-input"
                          placeholder="Inspection finding notes..."
                          value={activeAckModal.text}
                          onChange={e => setActiveAckModal({ id: a.id, text: e.target.value })}
                        />
                        <button
                          id={`ack-confirm-${a.id}`}
                          className="ss-btn ss-btn-primary ss-btn-sm"
                          onClick={async () => {
                            await onAcknowledge(a.id, activeAckModal.text);
                            setActiveAckModal(null);
                          }}
                        >
                          <Check size={13} /> Confirm Ack
                        </button>
                        <button
                          className="ss-btn ss-btn-ghost ss-btn-sm"
                          onClick={() => setActiveAckModal(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        id={`ack-btn-${a.id}`}
                        className="ss-btn ss-btn-outline ss-btn-sm"
                        onClick={() => setActiveAckModal({ id: a.id, text: '' })}
                      >
                        <CheckCircle size={13} /> Acknowledge + Add Note
                      </button>
                    )
                  ) : null}

                  {/* Clear Action (ThingsBoard pattern) */}
                  {!a.cleared ? (
                    activeClearModal?.id === a.id ? (
                      <div className="ss-action-input-wrap">
                        <input
                          type="text"
                          className="ss-input"
                          placeholder="Resolution / corrective action notes..."
                          value={activeClearModal.text}
                          onChange={e => setActiveClearModal({ id: a.id, text: e.target.value })}
                        />
                        <button
                          id={`clear-confirm-${a.id}`}
                          className="ss-btn ss-btn-warn ss-btn-sm"
                          onClick={async () => {
                            await onClear(a.id, activeClearModal.text);
                            setActiveClearModal(null);
                          }}
                        >
                          <XCircle size={13} /> Confirm Clear
                        </button>
                        <button
                          className="ss-btn ss-btn-ghost ss-btn-sm"
                          onClick={() => setActiveClearModal(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        id={`clear-btn-${a.id}`}
                        className="ss-btn ss-btn-outline ss-btn-sm"
                        onClick={() => setActiveClearModal({ id: a.id, text: '' })}
                      >
                        <XCircle size={13} /> Clear Alarm
                      </button>
                    )
                  ) : null}

                  {/* Home Assistant-Style Automation Trace Button */}
                  <button
                    className="ss-btn ss-btn-ghost ss-btn-sm"
                    style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                    onClick={() => toggleTrace(a.id)}
                  >
                    <GitBranch size={13} />
                    {openTraceId === a.id ? 'Hide Trace' : 'Automation Trace'}
                    {openTraceId === a.id ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>
                </div>

                {/* Home Assistant-Style Automation Execution Trace Panel */}
                {openTraceId === a.id && (
                  <div className="ss-trace-panel">
                    <div className="ss-trace-header">
                      <div className="ss-trace-title">
                        <GitBranch size={14} style={{ color: 'var(--accent-light)' }} />
                        <strong>Home Assistant Automation Trace</strong>
                        <span className="ss-trigger-rule-badge">
                          rule: {a.triggered_by.join(' + ') || 'threshold_breach'}
                        </span>
                      </div>
                      <span className="ss-status-tag" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#818cf8', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
                        DETERMINISTIC EVALUATION
                      </span>
                    </div>

                    {loadingTrace === a.id ? (
                      <div style={{ padding: '16px', display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-muted)' }}>
                        <div className="ss-spinner" style={{ width: '18px', height: '18px' }} />
                        <span>Evaluating automation step graph…</span>
                      </div>
                    ) : (
                      <div className="ss-trace-steps">
                        {(traceData[a.id]?.steps || []).map((step, idx) => (
                          <div key={step.step_id} className={`ss-trace-step-card step-${step.step_type}`}>
                            <div className="ss-step-marker-col">
                              <span className="ss-step-circle">{idx + 1}</span>
                              <span className={`ss-step-type-tag tag-${step.step_type}`}>
                                {step.step_type.toUpperCase()}
                              </span>
                            </div>
                            <div className="ss-step-body">
                              <div className="ss-step-headline">
                                <strong>{step.name}</strong>
                                <span className="ss-step-ts">{new Date(step.timestamp).toLocaleTimeString()}</span>
                              </div>
                              <div className="ss-step-details-grid">
                                {Object.entries(step.details || {}).map(([k, val]) => (
                                  <div key={k} className="ss-step-detail-item">
                                    <span className="ss-detail-label">{k}:</span>
                                    <span className="ss-detail-val">
                                      {typeof val === 'boolean' ? (val ? 'TRUE' : 'FALSE') : String(val)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                            <div className="ss-step-outcome">
                              <CheckCircle size={13} style={{ color: 'var(--green)' }} />
                              <span>{step.status.toUpperCase()}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

