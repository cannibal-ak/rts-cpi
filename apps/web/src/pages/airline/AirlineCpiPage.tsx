import { useState, useEffect } from 'react';
import { Box, Tabs, Tab } from '@mui/material';
import PageHeader from '../../components/common/PageHeader';
import DataFreshnessIndicator from '../../components/common/DataFreshnessIndicator';
import AirlineCpiPricingTab from './AirlineCpiPricingTab';
import AirlineCpiVelocityTab from './AirlineCpiVelocityTab';
import { api } from '../../api';
import type { DataFreshness } from '../../types';

interface AirlineCpiPageProps {
  /** Tenant code determines which snapshot view to query (JY or PW). */
  tenantCode: 'JY' | 'PW';
}

const TENANT_LABELS: Record<string, string> = {
  JY: 'Airline CPI – JY',
  PW: 'Airline CPI – PW',
};

export default function AirlineCpiPage({ tenantCode }: AirlineCpiPageProps) {
  // Filter state lifted to parent so each tab keeps its own filters
  // when the user switches tabs (T6 in spec).
  const [pricingFilters, setPricingFilters] = useState<Record<string, string>>({});
  const [velocityFilters, setVelocityFilters] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<0 | 1>(0); // 0 = Pricing, 1 = Velocity (JY only)

  const [freshness, setFreshness] = useState<DataFreshness | null>(null);

  const pageTitle = TENANT_LABELS[tenantCode] || `Airline CPI – ${tenantCode}`;
  const showTabs = tenantCode === 'JY' || tenantCode === 'PW';

  // Reset filters and tab when the tenant changes
  useEffect(() => {
    setPricingFilters({});
    setVelocityFilters({});
    setTab(0);
  }, [tenantCode]);

  useEffect(() => {
    api.stats.getFreshnessMetrics().then(data => {
      const air = data.find(d => d.domain === 'Airline CPI' || d.domain === `Airline CPI – ${tenantCode}`);
      if (air) setFreshness(air);
    });
  }, [tenantCode]);

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <PageHeader
        title={pageTitle}
        subtitle={`Competitive pricing intelligence for ${tenantCode} airline routes`}
        breadcrumbs={[{ label: 'Home', href: '/' }, { label: pageTitle }]}
        actions={freshness && <DataFreshnessIndicator data={freshness} compact />}
      />

      {showTabs ? (
        <>
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v as 0 | 1)}
            sx={{ borderBottom: 1, borderColor: 'divider', px: 2 }}
            aria-label="JY data tabs"
          >
            <Tab label="Pricing" />
            <Tab label="Velocity" />
          </Tabs>
          {tab === 0 && (
            <AirlineCpiPricingTab
              tenantCode={tenantCode}
              filters={pricingFilters}
              onFiltersChange={setPricingFilters}
            />
          )}
          {tab === 1 && (
            <AirlineCpiVelocityTab
              tenantCode={tenantCode}
              filters={velocityFilters}
              onFiltersChange={setVelocityFilters}
            />
          )}
        </>
      ) : (
        <AirlineCpiPricingTab
          tenantCode={tenantCode}
          filters={pricingFilters}
          onFiltersChange={setPricingFilters}
        />
      )}
    </Box>
  );
}
