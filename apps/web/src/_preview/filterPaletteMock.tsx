/**
 * THROWAWAY mock for the WinAir filter-bar recolour (red → light teal grey).
 * Not part of the app; served only via /filter-palette-mock.html on a local
 * dev port. Delete along with filter-palette-mock.html once the palette is
 * chosen and bannerTheme.ts carries the real tokens.
 *
 * It replicates WinairTopFilterBar / FilterSelect / TimeRangeFilter markup and
 * sx values one-for-one, with every colour lifted into a palette object, so a
 * candidate can be judged in the real component metrics without touching a
 * production file. The palette shape here IS the proposed bannerTheme split.
 */
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Autocomplete, Box, Button, Checkbox, Chip, CssBaseline, Skeleton, Slider,
  Tab, Tabs, TextField, ThemeProvider, Tooltip, Typography, createTheme,
} from '@mui/material';
import {
  CalendarMonth, Check, CheckBox as CheckBoxIcon, CheckBoxOutlineBlank,
  FilterAltOff, KeyboardArrowDown, ScatterPlot, Tune,
} from '@mui/icons-material';

// ── Today's WinAir chrome, for reference ────────────────────────────────
const BRAND_RED = '#CD1F25';
const BRAND_RED_DARK = '#A5181D';

/**
 * Every colour the filter panel uses. Today all of these are white-alpha over
 * red; the light variants below re-point them at dark ink over a teal grey.
 */
interface BarPalette {
  key: string;
  name: string;
  note: string;
  bg: string;
  /** Hairline round the card — a light panel needs one on a near-white page. */
  border: string;
  ink: string;
  labelInk: string;
  mutedInk: string;
  fieldBg: string;
  fieldBgActive: string;
  fieldLine: string;
  fieldLineActive: string;
  fieldHoverLine: string;
  placeholder: string;
  chipBg: string;
  chipInk: string;
  chipDelete: string;
  /** MUI's "+N" overflow marker, restyled as a count pill. */
  pillBg: string;
  pillInk: string;
  /** The "N active" chip in the actions row. */
  countBg: string;
  countInk: string;
  applyBg: string;
  applyInk: string;
  applyHoverBg: string;
  applyDisabledBg: string;
  applyDisabledInk: string;
  clearInk: string;
  clearHoverBg: string;
  clearDisabledInk: string;
  skeleton: string;
  skeletonText: string;
  errorInk: string;
  sliderInk: string;
  sliderRail: string;
  sliderHalo: string;
}

/** What is on screen today — the control in this comparison. */
const CURRENT: BarPalette = {
  key: 'current',
  name: 'Current — WinAir red',
  note: 'What ships today. #CD1F25 panel, white-alpha ink throughout.',
  bg: BRAND_RED,
  border: 'transparent',
  ink: '#ffffff',
  labelInk: 'rgba(255,255,255,0.82)',
  mutedInk: 'rgba(255,255,255,0.9)',
  fieldBg: 'rgba(255,255,255,0.06)',
  fieldBgActive: 'rgba(255,255,255,0.16)',
  fieldLine: 'rgba(255,255,255,0.22)',
  fieldLineActive: 'rgba(255,255,255,0.55)',
  fieldHoverLine: '#ffffff',
  placeholder: 'rgba(255,255,255,0.55)',
  chipBg: 'rgba(255,255,255,0.22)',
  chipInk: '#ffffff',
  chipDelete: 'rgba(255,255,255,0.7)',
  pillBg: '#ffffff',
  pillInk: BRAND_RED_DARK,
  countBg: 'rgba(255,255,255,0.88)',
  countInk: BRAND_RED_DARK,
  applyBg: '#ffffff',
  applyInk: BRAND_RED_DARK,
  applyHoverBg: '#fbeaea',
  applyDisabledBg: 'rgba(255,255,255,0.25)',
  applyDisabledInk: 'rgba(255,255,255,0.6)',
  clearInk: '#ffffff',
  clearHoverBg: 'rgba(255,255,255,0.10)',
  clearDisabledInk: 'rgba(255,255,255,0.4)',
  skeleton: 'rgba(255,255,255,0.18)',
  skeletonText: 'rgba(255,255,255,0.14)',
  errorInk: '#FFECB3',
  sliderInk: '#ffffff',
  sliderRail: 'rgba(255,255,255,0.9)',
  sliderHalo: 'rgba(255,255,255,0.16)',
};

