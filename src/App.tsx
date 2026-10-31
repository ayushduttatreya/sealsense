import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ScenarioSelector } from './components/ScenarioSelector';
import { Overview } from './pages/Overview';
import { StorageZones } from './pages/StorageZones';
import { AcousticMonitoring } from './pages/AcousticMonitoring';
import { AlertsEvents } from './pages/AlertsEvents';
import { DevicesSensors } from './pages/DevicesSensors';
import { useSealSenseData } from './hooks/useApi';
import type { DemoScenario } from './types';

function App() {
  const [scenario, setScenario] = useState<DemoScenario>('healthy_storage');
  const {
    mode,
    readings,
    events,
    alerts,
    devices,
    zones,
    loading,
    reload,
    acknowledgeAlert,
    clearAlert,
    validateAcousticEvent,
    batchReviewEvents,
    getAlertTrace,
    setScenario: applyScenario,
  } = useSealSenseData(scenario);

  const handleScenario = async (s: DemoScenario) => {
    setScenario(s);
    await applyScenario(s);
  };

  return (
    <BrowserRouter>
      <Layout mode={mode}>
        {mode === 'demo' && (
          <ScenarioSelector current={scenario} onChange={handleScenario} />
        )}
        {loading ? (
          <div className="ss-loading">
            <div className="ss-spinner" />
            <span>Loading sensor data…</span>
          </div>
        ) : (
          <Routes>
            <Route path="/" element={<Overview readings={readings} alerts={alerts} zones={zones} onReload={reload} />} />
            <Route path="/zones" element={<StorageZones zones={zones} devices={devices} readings={readings} alerts={alerts} />} />
            <Route path="/acoustic" element={<AcousticMonitoring events={events} onValidate={validateAcousticEvent} onBatchReview={batchReviewEvents} />} />
            <Route path="/alerts" element={<AlertsEvents alerts={alerts} onAcknowledge={acknowledgeAlert} onClear={clearAlert} onGetTrace={getAlertTrace} />} />
            <Route path="/devices" element={<DevicesSensors devices={devices} zones={zones} />} />
          </Routes>
        )}
      </Layout>
    </BrowserRouter>
  );
}


export default App;
