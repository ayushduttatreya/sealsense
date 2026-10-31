import type { DataSource } from '../types';

interface Props { source: DataSource; className?: string }

const labels: Record<DataSource, { text: string; cls: string }> = {
  REAL: { text: 'REAL', cls: 'badge-real' },
  SIMULATED: { text: 'SIMULATED', cls: 'badge-sim' },
  MODEL_EXPERIMENT: { text: 'MODEL EXPERIMENT', cls: 'badge-exp' },
};

export function SourceBadge({ source, className = '' }: Props) {
  const { text, cls } = labels[source];
  return <span className={`ss-source-badge ${cls} ${className}`}>{text}</span>;
}