/**
 * The light variants share one ink + accent system and differ only in how
 * deep the surface sits. Ink is a teal-leaning slate rather than neutral
 * grey, so the panel reads as one deliberate colour instead of grey text
 * dropped on a tinted box.
 */
const INK = '#1E3438';        // ≥ 10:1 on all three surfaces
const LABEL_INK = '#40585C';  // ≥ 5.5:1 — labels are 11px, so they need it
const MUTED_INK = '#5C7478';  // ≥ 4.5:1 — icons and placeholder
const ACCENT = '#2F6E73';     // teal: active borders, chips, sliders, pills

function lightVariant(
  key: string, name: string, note: string, bg: string, border: string,
): BarPalette {
  return {
    key, name, note, bg, border,
    ink: INK,
    labelInk: LABEL_INK,
    mutedInk: MUTED_INK,
    // White fields on a tinted panel: the strongest available separation
    // between "the surface" and "the thing you can type into".
    fieldBg: 'rgba(255,255,255,0.72)',
    fieldBgActive: '#ffffff',
    fieldLine: 'rgba(30,52,56,0.22)',
    fieldLineActive: ACCENT,
    fieldHoverLine: ACCENT,
    placeholder: 'rgba(30,52,56,0.45)',
    chipBg: 'rgba(47,110,115,0.14)',
    chipInk: INK,
    chipDelete: 'rgba(30,52,56,0.45)',
    pillBg: ACCENT,
    pillInk: '#ffffff',
    countBg: ACCENT,
    countInk: '#ffffff',
    // Apply keeps the brand red: it is the one committing action on the page,
    // and red on this surface is both the strongest call and the last bit of
    // WinAir identity left in the panel.
    applyBg: BRAND_RED,
    applyInk: '#ffffff',
    applyHoverBg: BRAND_RED_DARK,
    applyDisabledBg: 'rgba(30,52,56,0.10)',
    applyDisabledInk: 'rgba(30,52,56,0.38)',
    clearInk: LABEL_INK,
    clearHoverBg: 'rgba(30,52,56,0.07)',
    clearDisabledInk: 'rgba(30,52,56,0.32)',
    skeleton: 'rgba(30,52,56,0.11)',
    skeletonText: 'rgba(30,52,56,0.08)',
    errorInk: '#9A2A22',
    sliderInk: ACCENT,
    sliderRail: 'rgba(30,52,56,0.28)',
    sliderHalo: 'rgba(47,110,115,0.16)',
  };
}

const OPTION_A = lightVariant(
  'a', 'Option A — Mist', '#E9F0F0 · the lightest of the three; nearly a white panel with a teal cast.',
  '#E9F0F0', 'rgba(30,52,56,0.12)',
);
const OPTION_B = lightVariant(
  'b', 'Option B — Sea glass', '#D9E5E6 · clearly teal grey, still light. Reads as a distinct panel on a white page.',
  '#D9E5E6', 'rgba(30,52,56,0.13)',
);
const OPTION_C = lightVariant(
  'c', 'Option C — Harbour', '#C6D6D8 · deepest; the filter zone carries real weight against the page.',
  '#C6D6D8', 'rgba(30,52,56,0.14)',
);

const LIGHT_OPTIONS = [OPTION_A, OPTION_B, OPTION_C];
const ALL_OPTIONS = [CURRENT, ...LIGHT_OPTIONS];

// ── Stub data, matching dashboard 6's real filters ──────────────────────
interface MockFilter {
  id: string;
  label: string;
  values: string[];
  description?: string;
}

const FILTERS: MockFilter[] = [
  { id: 'NF-1', label: 'Route (O&D)', values: ['ANU-BGI', 'ANU-DOM', 'ANU-SXM', 'ANU-POS', 'BGI-ANU'] },
  { id: 'NF-2', label: 'Flight Number', values: ['WM 100', 'WM 202', 'WM 340', 'WM 412'] },
  { id: 'NF-3', label: 'Days Left', values: ['0-3', '4-7', '8-14', '15+'] },
  { id: 'NF-4', label: 'Stops', values: ['0', '1', '2'] },
];

const TABS = ['Avg_Fare', 'Min/Max_Fare', 'Competitor Breakdown', 'Pricing Recommendations', 'Velocity'];

const DEP_MIN = 0, DEP_MAX = 1439, DUR_MIN = 0, DUR_MAX = 1440;
const pad = (n: number) => String(n).padStart(2, '0');
const formatDuration = (m: number) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;

