import { useState, useEffect, useRef, type MutableRefObject } from 'react';
import { Box, Tabs, Tab, Breadcrumbs, Link, Typography, Tooltip, Button } from '@mui/material';
import { NavigateNext, FileDownload } from '@mui/icons-material';
import AirlineCpiPricingTab from './AirlineCpiPricingTab';
import AirlineCpiVelocityTab from './AirlineCpiVelocityTab';
import { api } from '../../api';
import type { DataFreshness } from '../../types';

interface AirlineCpiPageProps {
  /** Tenant code determines which snapshot view to query (JY, PW, ALT or WM). */
  tenantCode: 'JY' | 'PW' | 'ALT' | 'WM';
}

const TENANT_LABELS: Record<string, string> = {
  JY: 'Airline CPI – JY',
  PW: 'Airline CPI – PW',
  ALT: 'Airline CPI – SKY',
  WM: 'Airline CPI – WinAir',
};

export default function AirlineCpiPage({ tenantCode }: AirlineCpiPageProps) {
  // Filter state lifted to parent so each tab keeps its own filters
  // when the user switches tabs.
  const [pricingFilters, setPricingFilters] = useState<Record<string, string>>({});
  const [velocityFilters, setVelocityFilters] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<0 | 1>(0); // 0 = Pricing, 1 = Velocity

  const [freshness, setFreshness] = useState<DataFreshness | null>(null);

  // Each tab populates its own ref every render so the toolbar Export
  // button can invoke the active tab's handler (closing over its current
  // filtered rows). Initialised to no-op so the ref is always callable.
  const pricingExportRef = useRef<() => void>(() => {});
  const velocityExportRef = useRef<() => void>(() => {});

  const pageTitle = TENANT_LABELS[tenantCode] || `Airline CPI – ${tenantCode}`;
  const TENANTS_WITH_VELOCITY: AirlineCpiPageProps['tenantCode'][] = ['JY', 'PW', 'ALT', 'WM'];
  const showTabs = TENANTS_WITH_VELOCITY.includes(tenantCode);

  useEffect(() => {
    setPricingFilters({});
    setVelocityFilters({});
    setTab(0);
  }, [tenantCode]);

  useEffect(() => {
    api.stats.getFreshnessMetrics().then(data => {
      const air = data.find(d => d.domain === 'Airline CPI' || d.domain === pageTitle);
      if (air) setFreshness(air);
    });
  }, [tenantCode]);

  const isVelocityActive = showTabs && tab === 1;
  const exportTooltip = isVelocityActive
    ? 'Download filtered velocity rows as CSV (13 dictionary-named columns)'
    : 'Download filtered rows as CSV (76 dictionary-named columns)';
  const handleToolbarExport = () => {
    if (isVelocityActive) velocityExportRef.current();
    else pricingExportRef.current();
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ── Row 1 — Header bar (breadcrumb + freshness dot) ─────────── */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 1,
        height: 32,
        minHeight: 32,
        px: 2,
        flexShrink: 0,
      }}>
        <Breadcrumbs separator={<NavigateNext sx={{ fontSize: 14 }} />}>
          <Link underline="hover" color="inherit" href="/" sx={{ fontSize: 12 }}>Home</Link>
          <Typography color="text.primary" sx={{ fontSize: 12, fontWeight: 500 }}>{pageTitle}</Typography>
        </Breadcrumbs>
        {freshness && <FreshnessBadge data={freshness} />}
      </Box>

      {/* ── Row 2 — Tabs + Export (single thin toolbar) ─────────────── */}
      <Box sx={{
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        gap: 1,
        borderBottom: 1,
        borderColor: 'divider',
        minHeight: 32,
        height: 32,
        px: 2,
        flexShrink: 0,
      }}>
        {showTabs ? (
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v as 0 | 1)}
            aria-label={`${tenantCode} data tabs`}
            sx={{
              minHeight: 32,
              '& .MuiTabs-flexContainer': { gap: 0 },
              '& .MuiTab-root': {
                minHeight: 32,
                py: 0.25,
                px: 1.5,
                fontSize: 12,
                fontWeight: 500,
                textTransform: 'none',
              },
              '& .MuiTabs-indicator': { height: 2 },
            }}
          >
            <Tab label="Pricing" />
            <Tab label="Velocity" />
          </Tabs>
        ) : (
          <Box />
        )}
        <Tooltip title={exportTooltip}>
          <Button
            size="small"
            startIcon={<FileDownload sx={{ fontSize: 14 }} />}
            onClick={handleToolbarExport}
            sx={{
              fontSize: 11.5,
              textTransform: 'none',
              minHeight: 26,
              py: 0.25,
              px: 1,
              mb: 0.25,
            }}
          >
            Export
          </Button>
        </Tooltip>
      </Box>

      {/* ── Tab content ────────────────────────────────────────────── */}
      {(!showTabs || tab === 0) && (
        <AirlineCpiPricingTab
          tenantCode={tenantCode}
          filters={pricingFilters}
          onFiltersChange={setPricingFilters}
          exportRef={pricingExportRef}
        />
      )}
      {showTabs && tab === 1 && (
        <AirlineCpiVelocityTab
          tenantCode={tenantCode}
          filters={velocityFilters}
          onFiltersChange={setVelocityFilters}
          exportRef={velocityExportRef}
        />
      )}
    </Box>
  );
}

// ── Compact freshness badge ─────────────────────────────────────────────
// Renders a colored dot + the file's capture date as "DD Mon YYYY".
// Dot colour by age (theme-aware so dark mode works):
//   < 24h → success · 1–3 days → warning · > 3 days → error
// Tooltip shows full timestamp on hover.

interface FreshnessBadgeProps { data: DataFreshness }

function FreshnessBadge({ data }: FreshnessBadgeProps) {
  const capIso = data.last_capture_at || data.report_date || null;
  if (!capIso) {
    return <DotLabel color="text.disabled" label="No data" tooltip="No file uploaded yet" />;
  }
  const capDate = new Date(capIso);
  if (isNaN(capDate.getTime())) {
    return <DotLabel color="text.disabled" label="No data" tooltip="Invalid capture timestamp" />;
  }
  const ageHours = (Date.now() - capDate.getTime()) / 3600_000;
  let dotColor: string = 'success.main';
  if (ageHours > 24 * 3) dotColor = 'error.main';
  else if (ageHours > 24) dotColor = 'warning.main';

  const dateLabel = capDate.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  const timeLabel = capDate.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return <DotLabel color={dotColor} label={dateLabel} tooltip={`Last file uploaded: ${dateLabel} at ${timeLabel}`} />;
}

function DotLabel({ color, label, tooltip }: { color: string; label: string; tooltip: string }) {
  return (
    <Tooltip title={tooltip}>
      <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
        <Box component="span" sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: color, flexShrink: 0 }} />
        <Typography component="span" sx={{ fontSize: 11.5, color: 'text.primary', fontVariantNumeric: 'tabular-nums' }}>
          {label}
        </Typography>
      </Box>
    </Tooltip>
  );
}

// Re-export the ref type so the Pricing tab's prop signature matches.
export type PricingExportRef = MutableRefObject<() => void>;
