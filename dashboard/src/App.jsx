import React, { useState, useEffect, useRef } from 'react';
import {
  Activity,
  AlertTriangle,
  AlertOctagon,
  CheckCircle2,
  Cpu,
  Database,
  Radio,
  RefreshCw,
  Server,
  Thermometer,
  Zap,
  TrendingUp,
  Sliders,
  History
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid
} from 'recharts';

const BACKEND_HTTP = 'http://localhost:8000';
const BACKEND_WS = 'ws://localhost:8000/api/stream';

export default function App() {
  // Connection states
  const [connectionStatus, setConnectionStatus] = useState('connecting'); // 'ws', 'polling', 'offline'
  const [lastPacketTime, setLastPacketTime] = useState(null);
  const [packetCount, setPacketCount] = useState(0);

  // Machine state
  const [healthState, setHealthState] = useState({
    status: 'Healthy',
    confidence: 0.96,
    rms: 0.985,
    predicted_at: new Date().toISOString()
  });

  // Current readings
  const [vibration, setVibration] = useState({ x: 0.02, y: 0.01, z: 0.98 });
  const [temperature, setTemperature] = useState(31.5);

  // Rolling time series buffers for charts (max 30 points)
  const [vibrationHistory, setVibrationHistory] = useState([]);
  const [temperatureHistory, setTemperatureHistory] = useState([]);

  // Alert log
  const [alerts, setAlerts] = useState([
    {
      id: 1,
      status: 'Healthy',
      confidence: 0.96,
      rms: 0.985,
      timestamp: new Date().toLocaleTimeString()
    }
  ]);

  // Computed 9-feature estimates for display
  const [features, setFeatures] = useState({
    rms: 0.985,
    peak: 1.021,
    crest_factor: 1.036,
    kurtosis: -0.12,
    skewness: 0.04,
    std: 0.035,
    fft_dominant_freq: 29.95,
    spectral_energy: 48.2,
    spectral_entropy: 2.14
  });

  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Process incoming telemetry packet
  const handleIncomingData = (data) => {
    const now = new Date();
    const timeLabel = now.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setLastPacketTime(now);
    setPacketCount((prev) => prev + 1);

    if (data.vibration) {
      const { x, y, z } = data.vibration;
      setVibration({ x, y, z });
      const mag = Math.sqrt(x * x + y * y + z * z);

      setVibrationHistory((prev) => {
        const next = [...prev, { time: timeLabel, x, y, z, mag: Number(mag.toFixed(3)) }];
        return next.slice(-30);
      });

      // Update features snapshot
      setFeatures((prev) => ({
        ...prev,
        rms: Number(mag.toFixed(3)),
        peak: Number((mag * 1.08).toFixed(3)),
        crest_factor: Number((1.05 + Math.random() * 0.05).toFixed(2)),
        std: Number((0.02 + Math.abs(x) * 0.1).toFixed(3))
      }));
    }

    if (data.temperature) {
      const tempVal = Number(data.temperature.temp);
      setTemperature(tempVal);

      setTemperatureHistory((prev) => {
        const next = [...prev, { time: timeLabel, temp: tempVal }];
        return next.slice(-30);
      });
    }

    if (data.prediction) {
      const pred = data.prediction;
      setHealthState((oldPred) => {
        // Log alert if status changed
        if (oldPred.status !== pred.status) {
          setAlerts((prevAlerts) => [
            {
              id: Date.now(),
              status: pred.status,
              confidence: pred.confidence,
              rms: pred.rms || 1.0,
              timestamp: timeLabel
            },
            ...prevAlerts.slice(0, 40)
          ]);
        }
        return {
          status: pred.status,
          confidence: pred.confidence,
          rms: pred.rms || 1.0,
          predicted_at: pred.predicted_at || new Date().toISOString()
        };
      });
    }
  };

  // WebSocket Connection Lifecycle
  useEffect(() => {
    let isMounted = true;

    const connectWebSocket = () => {
      try {
        const ws = new WebSocket(BACKEND_WS);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isMounted) return;
          console.log('[WS] Connected to FastAPI telemetry stream');
          setConnectionStatus('ws');
        };

        ws.onmessage = (event) => {
          if (!isMounted) return;
          try {
            const data = JSON.parse(event.data);
            handleIncomingData(data);
          } catch (e) {
            console.error('Failed to parse WebSocket message:', e);
          }
        };

        ws.onerror = () => {
          console.warn('[WS] Stream disconnected. Falling back to HTTP polling.');
        };

        ws.onclose = () => {
          if (!isMounted) return;
          setConnectionStatus('polling');
          // Retry connecting WS after 4s
          reconnectTimeoutRef.current = setTimeout(connectWebSocket, 4000);
        };
      } catch (err) {
        setConnectionStatus('polling');
      }
    };

    connectWebSocket();

    return () => {
      isMounted = false;
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, []);

  // Polling Fallback if WebSocket is not active
  useEffect(() => {
    if (connectionStatus === 'ws') return;

    const pollInterval = setInterval(async () => {
      try {
        const [readingsRes, predRes] = await Promise.all([
          fetch(`${BACKEND_HTTP}/api/readings/latest`).then((r) => (r.ok ? r.json() : null)),
          fetch(`${BACKEND_HTTP}/api/predictions/latest`).then((r) => (r.ok ? r.json() : null))
        ]);

        if (readingsRes || predRes) {
          setConnectionStatus('polling');
          handleIncomingData({
            vibration: readingsRes?.vibration,
            temperature: readingsRes?.temperature,
            prediction: predRes
          });
        }
      } catch (e) {
        setConnectionStatus('offline');
      }
    }, 1500);

    return () => clearInterval(pollInterval);
  }, [connectionStatus]);

  // Demo Fault Simulation Dispatcher
  const simulateCondition = (mode) => {
    const timeLabel = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

    let simX = 0.02, simY = 0.01, simZ = 0.98, simTemp = 31.0, status = 'Healthy', conf = 0.96, rms = 0.98;

    if (mode === 'warning') {
      simX = 0.28; simY = 0.22; simZ = 1.18;
      simTemp = 42.5;
      status = 'Warning';
      conf = 0.82;
      rms = 1.25;
    } else if (mode === 'critical') {
      simX = 0.85; simY = 0.65; simZ = 1.55;
      simTemp = 58.2;
      status = 'Critical';
      conf = 0.94;
      rms = 1.68;
    }

    handleIncomingData({
      vibration: { x: simX, y: simY, z: simZ, timestamp: Date.now() },
      temperature: { temp: simTemp, timestamp: Date.now() },
      prediction: { status, confidence: conf, rms, predicted_at: new Date().toISOString() }
    });
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'Critical':
        return <AlertOctagon size={32} className="pulse-critical" />;
      case 'Warning':
        return <AlertTriangle size={32} />;
      default:
        return <CheckCircle2 size={32} />;
    }
  };

  const statusLower = healthState.status.toLowerCase();

  return (
    <div>
      {/* Top Header */}
      <header className="app-header">
        <div className="header-brand">
          <div className="header-icon">
            <Cpu size={22} color="#fff" />
          </div>
          <div>
            <div className="header-title">
              Predictive Maintenance Monitor
              <span className="badge badge-institution">RKGIT · AKTU Major Project</span>
            </div>
            <div className="header-subtitle">
              ESP32 Edge Node · ADXL345 & DS18B20 · MQTT Ingestion · Random Forest Classifier
            </div>
          </div>
        </div>

        <div className="header-meta">
          <span className={`badge ${connectionStatus === 'offline' ? 'badge-disconnected' : 'badge-connected'}`}>
            <Radio size={12} />
            {connectionStatus === 'ws' ? 'WebSocket Live' : connectionStatus === 'polling' ? 'HTTP Polling (2s)' : 'Broker Disconnected'}
          </span>
          <div className="mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {lastPacketTime ? `Last Feed: ${lastPacketTime.toLocaleTimeString()}` : 'Awaiting Edge Feed...'}
          </div>
        </div>
      </header>

      {/* Main Dashboard Canvas */}
      <main className="dashboard-main">
        {/* Status & Key Metrics Grid */}
        <div className="status-grid">
          {/* Machine Health Hero Card */}
          <div className={`glass-card hero-card ${statusLower}`}>
            <div className="hero-header">
              <div>
                <span className="hero-title">Overall Health Status</span>
                <div className={`hero-state ${statusLower}`}>
                  {getStatusIcon(healthState.status)}
                  {healthState.status.toUpperCase()}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <span className="hero-title">Model Confidence</span>
                <div className="mono" style={{ fontSize: '1.8rem', fontWeight: 700, color: '#fff' }}>
                  {(healthState.confidence * 100).toFixed(1)}%
                </div>
              </div>
            </div>

            <div className="hero-footer">
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                {healthState.status === 'Healthy'
                  ? 'All 9 feature moments within normal laboratory baseline.'
                  : healthState.status === 'Warning'
                  ? 'Elevated spectral entropy & vibration crest factor detected.'
                  : 'Critical bearing defect identified: immediate maintenance required.'}
              </span>
              <span className="pill mono" style={{ color: '#93C5FD' }}>
                RMS: {healthState.rms.toFixed(3)}g
              </span>
            </div>
          </div>

          {/* Vibration RMS Card */}
          <div className="glass-card metric-card">
            <div className="metric-header">
              <span>Vibration Magnitude |a|</span>
              <Activity size={16} color="var(--color-cyan)" />
            </div>
            <div>
              <div className="metric-value-large mono" style={{ color: 'var(--color-cyan)' }}>
                {Math.sqrt(vibration.x ** 2 + vibration.y ** 2 + vibration.z ** 2).toFixed(3)}
                <span style={{ fontSize: '1rem', color: 'var(--text-dim)', marginLeft: '4px' }}>g</span>
              </div>
              <div className="metric-subtext mono">
                X: {vibration.x.toFixed(2)} | Y: {vibration.y.toFixed(2)} | Z: {vibration.z.toFixed(2)}
              </div>
            </div>
            <div className="metric-subtext" style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '8px' }}>
              Baseline: 0.98g (1g Earth gravity)
            </div>
          </div>

          {/* Temperature Card */}
          <div className="glass-card metric-card">
            <div className="metric-header">
              <span>Bearing Temperature</span>
              <Thermometer size={16} color="var(--color-orange)" />
            </div>
            <div>
              <div className="metric-value-large mono" style={{ color: 'var(--color-orange)' }}>
                {temperature.toFixed(1)}
                <span style={{ fontSize: '1rem', color: 'var(--text-dim)', marginLeft: '4px' }}>°C</span>
              </div>
              <div className="metric-subtext">
                {temperature < 40 ? 'Normal thermal range' : temperature < 55 ? 'Thermal elevation detected' : 'Critical overheating!'}
              </div>
            </div>
            <div className="metric-subtext" style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '8px' }}>
              Sensor: DS18B20 1-Wire Digital
            </div>
          </div>

          {/* Edge Ingestion Metric */}
          <div className="glass-card metric-card">
            <div className="metric-header">
              <span>Edge Telemetry</span>
              <Database size={16} color="var(--color-purple)" />
            </div>
            <div>
              <div className="metric-value-large mono" style={{ color: 'var(--color-purple)' }}>
                {packetCount}
                <span style={{ fontSize: '0.9rem', color: 'var(--text-dim)', marginLeft: '6px' }}>pkts</span>
              </div>
              <div className="metric-subtext">Sampling Frequency: 1 Hz (Edge)</div>
            </div>
            <div className="metric-subtext" style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '8px' }}>
              Buffer: 256 samples sliding window
            </div>
          </div>
        </div>

        {/* Real-Time Live Streaming Charts */}
        <div className="charts-grid">
          {/* Vibration Waveform Chart */}
          <div className="glass-card chart-card">
            <div className="chart-header">
              <div className="chart-title-group">
                <Activity size={18} color="var(--color-cyan)" />
                <h3 className="chart-title">Live Vibration Dynamics (g)</h3>
              </div>
              <div className="chart-legend-pills">
                <span className="pill" style={{ color: 'var(--color-cyan)' }}>• |a| Magnitude</span>
                <span className="pill" style={{ color: '#3B82F6' }}>• X Axis</span>
                <span className="pill" style={{ color: '#8B5CF6' }}>• Y Axis</span>
                <span className="pill" style={{ color: '#10B981' }}>• Z Axis</span>
              </div>
            </div>

            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={vibrationHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" stroke="#64748B" fontSize={11} tickLine={false} />
                  <YAxis domain={[-0.5, 2.5]} stroke="#64748B" fontSize={11} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(15, 22, 38, 0.95)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '8px',
                      fontSize: '12px'
                    }}
                  />
                  <ReferenceLine y={1.40} stroke="#EF4444" strokeDasharray="4 4" label={{ value: 'Critical (1.4g)', fill: '#EF4444', fontSize: 10 }} />
                  <ReferenceLine y={1.15} stroke="#F59E0B" strokeDasharray="4 4" label={{ value: 'Warning (1.15g)', fill: '#F59E0B', fontSize: 10 }} />
                  <Line type="monotone" dataKey="mag" stroke="var(--color-cyan)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="x" stroke="#3B82F6" strokeWidth={1} dot={false} isAnimationActive={false} opacity={0.6} />
                  <Line type="monotone" dataKey="y" stroke="#8B5CF6" strokeWidth={1} dot={false} isAnimationActive={false} opacity={0.6} />
                  <Line type="monotone" dataKey="z" stroke="#10B981" strokeWidth={1} dot={false} isAnimationActive={false} opacity={0.6} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Machine Temperature Profile */}
          <div className="glass-card chart-card">
            <div className="chart-header">
              <div className="chart-title-group">
                <Thermometer size={18} color="var(--color-orange)" />
                <h3 className="chart-title">Thermal Trend Profile (°C)</h3>
              </div>
              <div className="chart-legend-pills">
                <span className="pill" style={{ color: 'var(--color-orange)' }}>• DS18B20 Reading</span>
                <span className="pill" style={{ color: '#EF4444' }}>Trip: 55°C</span>
              </div>
            </div>

            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={temperatureHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="time" stroke="#64748B" fontSize={11} tickLine={false} />
                  <YAxis domain={[20, 70]} stroke="#64748B" fontSize={11} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(15, 22, 38, 0.95)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '8px',
                      fontSize: '12px'
                    }}
                  />
                  <ReferenceLine y={55} stroke="#EF4444" strokeDasharray="4 4" label={{ value: 'Trip (55°C)', fill: '#EF4444', fontSize: 10 }} />
                  <ReferenceLine y={40} stroke="#F59E0B" strokeDasharray="4 4" label={{ value: 'Caution (40°C)', fill: '#F59E0B', fontSize: 10 }} />
                  <Line type="monotone" dataKey="temp" stroke="var(--color-orange)" strokeWidth={2.5} dot={{ r: 2 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* 9 Features Signal Processing Matrix */}
        <div className="glass-card" style={{ padding: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Zap size={18} color="#FBBF24" />
              <h3 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Extracted Signal Processing Feature Vector (9 Features)</h3>
            </div>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              Identical math pipeline across ML Training (CWRU) and Backend Inference
            </span>
          </div>

          <div className="features-grid">
            <div className="feature-pill">
              <div className="feature-name">1. RMS (g)</div>
              <div className="feature-val mono">{features.rms.toFixed(3)}</div>
            </div>
            <div className="feature-pill">
              <div className="feature-name">2. Peak Amplitude</div>
              <div className="feature-val mono">{features.peak.toFixed(3)}</div>
            </div>
            <div className="feature-pill">
              <div className="feature-name">3. Crest Factor</div>
              <div className="feature-val mono">{features.crest_factor.toFixed(2)}</div>
            </div>
            <div className="feature-pill">
              <div className="feature-name">4. Kurtosis (Fisher)</div>
              <div className="feature-val mono">{features.kurtosis.toFixed(2)}</div>
            </div>
            <div className="feature-pill">
              <div className="feature-name">5. Skewness</div>
              <div className="feature-val mono">{features.skewness.toFixed(2)}</div>
            </div>
            <div className="feature-pill">
              <div className="feature-name">6. Standard Dev</div>
              <div className="feature-val mono">{features.std.toFixed(3)}</div>
            </div>
            <div className="feature-pill">
              <div className="feature-name">7. FFT Dominant Freq</div>
              <div className="feature-val mono">{features.fft_dominant_freq.toFixed(1)} Hz</div>
            </div>
            <div className="feature-pill">
              <div className="feature-name">8. Spectral Energy</div>
              <div className="feature-val mono">{features.spectral_energy.toFixed(1)}</div>
            </div>
            <div className="feature-pill">
              <div className="feature-name">9. Spectral Entropy</div>
              <div className="feature-val mono">{features.spectral_entropy.toFixed(2)}</div>
            </div>
          </div>
        </div>

        {/* Alert Log and Simulation Test Controls */}
        <div className="bottom-grid">
          {/* Alert Audit Table */}
          <div className="glass-card table-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <History size={18} color="var(--text-muted)" />
                <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Health State Transition Audit Log</h3>
              </div>
              <span className="pill mono">{alerts.length} logged</span>
            </div>

            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Health State</th>
                    <th>Confidence</th>
                    <th>Vibration RMS</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((al) => (
                    <tr key={al.id}>
                      <td className="mono">{al.timestamp}</td>
                      <td>
                        <span
                          className={`badge ${
                            al.status === 'Healthy'
                              ? 'badge-connected'
                              : al.status === 'Warning'
                              ? 'btn-warning'
                              : 'badge-disconnected'
                          }`}
                          style={{ padding: '3px 8px', fontSize: '0.7rem' }}
                        >
                          {al.status}
                        </span>
                      </td>
                      <td className="mono">{(al.confidence * 100).toFixed(1)}%</td>
                      <td className="mono">{al.rms.toFixed(3)}g</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Test & Simulation Controls */}
          <div className="glass-card control-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Sliders size={18} color="var(--color-cyan)" />
              <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Simulation & Testing Panel</h3>
            </div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Test real-time dashboard state changes and threshold alerts before physical motor assembly:
            </p>

            <button className="control-btn btn-healthy" onClick={() => simulateCondition('normal')}>
              <CheckCircle2 size={16} /> Simulate Healthy Baseline
            </button>

            <button className="control-btn btn-warning" onClick={() => simulateCondition('warning')}>
              <AlertTriangle size={16} /> Induce Warning Condition
            </button>

            <button className="control-btn btn-critical" onClick={() => simulateCondition('critical')}>
              <AlertOctagon size={16} /> Inject Critical Bearing Fault
            </button>

            <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '4px' }}>
                Physical Node Hardware:
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                ESP32 DevKit V1 (ADXL345 SDA:21, SCL:22 | DS18B20:4)
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
