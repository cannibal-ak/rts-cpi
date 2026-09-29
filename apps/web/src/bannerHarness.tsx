/**
 * THROWAWAY visual harness for the WinAir banner recolor — not part of the app.
 * Served only via /banner-harness.html on a local dev port; renders every
 * banner state with stub data so the recolor can be eyeballed without a
 * backend or login. Delete along with banner-harness.html when done.
 */
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Box, Chip, Typography, ThemeProvider, createTheme, CssBaseline,
  List, ListItemButton, ListItemIcon, ListItemText, Avatar,
} from '@mui/material';
import { CalendarMonth, Dashboard as DashboardIcon, ShowChart } from '@mui/icons-material';
import WinairTabBar from './components/dashboard/winair/WinairTabBar';
import WinairTopFilterBar from './components/dashboard/winair/WinairTopFilterBar';
import FilterSelect from './components/dashboard/winair/FilterSelect';
import CapDateChip from './components/dashboard/CapDateChip';
import TimeRangeFilter from './components/dashboard/winair/PriceChartFilters';
import {
  DEP_TIME_MIN, DEP_TIME_MAX, DURATION_MIN, DURATION_MAX,
} from './components/dashboard/winair/priceChartTheme';
import { BANNER_BG, BANNER_HEADER_BG, FILTER_BG } from './components/dashboard/bannerTheme';
import { selectedRowSx, subItemSx } from './components/layout/sidebarSubItem';
import { buildAirlineColorMap } from './components/dashboard/winair/priceChartTheme';
import type {
  DashboardFilter, DashboardFilterSelections, DashboardDateFilter, DashboardTab,
} from './api/client';

const theme = createTheme({
  palette: { primary: { main: '#1a5276', light: '#2980b9', dark: '#0e2f44' } },
});
const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#1a5276', light: '#2980b9', dark: '#0e2f44' },
    background: { default: '#0f1419', paper: '#1a2332' },
  },
});

/** Panel rows through the REAL sidebar factories — accent vs no accent. */
function SidebarRows({ accent, label }: { accent?: string; label: string }) {
  return (
    <List dense disablePadding sx={{ width: 250, bgcolor: 'background.paper', borderRadius: 1.5, py: 1 }} data-rows={label}>
      <ListItemButton selected sx={{ mx: 1, borderRadius: 1, mb: 0.5, px: 1.5, minHeight: 40, ...selectedRowSx(accent) }}>
        <ListItemIcon sx={{ minWidth: 0, mr: 1.5, justifyContent: 'center' }}><DashboardIcon sx={{ fontSize: 20 }} /></ListItemIcon>
        <ListItemText primary="Selected row" primaryTypographyProps={{ fontSize: 13, fontWeight: 700 }} />
      </ListItemButton>
      <ListItemButton selected sx={subItemSx(accent)}>
        <ListItemIcon sx={{ minWidth: 0, mr: 1.5, justifyContent: 'center' }}><ShowChart sx={{ fontSize: 17 }} /></ListItemIcon>
        <ListItemText primary="Selected sub-item" primaryTypographyProps={{ fontSize: 12, fontWeight: 700 }} />
      </ListItemButton>
      <ListItemButton sx={subItemSx(accent)}>
        <ListItemIcon sx={{ minWidth: 0, mr: 1.5, justifyContent: 'center' }}><ShowChart sx={{ fontSize: 17 }} /></ListItemIcon>
        <ListItemText primary="Idle sub-item" primaryTypographyProps={{ fontSize: 12 }} />
      </ListItemButton>
    </List>
  );
}

/** Rail active tile + WA avatar, replicating the Sidebar/AppBar accent sx. */
function RailAndAvatar({ wm }: { wm: boolean }) {
  const accent = wm ? BANNER_BG : undefined;
  return (
    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', bgcolor: 'background.paper', p: 1.5, borderRadius: 1.5 }} data-rail={wm ? 'wm' : 'default'}>
      <ListItemButton
        selected
        sx={{
          width: 44, minHeight: 44, maxHeight: 44, flexGrow: 0, borderRadius: '10px', justifyContent: 'center', px: 0,
          '&.Mui-selected': {
            bgcolor: accent ?? 'primary.main',
            color: 'primary.contrastText',
            '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
            '&:hover': { bgcolor: accent ? BANNER_HEADER_BG : 'primary.dark' },
          },
        }}
      >
        <ListItemIcon sx={{ minWidth: 0, justifyContent: 'center' }}><DashboardIcon /></ListItemIcon>
      </ListItemButton>
      <Avatar sx={{ width: 36, height: 36, bgcolor: wm ? BANNER_BG : 'primary.light', color: wm ? '#ffffff' : 'primary.dark', fontSize: 14, fontWeight: 500 }}>
        WA
      </Avatar>
    </Box>
  );
}

