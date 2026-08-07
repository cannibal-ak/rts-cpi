import React, { useState } from 'react';
import {
  Box,
  Typography,
  Select,
  MenuItem,
  Button,
  Chip,
  Tooltip,
  Tabs,
  Tab,
} from '@mui/material';
import {
  FlightTakeoff,
  FilterList,
} from '@mui/icons-material';
import DateFilterToggle from '../DateFilterToggle';
import type { DashboardDateFilter } from '../../../api/client';

export interface WinairFilterState {
  route: string;
  airline: string;
  flightNum: string;
  dtdBucket: string;
  pricePosition: string;
  priceAction: string;
  cheapestComp: string;
  currency: string;
  activeSubTab: string;
  airlines: { [code: string]: boolean };
}

export interface WinairTopFilterBarProps {
  availableDates: string[];
  dateFilter: DashboardDateFilter;
  onDateFilterChange: (val: DashboardDateFilter) => void;
  datesLoading?: boolean;
  onOpenFilterDrawer?: () => void;
  filterState?: WinairFilterState;
  onFilterStateChange?: (state: Partial<WinairFilterState>) => void;
}

const DEFAULT_ROUTES = [
  { code: 'EIS-SXM', label: 'Tortola (EIS) > St Maarten (SXM)' },
  { code: 'ANU-BGI', label: 'Antigua (ANU) > Barbados (BGI)' },
  { code: 'ANU-SXM', label: 'Antigua (ANU) > St Maarten (SXM)' },
  { code: 'AUA-CUR', label: 'Aruba (AUA) > Curacao (CUR)' },
  { code: 'BGI-SXM', label: 'Barbados (BGI) > St Maarten (SXM)' },
  { code: 'BON-CUR', label: 'Bonaire (BON) > Curacao (CUR)' },
  { code: 'CUR-SXM', label: 'Curacao (CUR) > St Maarten (SXM)' },
  { code: 'DOM-ANU', label: 'Dominica (DOM) > Antigua (ANU)' },
];

const FLIGHT_NUMBERS = [
  'All Flights',
  'WM-2041',
  'WM-2042',
  'WM-2050',
  'WM-2051',
  'WM-2052',
  'WM-2315',
  'WM-2316',
  'WM-2317',
];

const DTD_BUCKETS = [
  { code: 'all', label: 'All DtD' },
  { code: '0-7', label: '0-7 Days' },
  { code: '8-14', label: '8-14 Days' },
  { code: '15-30', label: '15-30 Days' },
  { code: '31-60', label: '31-60 Days' },
  { code: '60+', label: '60+ Days' },
];

const PRICE_POSITIONS = [
  { code: 'all', label: 'All Positions' },
  { code: 'lowest', label: 'Lowest Fare' },
  { code: 'higher', label: 'Higher Fare' },
  { code: 'parity', label: 'Parity' },
];

const PRICING_ACTIONS = [
  { code: 'all', label: 'All Actions' },
  { code: 'hold', label: 'Hold' },
  { code: 'increase', label: 'Increase' },
  { code: 'decrease', label: 'Decrease' },
];

const AIRLINE_BADGES = [
  { code: '5L', name: '5L', color: '#2B6B2B' },
  { code: 'JY', name: 'JY', color: '#E4049C' },
  { code: 'WM', name: 'WM', color: '#0070C0' },
];