type Selections = Record<string, string[]>;

// ── Replica controls ────────────────────────────────────────────────────

/** FilterSelect, with every onDark branch re-pointed at the palette. */
function MockFilterSelect({
  p, id, label, options, value, onChange,
}: {
  p: BarPalette; id: string; label: string; options: string[];
  value: string[]; onChange: (next: string[]) => void;
}) {
  const active = value.length > 0;
  const fieldId = `mock-${p.key}-${id}`;

  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography
        component="label"
        htmlFor={fieldId}
        noWrap
        sx={{
          display: 'block', fontSize: 11, fontWeight: 500, letterSpacing: '0.05em',
          textTransform: 'uppercase',
          color: active ? p.ink : p.labelInk,
          mb: '5px',
        }}
      >
        {label}
      </Typography>

      <Autocomplete
        id={fieldId}
        multiple
        size="small"
        fullWidth
        disableCloseOnSelect
        limitTags={1}
        getLimitTagsText={more => `+${more}`}
        popupIcon={<KeyboardArrowDown fontSize="small" />}
        options={options}
        value={value}
        onChange={(_, next) => onChange(next as string[])}
        renderOption={(props, option, { selected }) => {
          const { key, ...rest } = props as { key?: string } & Record<string, unknown>;
          return (
            <li key={key ?? option} {...rest} style={{ fontSize: 13 }}>
              <Checkbox
                icon={<CheckBoxOutlineBlank fontSize="small" />}
                checkedIcon={<CheckBoxIcon fontSize="small" />}
                checked={selected}
                size="small"
                sx={{ mr: 0.75, p: 0.25, '&.Mui-checked': { color: p.fieldLineActive } }}
              />
              {option}
            </li>
          );
        }}
        renderTags={(selected, getTagProps) =>
          selected.map((option, index) => {
            const { key, ...rest } = getTagProps({ index });
            return (
              <Chip
                key={key}
                label={option}
                size="small"
                {...rest}
                sx={{
                  height: 20, maxWidth: 120, fontSize: 11, m: 0,
                  bgcolor: p.chipBg,
                  color: p.chipInk,
                  '& .MuiChip-label': { px: 0.75 },
                  '& .MuiChip-deleteIcon': { color: p.chipDelete },
                }}
              />
            );
          })
        }
        renderInput={params => (
          <TextField {...params} placeholder={value.length === 0 ? 'All' : undefined} variant="outlined" />
        )}
        sx={{
          '& .MuiInputBase-root': {
            minHeight: 34, py: '2px !important', pl: '8px', pr: '52px !important',
            gap: '3px', fontSize: 12, color: p.ink, borderRadius: '8px',
            flexWrap: 'nowrap', overflow: 'hidden',
            bgcolor: active ? p.fieldBgActive : p.fieldBg,
          },
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: active ? p.fieldLineActive : p.fieldLine,
          },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: p.fieldHoverLine },
          '& .Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: p.fieldHoverLine },
          '& .MuiSvgIcon-root': { color: p.mutedInk },
          '& input::placeholder': { color: p.placeholder, opacity: 1 },
          '& .MuiAutocomplete-input': { minWidth: '30px !important' },
          '& .MuiAutocomplete-endAdornment': { right: 6 },
          '& .MuiAutocomplete-tag': { m: 0 },
          '& span.MuiAutocomplete-tag': {
            bgcolor: p.pillBg, color: p.pillInk, fontSize: 11, fontWeight: 500,
            lineHeight: '18px', height: 18, borderRadius: '20px', px: 0.75, flexShrink: 0,
          },
        }}
      />
    </Box>
  );
}