const TABS: DashboardTab[] = [
  { id: 'TAB-avg', label: 'Avg_Fare' },
  { id: 'TAB-minmax', label: 'Min/Max_Fare' },
  { id: 'TAB-comp', label: 'Competitor Breakdown' },
  { id: 'TAB-rec', label: 'Pricing Recommendations' },
  { id: 'TAB-vel', label: 'Velocity' },
];

const FILTERS: DashboardFilter[] = [
  { id: 'NF-1', field: 'route', label: 'Route (O&D)', description: null, dataset_id: 1, multi_select: true, values: ['ANU-BGI', 'ANU-DOM', 'ANU-SXM', 'ANU-POS'], charts_in_scope: null },
  { id: 'NF-2', field: 'flight_number', label: 'Flight Number', description: null, dataset_id: 1, multi_select: true, values: ['WM 100', 'WM 202', 'WM 340'], charts_in_scope: null },
  { id: 'NF-3', field: 'days_left', label: 'Days Left', description: null, dataset_id: 1, multi_select: true, values: ['0-3', '4-7', '8-14', '15+'], charts_in_scope: null },
  { id: 'NF-4', field: 'stops', label: 'Stops', description: null, dataset_id: 1, multi_select: true, values: ['0', '1', '2'], charts_in_scope: null },
];

const DATES = ['2026-07-29', '2026-07-28', '2026-07-27'];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography sx={{ fontSize: 13, fontWeight: 700, mb: 1, color: 'text.secondary' }}>{title}</Typography>
      {children}
    </Box>
  );
}

