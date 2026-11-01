import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, Warehouse, Mic, Bell, Cpu, ChevronRight,
  Radio, Wifi, WifiOff, FlaskConical
} from 'lucide-react';
import type { AppMode } from '../hooks/useApi';

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const NAV: NavItem[] = [
  { to: '/', label: 'Overview', icon: <LayoutDashboard size={18} /> },
  { to: '/zones', label: 'Storage Zones', icon: <Warehouse size={18} /> },
  { to: '/acoustic', label: 'Acoustic Monitoring', icon: <Mic size={18} /> },
  { to: '/alerts', label: 'Alerts & Events', icon: <Bell size={18} /> },
  { to: '/devices', label: 'Devices & Sensors', icon: <Cpu size={18} /> },
];

interface LayoutProps {
  children: React.ReactNode;
  mode: AppMode;
}

export function Layout({ children, mode }: LayoutProps) {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="ss-app">
      {/* Sidebar */}
      <aside className={`ss-sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="ss-sidebar-header">
          <div className="ss-logo">
            <div className="ss-logo-icon">
              <Radio size={20} />
            </div>
            <div>
              <div className="ss-logo-name">SealSense</div>
              <div className="ss-logo-sub">Grain Storage Monitor</div>
            </div>
          </div>
        </div>

        <nav className="ss-nav">
          {NAV.map(item => {
            const active = location.pathname === item.to;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`ss-nav-item ${active ? 'active' : ''}`}
                onClick={() => setSidebarOpen(false)}
              >
                {item.icon}
                <span>{item.label}</span>
                {active && <ChevronRight size={14} className="ss-nav-arrow" />}
              </Link>
            );
          })}
        </nav>

        <div className="ss-sidebar-footer">
          <Link
            to="/farmer"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              background: 'linear-gradient(135deg, #1b4d3e, #2d7a62)',
              color: '#ffffff',
              padding: '10px 14px',
              borderRadius: 10,
              textDecoration: 'none',
              fontWeight: 600,
              fontSize: 13,
              marginBottom: 12,
              boxShadow: '0 2px 6px rgba(27, 77, 62, 0.3)',
            }}
          >
            <span style={{ fontSize: 16 }}>🌾</span>
            <span>Farmer View / किसान दृश्य</span>
          </Link>
          <div className={`ss-mode-badge ${mode === 'backend' ? 'live' : 'demo'}`}>
            {mode === 'backend' ? <Wifi size={12} /> : <WifiOff size={12} />}
            {mode === 'backend' ? 'Live Backend' : 'Demo Mode'}
          </div>
          {mode === 'demo' && (
            <div className="ss-demo-note">
              <FlaskConical size={11} />
              Backend offline — showing demo data
            </div>
          )}
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && <div className="ss-overlay" onClick={() => setSidebarOpen(false)} />}

      {/* Main */}
      <div className="ss-main">
        <header className="ss-topbar">
          <button
            className="ss-menu-btn"
            onClick={() => setSidebarOpen(v => !v)}
            aria-label="Toggle sidebar"
          >
            <span /><span /><span />
          </button>
          <div className="ss-topbar-right">
            <Link
              to="/farmer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: '#1b4d3e',
                color: '#ffffff',
                padding: '6px 12px',
                borderRadius: 999,
                textDecoration: 'none',
                fontWeight: 600,
                fontSize: 12,
                marginRight: 8,
                transition: 'opacity 0.15s ease',
              }}
            >
              <span>🌾</span>
              <span>Farmer View</span>
            </Link>
            <div className={`ss-status-pill ${mode === 'backend' ? 'live' : 'demo'}`}>
              <span className="ss-status-dot" />
              {mode === 'backend' ? 'System Online' : 'Demo Simulation'}
            </div>
          </div>
        </header>
        <main className="ss-content">{children}</main>
      </div>
    </div>
  );
}