/** TimeRangeFilter, same treatment. */
function MockTimeRange({
  p, label, value, min, max, onChange,
}: {
  p: BarPalette; label: string; value: [number, number];
  min: number; max: number; onChange: (next: [number, number]) => void;
}) {
  const active = value[0] > min || value[1] < max;
  return (
    <Box>
      <Typography
        component="span"
        sx={{
          display: 'block', fontSize: 11, fontWeight: 500, color: p.labelInk,
          textTransform: 'uppercase', letterSpacing: 0.3, mb: 0.25,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}
      >
        {label}
      </Typography>
      <Box
        sx={{
          border: '1px solid',
          borderColor: active ? p.fieldLineActive : p.fieldLine,
          bgcolor: active ? p.fieldBgActive : p.fieldBg,
          borderRadius: '4px', px: 1, pt: 0.25, pb: 0.5, height: 34,
          display: 'flex', alignItems: 'center', gap: 1,
        }}
      >
        <Slider
          size="small"
          value={value}
          min={min}
          max={max}
          step={15}
          onChange={(_, next) => onChange(next as [number, number])}
          valueLabelDisplay="auto"
          valueLabelFormat={(v: number) => formatDuration(v)}
          aria-label={label}
          sx={{
            color: p.sliderInk, py: 0,
            '& .MuiSlider-rail': { backgroundColor: p.sliderRail, opacity: 0.45 },
            '& .MuiSlider-track': { border: 'none' },
            '& .MuiSlider-thumb': {
              width: 11, height: 11,
              '&:hover, &.Mui-focusVisible': { boxShadow: `0 0 0 6px ${p.sliderHalo}` },
            },
            '& .MuiSlider-valueLabel': { fontSize: 10, py: 0.25, px: 0.5 },
          }}
        />
        <Typography
          component="span"
          sx={{
            fontSize: 10.5, color: active ? p.ink : p.mutedInk,
            fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', flexShrink: 0,
          }}
        >
          {formatDuration(value[0])}–{formatDuration(value[1])}
        </Typography>
      </Box>
    </Box>
  );
}

type BarState = 'ready' | 'loading' | 'error';

/** WinairTopFilterBar replica. */
function MockFilterBar({
  p, state = 'ready', withRanges = true, initial = {},
}: {
  p: BarPalette; state?: BarState; withRanges?: boolean; initial?: Selections;
}) {
  const [pending, setPending] = useState<Selections>(initial);
  const [dep, setDep] = useState<[number, number]>([DEP_MIN, DEP_MAX]);
  const [dur, setDur] = useState<[number, number]>([DUR_MIN, DUR_MAX]);

  const activeCount = FILTERS.filter(f => (pending[f.id] ?? []).length > 0).length;
  const hasAnySelection = Object.values(pending).some(v => v && v.length > 0);

  return (
    <Box
      sx={{
        width: '100%', mb: 0.75, borderRadius: 1.5, overflow: 'hidden', boxShadow: 1,
        bgcolor: p.bg,
        border: '1px solid', borderColor: p.border,
        color: p.ink,
        px: 1.75, pt: 1, pb: 1.5,
      }}
    >
      {/* ── Actions row ── */}
      <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1.25, rowGap: 1, mb: 1.25 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
          <Tune sx={{ fontSize: 17, color: p.mutedInk }} />
          <Typography sx={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap' }}>Filters</Typography>
        </Box>

        <Box aria-live="polite" sx={{ display: 'flex', alignItems: 'center' }}>
          {hasAnySelection && (
            <Chip
              label={`${activeCount} active`}
              size="small"
              sx={{ height: 20, fontSize: 11, fontWeight: 500, bgcolor: p.countBg, color: p.countInk }}
            />
          )}
        </Box>

        <Box sx={{ flexGrow: 1 }} />

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Button
            size="small"
            disabled={!hasAnySelection}
            onClick={() => setPending({})}
            startIcon={<FilterAltOff fontSize="small" />}
            sx={{
              color: p.clearInk, fontSize: 12, textTransform: 'none', borderRadius: '8px', px: 1.25,
              '&:hover': { bgcolor: p.clearHoverBg },
              '&.Mui-disabled': { color: p.clearDisabledInk },
            }}
          >
            Clear all
          </Button>

          <Button
            size="small"
            variant="contained"
            disabled={!hasAnySelection}
            startIcon={<Check fontSize="small" />}
            sx={{
              bgcolor: p.applyBg, color: p.applyInk, fontSize: 12, fontWeight: 700,
              textTransform: 'none', borderRadius: '8px', px: 1.75, boxShadow: 'none',
              '&:hover': { bgcolor: p.applyHoverBg, boxShadow: 'none' },
              '&.Mui-disabled': { bgcolor: p.applyDisabledBg, color: p.applyDisabledInk },
            }}
          >
            Apply
          </Button>
        </Box>
      </Box>

      {/* ── Filter grid ── */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
          gap: '12px 14px',
          alignItems: 'end',
        }}
      >
        {state === 'loading' && [0, 1, 2, 3].map(i => (
          <Box key={i}>
            <Skeleton variant="text" width="55%" sx={{ fontSize: 11, bgcolor: p.skeletonText }} />
            <Skeleton variant="rounded" height={34} sx={{ bgcolor: p.skeleton }} />
          </Box>
        ))}

        {state === 'error' && (
          <Typography sx={{ gridColumn: '1 / -1', fontSize: 12.5, color: p.errorInk }}>
            Filters unavailable — request failed with status 502
          </Typography>
        )}

        {state === 'ready' && FILTERS.map(f => (
          <MockFilterSelect
            key={f.id}
            p={p}
            id={f.id}
            label={f.label}
            options={f.values}
            value={pending[f.id] ?? []}
            onChange={next => setPending({ ...pending, [f.id]: next })}
          />
        ))}

        {state === 'ready' && withRanges && (
          <>
            <MockTimeRange p={p} label="Departure Time" value={dep} min={DEP_MIN} max={DEP_MAX} onChange={setDep} />
            <MockTimeRange p={p} label="Duration" value={dur} min={DUR_MIN} max={DUR_MAX} onChange={setDur} />
          </>
        )}
      </Box>
    </Box>
  );
}

/** The red tab bar, unchanged — shown so each panel is judged in context. */
function MockTabBar({ bg = BRAND_RED_DARK }: { bg?: string }) {
  const [tab, setTab] = useState('prices');
  return (
    <Box sx={{ bgcolor: bg, borderRadius: 1.5, boxShadow: 1, mb: 0.75, px: 1 }}>
      <Tabs
        value={tab}
        onChange={(_, next) => setTab(next)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{
          minHeight: 44, py: 0.75,
          '& .MuiTabs-indicator': { display: 'none' },
          '& .MuiTabs-scrollButtons': { color: 'rgba(255,255,255,0.82)' },
          '& .MuiTab-root': {
            minHeight: 32, minWidth: 'auto', my: 'auto', mr: 1, py: 0.5, px: 1.75,
            borderRadius: 999,
            bgcolor: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.22)',
            fontSize: 12.5, fontWeight: 500, textTransform: 'none',
            color: 'rgba(255,255,255,0.9)', gap: 0.75,
            '&.Mui-selected': {
              color: '#ffffff', fontWeight: 600,
              bgcolor: 'rgba(255,255,255,0.16)', borderColor: 'rgba(255,255,255,0.55)',
            },
          },
        }}
      >
        <Tab value="prices" label="Latest Prices" icon={<ScatterPlot sx={{ fontSize: 15 }} />} iconPosition="start" />
        {TABS.map(t => <Tab key={t} value={t} label={t} />)}
      </Tabs>
    </Box>
  );
}