export default function WinairTopFilterBar({
  availableDates,
  dateFilter,
  onDateFilterChange,
  datesLoading = false,
  onOpenFilterDrawer,
  filterState,
  onFilterStateChange,
}: WinairTopFilterBarProps) {
  const [selectedRoute, setSelectedRoute] = useState(filterState?.route || 'EIS-SXM');
  const [selectedAirline, setSelectedAirline] = useState(filterState?.airline || 'all');
  const [flightNum, setFlightNum] = useState(filterState?.flightNum || 'All Flights');
  const [dtdBucket, setDtdBucket] = useState(filterState?.dtdBucket || 'all');
  const [pricePosition, setPricePosition] = useState(filterState?.pricePosition || 'all');
  const [priceAction, setPriceAction] = useState(filterState?.priceAction || 'all');
  const [currency, setCurrency] = useState(filterState?.currency || 'USD');
  const [activeTab, setActiveTab] = useState(filterState?.activeSubTab || 'latest');
  const [activeAirlines, setActiveAirlines] = useState<{ [code: string]: boolean }>(
    filterState?.airlines || { '5L': true, JY: true, WM: true }
  );

  const handleRouteChange = (val: string) => {
    setSelectedRoute(val);
    onFilterStateChange?.({ route: val });
  };

  const handleAirlineChange = (val: string) => {
    setSelectedAirline(val);
    onFilterStateChange?.({ airline: val });
  };

  const handleFlightNumChange = (val: string) => {
    setFlightNum(val);
    onFilterStateChange?.({ flightNum: val });
  };

  const handleDtdBucketChange = (val: string) => {
    setDtdBucket(val);
    onFilterStateChange?.({ dtdBucket: val });
  };

  const handlePricePositionChange = (val: string) => {
    setPricePosition(val);
    onFilterStateChange?.({ pricePosition: val });
  };

  const handlePriceActionChange = (val: string) => {
    setPriceAction(val);
    onFilterStateChange?.({ priceAction: val });
  };

  const toggleAirline = (code: string) => {
    const updated = { ...activeAirlines, [code]: !activeAirlines[code] };
    setActiveAirlines(updated);
    onFilterStateChange?.({ airlines: updated });
  };

  return (
    <Box sx={{ width: '100%', mb: 1, borderRadius: 1.5, overflow: 'hidden', boxShadow: 1 }}>
      {/* ── TOP HEADER CONTROL BAR (TEAL BANNER WITH EXACT SUPERSET FILTERS) ──────────────── */}
      <Box
        sx={{
          bgcolor: '#005973',
          color: '#ffffff',
          px: 2,
          py: 1,
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1.25,
        }}
      >
        {/* 1. Route Selector (O&D) */}
        <Box sx={{ display: 'flex', alignItems: 'center', bgcolor: 'rgba(255, 255, 255, 0.15)', borderRadius: 1, px: 1.5, py: 0.5 }}>
          <FlightTakeoff sx={{ fontSize: 18, mr: 1, color: '#64D2FF' }} />
          <Select
            value={selectedRoute}
            onChange={(e) => handleRouteChange(e.target.value)}
            variant="standard"
            disableUnderline
            sx={{
              color: '#ffffff',
              fontWeight: 700,
              fontSize: 13,
              '& .MuiSelect-icon': { color: '#ffffff' },
            }}
          >
            {DEFAULT_ROUTES.map((r) => (
              <MenuItem key={r.code} value={r.code} sx={{ fontSize: 13, py: 0.75 }}>
                {r.label}
              </MenuItem>
            ))}
          </Select>
        </Box>

        {/* 2. Airline Filter */}
        <Select
          value={selectedAirline}
          onChange={(e) => handleAirlineChange(e.target.value)}
          variant="standard"
          disableUnderline
          sx={{
            color: '#ffffff',
            fontSize: 12,
            bgcolor: 'rgba(255, 255, 255, 0.1)',
            borderRadius: 1,
            px: 1.25,
            py: 0.5,
            '& .MuiSelect-icon': { color: '#ffffff' },
          }}
        >
          <MenuItem value="all">All Airlines</MenuItem>
          <MenuItem value="WM">WM (WinAir)</MenuItem>
          <MenuItem value="5L">5L (Air France)</MenuItem>
          <MenuItem value="JY">JY (interCaribbean)</MenuItem>
        </Select>

        {/* 3. Flight Number Filter */}
        <Select
          value={flightNum}
          onChange={(e) => handleFlightNumChange(e.target.value)}
          variant="standard"
          disableUnderline
          sx={{
            color: '#ffffff',
            fontSize: 12,
            bgcolor: 'rgba(255, 255, 255, 0.1)',
            borderRadius: 1,
            px: 1.25,
            py: 0.5,
            '& .MuiSelect-icon': { color: '#ffffff' },
          }}
        >
          {FLIGHT_NUMBERS.map((f) => (
            <MenuItem key={f} value={f} sx={{ fontSize: 12 }}>
              {f}
            </MenuItem>
          ))}
        </Select>

        {/* 4. Days to Departure (DtD) Filter */}
        <Select
          value={dtdBucket}
          onChange={(e) => handleDtdBucketChange(e.target.value)}
          variant="standard"
          disableUnderline
          sx={{
            color: '#ffffff',
            fontSize: 12,
            bgcolor: 'rgba(255, 255, 255, 0.1)',
            borderRadius: 1,
            px: 1.25,
            py: 0.5,
            '& .MuiSelect-icon': { color: '#ffffff' },
          }}
        >
          {DTD_BUCKETS.map((d) => (
            <MenuItem key={d.code} value={d.code} sx={{ fontSize: 12 }}>
              {d.label}
            </MenuItem>
          ))}
        </Select>

        {/* 5. Price Position Filter */}
        <Select
          value={pricePosition}
          onChange={(e) => handlePricePositionChange(e.target.value)}
          variant="standard"
          disableUnderline
          sx={{
            color: '#ffffff',
            fontSize: 12,
            bgcolor: 'rgba(255, 255, 255, 0.1)',
            borderRadius: 1,
            px: 1.25,
            py: 0.5,
            '& .MuiSelect-icon': { color: '#ffffff' },
          }}
        >
          {PRICE_POSITIONS.map((p) => (
            <MenuItem key={p.code} value={p.code} sx={{ fontSize: 12 }}>
              {p.label}
            </MenuItem>
          ))}
        </Select>

        {/* 6. Pricing Action Filter */}
        <Select
          value={priceAction}
          onChange={(e) => handlePriceActionChange(e.target.value)}
          variant="standard"
          disableUnderline
          sx={{
            color: '#ffffff',
            fontSize: 12,
            bgcolor: 'rgba(255, 255, 255, 0.1)',
            borderRadius: 1,
            px: 1.25,
            py: 0.5,
            '& .MuiSelect-icon': { color: '#ffffff' },
          }}
        >
          {PRICING_ACTIONS.map((a) => (
            <MenuItem key={a.code} value={a.code} sx={{ fontSize: 12 }}>
              {a.label}
            </MenuItem>
          ))}
        </Select>

        {/* 7. Currency Selector */}
        <Select
          value={currency}
          onChange={(e) => setCurrency(e.target.value)}
          variant="standard"
          disableUnderline
          sx={{
            color: '#ffffff',
            fontSize: 12,
            bgcolor: 'rgba(255, 255, 255, 0.1)',
            borderRadius: 1,
            px: 1.25,
            py: 0.5,
            '& .MuiSelect-icon': { color: '#ffffff' },
          }}
        >
          <MenuItem value="USD">USD</MenuItem>
          <MenuItem value="EUR">EUR</MenuItem>
        </Select>

        {/* 8. Integrated Date Filter Toggle (Cap Date / Single Day / Range) */}
        <Box sx={{ bgcolor: 'rgba(255, 255, 255, 0.15)', borderRadius: 1, p: 0.25 }}>
          <DateFilterToggle
            availableDates={availableDates}
            value={dateFilter}
            onChange={onDateFilterChange}
            disabled={datesLoading || availableDates.length === 0}
          />
        </Box>

        <Box sx={{ flexGrow: 1 }} />

        {/* 9. Action Buttons */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Tooltip title="All Filters Drawer">
            <Button
              variant="outlined"
              size="small"
              onClick={onOpenFilterDrawer}
              startIcon={<FilterList fontSize="small" />}
              sx={{
                color: '#ffffff',
                borderColor: 'rgba(255, 255, 255, 0.4)',
                fontSize: 12,
                textTransform: 'none',
                bgcolor: 'rgba(255, 255, 255, 0.08)',
                '&:hover': {
                  borderColor: '#ffffff',
                  bgcolor: 'rgba(255, 255, 255, 0.2)',
                },
              }}
            >
              Filters
            </Button>
          </Tooltip>
        </Box>
      </Box>

      {/* ── SUB-HEADER NAVIGATION TABS & AIRLINE BADGES ───────────────────────── */}
      <Box
        sx={{
          bgcolor: '#ffffff',
          borderBottom: '1px solid',
          borderColor: 'divider',
          px: 2,
          py: 0.5,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        {/* Navigation Tabs */}
        <Tabs
          value={activeTab}
          onChange={(_, v) => {
            setActiveTab(v);
            onFilterStateChange?.({ activeSubTab: v });
          }}
          indicatorColor="primary"
          textColor="primary"
          sx={{
            minHeight: 36,
            '& .MuiTab-root': {
              minHeight: 36,
              py: 0.5,
              px: 1.5,
              fontSize: 13,
              fontWeight: 600,
              textTransform: 'none',
            },
          }}
        >
          <Tab label="Latest Prices" value="latest" />
          <Tab label="Price Evolution" value="evolution" />
          <Tab label="Average Prices" value="average" />
          <Tab label="Price Distribution" value="distribution" />
          <Tab label="Indicator" value="indicator" />
        </Tabs>

        {/* Airline Badges / Series Toggles */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {AIRLINE_BADGES.map((al) => {
            const active = activeAirlines[al.code] !== false;
            return (
              <Chip
                key={al.code}
                label={`✈ ${al.name}`}
                clickable
                onClick={() => toggleAirline(al.code)}
                size="small"
                sx={{
                  bgcolor: active ? `${al.color}15` : '#f1f5f9',
                  color: active ? al.color : '#94a3b8',
                  border: '1px solid',
                  borderColor: active ? al.color : '#cbd5e1',
                  fontWeight: 700,
                  fontSize: 12,
                  height: 26,
                  '&:hover': {
                    bgcolor: active ? `${al.color}25` : '#e2e8f0',
                  },
                }}
              />
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}
