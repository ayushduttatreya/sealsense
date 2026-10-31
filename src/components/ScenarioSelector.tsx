import { SCENARIOS } from '../lib/demo';
import type { DemoScenario } from '../types';

interface Props {
  current: DemoScenario;
  onChange: (s: DemoScenario) => void;
}

export function ScenarioSelector({ current, onChange }: Props) {
  return (
    <div className="ss-scenario-panel">
      <div className="ss-scenario-header">
        <span className="ss-scenario-label">🎬 Demo Scenario Selector</span>
        <span className="ss-scenario-sub">Deterministic — all data is labelled SIMULATED or MODEL EXPERIMENT</span>
      </div>
      <div className="ss-scenario-grid">
        {SCENARIOS.map(s => (
          <button
            key={s.id}
            id={`scenario-${s.id}`}
            className={`ss-scenario-btn ${current === s.id ? 'active' : ''}`}
            onClick={() => onChange(s.id)}
            title={s.description}
          >
            <span className="ss-scenario-icon">{s.icon}</span>
            <span className="ss-scenario-name">{s.label}</span>
            <span className="ss-scenario-desc">{s.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