/** Page header — title + the two date chips, as on the real page. */
function MockHeader({ dark = false }: { dark?: boolean }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
      <Typography variant="h5" fontWeight={600} sx={{ color: dark ? '#fff' : undefined }}>
        WinAir Dashboard
      </Typography>
      <Chip
        icon={<CalendarMonth sx={{ fontSize: 16 }} />}
        label="Latest data: 29 Jul 2026"
        size="small"
        variant="outlined"
        sx={{ ml: 2, fontWeight: 500, color: BRAND_RED, borderColor: BRAND_RED, '& .MuiChip-icon': { color: BRAND_RED } }}
      />
      <Chip
        icon={<CalendarMonth sx={{ fontSize: 16 }} />}
        label="Cap date: 29 Jul 2026"
        size="small"
        sx={{ ml: 1, fontWeight: 500, bgcolor: BRAND_RED, color: '#fff', '& .MuiChip-icon': { color: '#fff' } }}
      />
    </Box>
  );
}

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 4 }}>
      <Typography sx={{ fontSize: 14, fontWeight: 700, color: 'text.primary' }}>{title}</Typography>
      {sub && <Typography sx={{ fontSize: 12.5, color: 'text.secondary', mb: 1.25 }}>{sub}</Typography>}
      {children}
    </Box>
  );
}

/** Swatch row, so the three surfaces can be compared without the chrome. */
function Swatches() {
  return (
    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 1 }}>
      {LIGHT_OPTIONS.map(p => (
        <Box key={p.key} sx={{ textAlign: 'center' }}>
          <Box sx={{ width: 132, height: 64, bgcolor: p.bg, border: '1px solid', borderColor: p.border, borderRadius: 1.5 }} />
          <Typography sx={{ fontSize: 11.5, fontWeight: 700, mt: 0.5 }}>{p.name.replace(/^Option /, '')}</Typography>
          <Typography sx={{ fontSize: 11, color: 'text.secondary', fontFamily: 'monospace' }}>{p.bg}</Typography>
        </Box>
      ))}
    </Box>
  );
}

