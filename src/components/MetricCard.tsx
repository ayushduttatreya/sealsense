import React from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  unit?: string;
  icon?: React.ReactNode;
  trend?: 'up' | 'down' | 'stable';
  status?: 'ok' | 'warn' | 'crit' | 'unknown';
  sublabel?: string;
}

const trendArrow = { up: '↑', down: '↓', stable: '→' };
const trendCls = { up: 'trend-up', down: 'trend-down', stable: 'trend-stable' };

export function MetricCard({ label, value, unit, icon, trend, status = 'ok', sublabel }: MetricCardProps) {
  return (
    <div className={`ss-metric-card status-${status}`}>
      <div className="ss-metric-header">
        {icon && <span className="ss-metric-icon">{icon}</span>}
        <span className="ss-metric-label">{label}</span>
      </div>
      <div className="ss-metric-value">
        {value}
        {unit && <span className="ss-metric-unit">{unit}</span>}
        {trend && <span className={`ss-metric-trend ${trendCls[trend]}`}>{trendArrow[trend]}</span>}
      </div>
      {sublabel && <div className="ss-metric-sub">{sublabel}</div>}
    </div>
  );
}