function Harness() {
  const [tab, setTab] = useState('TAB-minmax');
  const [pendingDirty, setPendingDirty] = useState<DashboardFilterSelections>({ 'NF-1': ['ANU-BGI', 'ANU-DOM', 'ANU-SXM'], 'NF-3': ['4-7'] });
  const [pendingClean, setPendingClean] = useState<DashboardFilterSelections>({});
  const [capDate, setCapDate] = useState<DashboardDateFilter>({ mode: 'single', capDateEq: '2026-07-29' });
  const [depRange, setDepRange] = useState<[number, number]>([DEP_TIME_MIN, DEP_TIME_MAX]);
  const [durRange, setDurRange] = useState<[number, number]>([60, 510]);

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Section title="1. Header chips (light page background) — Latest data (outlined, WM red) + Cap date (filled, accent)">
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <Typography variant="h5" fontWeight={600}>WinAir Dashboard</Typography>
          <Chip
            icon={<CalendarMonth sx={{ fontSize: 16 }} />}
            label="Latest data: 29 Jul 2026"
            size="small"
            variant="outlined"
            color="primary"
            sx={{
              ml: 2, fontWeight: 500,
              color: BANNER_BG, borderColor: BANNER_BG,
              '& .MuiChip-icon': { color: BANNER_BG },
            }}
          />
          <CapDateChip availableDates={DATES} value={capDate} onChange={setCapDate} accent={BANNER_BG} />
        </Box>
      </Section>

      <Section title="1b. Same chips on a dark page background (dark-mode sanity)">
        <Box sx={{ display: 'flex', alignItems: 'center', bgcolor: '#121212', p: 2, borderRadius: 1.5 }}>
          <Typography variant="h5" fontWeight={600} sx={{ color: '#fff' }}>WinAir Dashboard</Typography>
          <Chip
            icon={<CalendarMonth sx={{ fontSize: 16 }} />}
            label="Latest data: 29 Jul 2026"
            size="small"
            variant="outlined"
            color="primary"
            sx={{
              ml: 2, fontWeight: 500,
              color: BANNER_BG, borderColor: BANNER_BG,
              '& .MuiChip-icon': { color: BANNER_BG },
            }}
          />
          <CapDateChip availableDates={DATES} value={capDate} onChange={setCapDate} accent={BANNER_BG} />
        </Box>
      </Section>

      <Section title="2. Tab bar — selected vs idle pills">
        <WinairTabBar tabs={TABS} value={tab} onChange={setTab} loading={false} switching={false} error={null} />
      </Section>

      <Section title="2b. Tab bar — switching spinner + warning alert">
        <WinairTabBar tabs={TABS} value="TAB-comp" onChange={() => {}} loading={false} switching error="Couldn't load dashboard sections — showing the default view." />
      </Section>

      <Section title="2c. Tab bar — loading skeletons">
        <WinairTabBar tabs={[]} value="prices" onChange={() => {}} loading switching={false} error={null} />
      </Section>

      <Section title="3. Filter bar — selections held (3 active), DIRTY (Apply enabled). Hover Apply to check tint.">
        <WinairTopFilterBar
          filters={FILTERS} filtersLoading={false} filtersError={null}
          pending={pendingDirty} onPendingChange={setPendingDirty}
          dirty applying={false} onApply={() => {}} onReset={() => setPendingDirty({})}
          // The Latest Prices tab's two range controls, so the sliders are
          // eyeballed on the same surface the dropdowns sit on. Duration is
          // narrowed to show the active border and readout ink.
          extraControls={
            <>
              <TimeRangeFilter
                label="Departure Time" value={depRange}
                min={DEP_TIME_MIN} max={DEP_TIME_MAX} onChange={setDepRange}
              />
              <TimeRangeFilter
                label="Duration" value={durRange}
                min={DURATION_MIN} max={DURATION_MAX} onChange={setDurRange}
              />
            </>
          }
        />
      </Section>

      <Section title="3b. Filter bar — idle, nothing selected, Apply/Clear DISABLED">
        <WinairTopFilterBar
          filters={FILTERS} filtersLoading={false} filtersError={null}
          pending={pendingClean} onPendingChange={setPendingClean}
          dirty={false} applying={false} onApply={() => {}} onReset={() => setPendingClean({})}
        />
      </Section>

      <Section title="3c. Filter bar — error text (deep red on teal grey)">
        <WinairTopFilterBar
          filters={[]} filtersLoading={false} filtersError="request failed with status 502"
          pending={{}} onPendingChange={() => {}}
          dirty={false} applying={false} onApply={() => {}} onReset={() => {}}
        />
      </Section>

      <Section title="3d. Filter bar — loading skeletons">
        <WinairTopFilterBar
          filters={[]} filtersLoading filtersError={null}
          pending={{}} onPendingChange={() => {}}
          dirty={false} applying={false} onApply={() => {}} onReset={() => {}}
        />
      </Section>

      <Section title="4. Sidebar rows via REAL factories + rail tile/avatar — WM red vs default navy, light mode">
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
          <SidebarRows accent={BANNER_BG} label="wm-light" />
          <SidebarRows label="default-light" />
          <RailAndAvatar wm />
          <RailAndAvatar wm={false} />
        </Box>
      </Section>

      <Section title="4b. Same in DARK mode (accent ink must lighten)">
        <ThemeProvider theme={darkTheme}>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', bgcolor: '#0f1419', p: 2, borderRadius: 1.5 }}>
            <SidebarRows accent={BANNER_BG} label="wm-dark" />
            <SidebarRows label="default-dark" />
            <RailAndAvatar wm />
          </Box>
        </ThemeProvider>
      </Section>

      <Section title="6. Airline series palette — real buildAirlineColorMap output (XX = fallback path)">
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {Object.entries(buildAirlineColorMap(['WM', '5L', '7Z', 'BW', 'DM', 'Exp', 'JY', 'S6', 'XX'])).map(([code, c]) => (
            <Box
              key={code}
              data-airline={code}
              data-expected={c}
              sx={{ px: 1.5, py: 1, borderRadius: 1, bgcolor: c, color: '#fff', fontSize: 12, fontWeight: 700 }}
            >
              {code}
            </Box>
          ))}
        </Box>
      </Section>

      <Section title="5. Standalone FilterSelect (onBanner) — open dropdown to check teal checkbox">
        <Box sx={{ bgcolor: FILTER_BG, p: 2, borderRadius: 1.5, maxWidth: 260 }}>
          <FilterSelect
            id="cb-test" label="Route (O&D)" options={['ANU-BGI', 'ANU-DOM', 'ANU-SXM']}
            value={['ANU-BGI']} multiple onBanner onChange={() => {}}
          />
        </Box>
      </Section>
    </Box>
  );
}

createRoot(document.getElementById('root')!).render(
  <ThemeProvider theme={theme}>
    <CssBaseline />
    <Harness />
  </ThemeProvider>,
);