const light = createTheme({ palette: { primary: { main: '#1a5276' }, background: { default: '#f6f8f9' } } });
const dark = createTheme({
  palette: { mode: 'dark', primary: { main: '#1a5276' }, background: { default: '#0f1419', paper: '#1a2332' } },
});

function Mock() {
  const [statesFor, setStatesFor] = useState<BarPalette>(OPTION_B);

  return (
    <Box sx={{ p: 3, maxWidth: 1280, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={700} sx={{ mb: 0.5 }}>
        WinAir filter bar — light teal grey mock
      </Typography>
      <Typography sx={{ fontSize: 13, color: 'text.secondary', mb: 3 }}>
        Real MUI controls at the live component's exact metrics. The tab bar above each panel stays
        WinAir red — only the filter card changes. Everything is interactive: open a dropdown, pick
        values, drag a slider, watch Apply light up.
      </Typography>

      <Section title="Surfaces on offer">
        <Swatches />
      </Section>

      {ALL_OPTIONS.map(p => (
        <Section
          key={p.key}
          title={p.name}
          sub={p.note}
        >
          <MockTabBar />
          <MockFilterBar p={p} initial={{ 'NF-1': ['ANU-BGI', 'ANU-DOM', 'ANU-SXM'], 'NF-3': ['4-7'] }} />
        </Section>
      ))}

      <Section
        title="Idle state — nothing selected, Apply and Clear disabled"
        sub="The state the bar is in most of the time. Shown for all three light options."
      >
        {LIGHT_OPTIONS.map(p => (
          <Box key={p.key} sx={{ mb: 1.5 }}>
            <Typography sx={{ fontSize: 11.5, fontWeight: 700, color: 'text.secondary', mb: 0.5 }}>
              {p.name}
            </Typography>
            <MockFilterBar p={p} />
          </Box>
        ))}
      </Section>

      <Section
        title="Loading and failure states"
        sub={`Skeletons and the "filters unavailable" line, on ${statesFor.name}. Click to switch option.`}
      >
        <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
          {LIGHT_OPTIONS.map(p => (
            <Button
              key={p.key}
              size="small"
              variant={statesFor.key === p.key ? 'contained' : 'outlined'}
              onClick={() => setStatesFor(p)}
              sx={{ textTransform: 'none', fontSize: 12 }}
            >
              {p.name.replace(/^Option /, '')}
            </Button>
          ))}
        </Box>
        <MockFilterBar key={`load-${statesFor.key}`} p={statesFor} state="loading" />
        <MockFilterBar key={`err-${statesFor.key}`} p={statesFor} state="error" />
      </Section>

      <Section
        title="In page context — header, tabs, filters, then the dashboard"
        sub="Option B against the real page background, with a stand-in for the embedded dashboard below."
      >
        <Box sx={{ bgcolor: 'background.default', p: 2, borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
          <MockHeader />
          <MockTabBar />
          <MockFilterBar p={OPTION_B} initial={{ 'NF-1': ['ANU-BGI'] }} />
          <Box
            sx={{
              height: 190, borderRadius: 1.5, bgcolor: 'background.paper',
              border: '1px solid', borderColor: 'divider',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>embedded Superset dashboard</Typography>
          </Box>
        </Box>
      </Section>

      <Section
        title="Dark mode check"
        sub="The panel is a fixed light surface, so in dark mode it stays light — deliberate, the same way the red one does not track the theme. Judge whether it glows too hard."
      >
        <ThemeProvider theme={dark}>
          <Box sx={{ bgcolor: '#0f1419', p: 2, borderRadius: 2 }}>
            <MockHeader dark />
            <MockTabBar />
            {LIGHT_OPTIONS.map(p => (
              <Box key={p.key} sx={{ mb: 1.5 }}>
                <Typography sx={{ fontSize: 11.5, fontWeight: 700, color: 'rgba(255,255,255,0.6)', mb: 0.5 }}>
                  {p.name}
                </Typography>
                <MockFilterBar p={p} initial={{ 'NF-1': ['ANU-BGI'] }} />
              </Box>
            ))}
          </Box>
        </ThemeProvider>
      </Section>
    </Box>
  );
}

createRoot(document.getElementById('root')!).render(
  <ThemeProvider theme={light}>
    <CssBaseline />
    <Mock />
  </ThemeProvider>,
);
