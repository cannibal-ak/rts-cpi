import type {
  AirlineSnapshot, CflSnapshot,
  AlertRule, AlertEvent, AlertPreset, TenantFeature,
  FilterMetadata,
} from '../types';

// ── Helpers ─────────────────────────
const rand = (min: number, max: number) => Math.round((Math.random() * (max - min) + min) * 100) / 100;
const randInt = (min: number, max: number) => Math.floor(Math.random() * (max - min + 1)) + min;
const pick = <T>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];
const uuid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

const AIRLINES = ['BA', 'EK', 'SQ', 'LH', 'AF', 'QR', 'VS', 'AA', 'UA', 'DL', 'TK', 'NH'];
const AIRPORTS = ['LHR', 'JFK', 'DXB', 'SIN', 'CDG', 'FRA', 'IST', 'NRT', 'LAX', 'ORD', 'AMS', 'DOH'];
const CABINS = ['F', 'J', 'W', 'Y'];
const POS_CODES = ['GB', 'US', 'AE', 'SG', 'FR', 'DE'];

const FERRY_OPS = ['P&O Ferries', 'DFDS', 'Irish Ferries', 'Stena Line', 'Brittany Ferries', 'Viking Line'];
const PORTS = ['DVR', 'CLS', 'PLY', 'SBG', 'ROS', 'HEL', 'TLL', 'STO', 'CPH'];
const PROD_FAMILIES = ['Standard', 'Flexi', 'Premium', 'Economy Saver', 'Club'];
const EQUIP = ['Spirit of Britain', 'Cote dAlbatros', 'Stena Adventurer', 'MS Viking Grace', 'Pont-Aven'];
const VEH_SIZES = ['car', 'van', 'motorcycle', 'none', 'caravan'];
const CURRENCIES = ['USD'];

// ── Airline snapshots ───────────────
export function generateAirlineSnapshots(count: number = 60): AirlineSnapshot[] {
  const rows: AirlineSnapshot[] = [];
  for (let i = 0; i < count; i++) {
    const tripType = pick(['OW', 'RT'] as const);
    const refOrg = pick(AIRPORTS);
    let refDst = pick(AIRPORTS);
    while (refDst === refOrg) refDst = pick(AIRPORTS);
    const refAl = pick(AIRLINES);
    let compAl = pick(AIRLINES);
    while (compAl === refAl) compAl = pick(AIRLINES);
    const depOffset = randInt(1, 60);
    const depDate = new Date(Date.now() + depOffset * 86400000).toISOString().slice(0, 10);
    const capDate = new Date(Date.now() - randInt(0, 5) * 86400000).toISOString().slice(0, 10);
    const cabin = pick(CABINS);
    const refBase = rand(80, 1200);
    const refTax = rand(20, 180);
    const refYq = rand(0, 80);
    const compBase = refBase * rand(0.7, 1.35);
    const compTax = rand(20, 180);
    const compYq = rand(0, 80);
    rows.push({
      id: `air-${uuid()}`,
      cap_date: capDate,
      cap_time: `${String(randInt(0, 23)).padStart(2, '0')}:${String(randInt(0, 59)).padStart(2, '0')}:00`,
      trip_type: tripType,
      ref_al: refAl,
      ref_flt_num: `${refAl}${randInt(100, 999)}`,
      ref_org: refOrg,
      ref_dst: refDst,
      ref_dep_date: depDate,
      ref_cab_code: cabin,
      ref_tot_fare: Math.round((refBase + refTax + refYq) * 100) / 100,
      ref_base_fare: Math.round(refBase * 100) / 100,
      ref_tax: Math.round(refTax * 100) / 100,
      ref_yq: Math.round(refYq * 100) / 100,
      ref_seats: randInt(1, 9),
      comp_al: compAl,
      comp_flt_num: `${compAl}${randInt(100, 999)}`,
      comp_org: refOrg,
      comp_dst: refDst,
      comp_dep_date: depDate,
      comp_cab_code: cabin,
      comp_tot_fare: Math.round((compBase + compTax + compYq) * 100) / 100,
      comp_base_fare: Math.round(compBase * 100) / 100,
      comp_tax: Math.round(compTax * 100) / 100,
      comp_yq: Math.round(compYq * 100) / 100,
      comp_seats: randInt(1, 9),
      pos: pick(POS_CODES),
      poa: pick(POS_CODES),
    });
  }
  return rows;
}

// ── CFL snapshots ───────────────────
export function generateCflSnapshots(count: number = 40): CflSnapshot[] {
  const rows: CflSnapshot[] = [];
  for (let i = 0; i < count; i++) {
    const tripType = pick(['ONE_WAY', 'ROUND_TRIP'] as const);
    const org = pick(PORTS);
    let dest = pick(PORTS);
    while (dest === org) dest = pick(PORTS);
    const depOffset = randInt(1, 45);
    const depDate = new Date(Date.now() + depOffset * 86400000).toISOString().slice(0, 10);
    const capDate = new Date(Date.now() - randInt(0, 3) * 86400000).toISOString().slice(0, 10);
    const paxFare = rand(25, 220);
    const vehFare = rand(50, 350);
    const cabFare = rand(0, 180);
    const taxes = rand(5, 45);
    rows.push({
      id: `cfl-${uuid()}`,
      cap_date: capDate,
      cap_time: `${String(randInt(0, 23)).padStart(2, '0')}:${String(randInt(0, 59)).padStart(2, '0')}:00`,
      trip_type: tripType,
      source: pick(FERRY_OPS),
      org,
      dest,
      out_dep_date: depDate,
      out_dep_time: `${String(randInt(5, 22)).padStart(2, '0')}:${pick(['00', '15', '30', '45'])}`,
      prod_family: pick(PROD_FAMILIES),
      out_equip_name: pick(EQUIP),
      out_cab_type: pick(['Inside', 'Outside', 'Balcony', 'Suite', 'none']),
      total_fare: Math.round((paxFare + vehFare + cabFare + taxes) * 100) / 100,
      out_per_pax_fare: Math.round(paxFare * 100) / 100,
      out_veh_fare: Math.round(vehFare * 100) / 100,
      out_cab_fare: Math.round(cabFare * 100) / 100,
      out_taxes: Math.round(taxes * 100) / 100,
      out_num_pax: randInt(1, 6),
      veh_size: pick(VEH_SIZES),
      curr_code: pick(CURRENCIES),
      out_avail: pick(['Available', 'Limited', 'Sold Out']),
    });
  }
  return rows;
}

// ── Alert rules ─────────────────────
export function generateAlertRules(): AlertRule[] {
  return [
    { id: 'ar-001', name: 'Fare Drop > 15% on Key Routes', domain: 'airline', rule_type: 'threshold', condition_json: '{"metric":"comp_tot_fare","operator":"decrease_pct","threshold":15,"routes":["LHR-DXB","LHR-JFK","CDG-SIN"]}', is_active: true, created_at: '2026-02-15T10:00:00Z', owner: 'Alex Rivera' },
    { id: 'ar-002', name: 'New Competitor on LHR-JFK', domain: 'airline', rule_type: 'anomaly', condition_json: '{"route":"LHR-JFK","event":"new_carrier"}', is_active: true, created_at: '2026-02-20T14:00:00Z', owner: 'Alex Rivera' },
    { id: 'ar-003', name: 'CFL Price Anomaly Detection', domain: 'cfl', rule_type: 'anomaly', condition_json: '{"metric":"total_fare","zscore_threshold":3}', is_active: false, created_at: '2026-01-10T08:00:00Z', owner: 'Sam Taylor' },
    { id: 'ar-004', name: 'Daily Import Health Check', domain: 'airline', rule_type: 'schedule', condition_json: '{"cron":"0 10 * * *","check":"import_freshness","max_age_hours":24}', is_active: true, created_at: '2026-02-01T09:00:00Z', owner: 'Jordan Chen' },
    { id: 'ar-005', name: 'DVR-CLS Vehicle Fare Spike', domain: 'cfl', rule_type: 'threshold', condition_json: '{"metric":"out_veh_fare","operator":"increase_pct","threshold":25,"route":"DVR-CLS"}', is_active: true, created_at: '2026-02-28T11:00:00Z', owner: 'Morgan Lee' },
  ];
}

// ── Alert events ────────────────────
export function generateAlertEvents(): AlertEvent[] {
  // Relative to now, so the "time ago" labels stay believable whenever this
  // runs. Real DreamAir routes and competitor codes (TC, KQ, YS, UI, ...).
  const hoursAgo = (h: number) =>
    new Date(Date.now() - h * 3_600_000).toISOString();
  const dayOf = (h: number) =>
    new Date(Date.now() - h * 3_600_000).toISOString().slice(0, 10);

  const ev = (
    id: string, h: number, severity: AlertEvent['severity'],
    rule_key: string, rule_name: string, message: string,
    payload: AlertEvent['payload'], is_read: boolean,
  ): AlertEvent => ({
    id, rule_id: `ar-${rule_key}`, rule_key, rule_name,
    triggered_at: hoursAgo(h), severity, message,
    delivery_status: 'sent', scope_key: null,
    observed_at: dayOf(h), prev_observed_at: dayOf(h + 48),
    evaluation_mode: 'live', payload, is_read,
  });

  return [
    ev('ae-001', 2, 'warning', 'undercut_position', 'Lost the cheapest position',
       'We are no longer cheapest on ZNZ-NBO for departures 00-07 days out - rank 3 of 3. YS at USD 205.00 against our USD 333.75.',
       { route: 'ZNZ-NBO', origin: 'ZNZ', destination: 'NBO', window: '00-07',
         currency: 'USD', state: 'undercut', da_fare: 333.75, da_rank: 3,
         competitor_count: 3, best_competitor: 'YS', best_competitor_fare: 205.0 }, false),
    ev('ae-002', 5, 'warning', 'comp_price_move', 'Competitor fare moved sharply',
       'TC cut its ZNZ-NBO fare 30.6% (USD 229.00 → USD 159.00) for departures 15-30 days out.',
       { route: 'ZNZ-NBO', competitor: 'TC', window: '15-30', currency: 'USD',
         prev_value: 229.0, current_value: 159.0, delta_abs: -70.0,
         delta_pct: -30.6, direction: 'down' }, false),
    ev('ae-003', 9, 'warning', 'comp_price_move', 'Competitor fare moved sharply',
       'UI cut its DAR-ARK fare 26.3% (USD 95.00 → USD 70.00) for departures 00-07 days out.',
       { route: 'DAR-ARK', competitor: 'UI', window: '00-07', currency: 'USD',
         prev_value: 95.0, current_value: 70.0, delta_abs: -25.0,
         delta_pct: -26.3, direction: 'down' }, false),
    ev('ae-004', 26, 'info', 'undercut_position', 'Lost the cheapest position',
       'We are cheapest again on JRO-MWZ for departures 08-14 days out at USD 108.40.',
       { route: 'JRO-MWZ', window: '08-14', currency: 'USD', state: 'cheapest',
         da_fare: 108.4, da_rank: 1, competitor_count: 1 }, false),
    ev('ae-005', 30, 'warning', 'comp_price_move', 'Competitor fare moved sharply',
       'TC raised its ARK-ZNZ fare 46.1% (USD 204.00 → USD 298.00) for departures 08-14 days out.',
       { route: 'ARK-ZNZ', competitor: 'TC', window: '08-14', currency: 'USD',
         prev_value: 204.0, current_value: 298.0, delta_abs: 94.0,
         delta_pct: 46.1, direction: 'up' }, true),
    ev('ae-006', 33, 'warning', 'undercut_position', 'Lost the cheapest position',
       'We are no longer cheapest on JRO-DAR for departures 00-07 days out - rank 2 of 2. TC at USD 150.00 against our USD 160.40.',
       { route: 'JRO-DAR', window: '00-07', currency: 'USD', state: 'undercut',
         da_fare: 160.4, da_rank: 2, competitor_count: 1,
         best_competitor: 'TC', best_competitor_fare: 150.0 }, true),
    ev('ae-007', 51, 'warning', 'comp_price_move', 'Competitor fare moved sharply',
       'KQ cut its DAR-NBO fare 18.4% (USD 326.00 → USD 266.00) for departures 00-07 days out.',
       { route: 'DAR-NBO', competitor: 'KQ', window: '00-07', currency: 'USD',
         prev_value: 326.0, current_value: 266.0, delta_abs: -60.0,
         delta_pct: -18.4, direction: 'down' }, true),
    ev('ae-008', 55, 'info', 'undercut_position', 'Lost the cheapest position',
       'We are cheapest again on JRO-ZNZ for departures 08-14 days out at USD 169.40.',
       { route: 'JRO-ZNZ', window: '08-14', currency: 'USD', state: 'cheapest',
         da_fare: 169.4, da_rank: 1, competitor_count: 1 }, true),
    ev('ae-009', 74, 'warning', 'comp_price_move', 'Competitor fare moved sharply',
       'YS raised its ARK-ZNZ fare 22.8% (USD 151.00 → USD 185.00) for departures 15-30 days out.',
       { route: 'ARK-ZNZ', competitor: 'YS', window: '15-30', currency: 'USD',
         prev_value: 151.0, current_value: 185.0, delta_abs: 34.0,
         delta_pct: 22.8, direction: 'up' }, true),
    ev('ae-010', 80, 'warning', 'comp_price_move', 'Competitor fare moved sharply',
       'TC cut its DAR-MWZ fare 13.5% (USD 192.00 → USD 166.00) for departures 00-07 days out.',
       { route: 'DAR-MWZ', competitor: 'TC', window: '00-07', currency: 'USD',
         prev_value: 192.0, current_value: 166.0, delta_abs: -26.0,
         delta_pct: -13.5, direction: 'down' }, true),
    ev('ae-011', 98, 'info', 'undercut_position', 'Lost the cheapest position',
       'We are cheapest again on ARK-ZNZ for departures 08-14 days out at USD 224.40.',
       { route: 'ARK-ZNZ', window: '08-14', currency: 'USD', state: 'cheapest',
         da_fare: 224.4, da_rank: 1, competitor_count: 4 }, true),
    ev('ae-012', 121, 'warning', 'comp_price_move', 'Competitor fare moved sharply',
       'Coa cut its DAR-JRO fare 34.2% (USD 452.00 → USD 297.00) for departures 15-30 days out.',
       { route: 'DAR-JRO', competitor: 'Coa', window: '15-30', currency: 'USD',
         prev_value: 452.0, current_value: 297.0, delta_abs: -155.0,
         delta_pct: -34.2, direction: 'down' }, true),
    ev('ae-013', 145, 'warning', 'undercut_position', 'Lost the cheapest position',
       'We are no longer cheapest on DAR-MWZ for departures 08-14 days out - rank 2 of 2. YS at USD 131.00 against our USD 166.40.',
       { route: 'DAR-MWZ', window: '08-14', currency: 'USD', state: 'undercut',
         da_fare: 166.4, da_rank: 2, competitor_count: 1,
         best_competitor: 'YS', best_competitor_fare: 131.0 }, true),
    ev('ae-014', 168, 'warning', 'comp_price_move', 'Competitor fare moved sharply',
       'Fli raised its JRO-NBO fare 27.9% (USD 283.00 → USD 362.00) for departures 00-07 days out.',
       { route: 'JRO-NBO', competitor: 'Fli', window: '00-07', currency: 'USD',
         prev_value: 283.0, current_value: 362.0, delta_abs: 79.0,
         delta_pct: 27.9, direction: 'up' }, true),
  ];
}

// The server fills the routes and competitors pickers per request from the
// tenant's own captures. The mock has no capture table, so it names the routes
// and carriers its own fixtures use. Without these, every `options` here is
// null and the settings screen in mock mode shows NO multiselects at all —
// which looks exactly like the bug it took months to notice in production.
const _MOCK_ROUTES = ['ARK-ZNZ', 'DAR-ARK', 'DAR-JRO', 'DAR-MWZ', 'DAR-NBO',
                      'JRO-DAR', 'JRO-MWZ', 'JRO-NBO', 'JRO-ZNZ', 'ZNZ-NBO'];
const _MOCK_COMPETITORS = ['Coa', 'Fli', 'KQ', 'TC', 'UI', 'YS'];

const _ROUTES_TUNABLE = {
  key: 'routes', label: 'Routes', type: 'multiselect' as const,
  unit: null, min: null, max: null, step: null,
  options: _MOCK_ROUTES, help: 'Leave empty to watch every route.',
};

const _COMPETITORS_TUNABLE = {
  key: 'competitors', label: 'Competitors', type: 'multiselect' as const,
  unit: null, min: null, max: null, step: null,
  options: _MOCK_COMPETITORS, help: 'Leave empty to watch every competitor.',
};

const _TRIP_TYPE_TUNABLE = {
  key: 'trip_types', label: 'Trip types', type: 'multiselect' as const,
  unit: null, min: null, max: null, step: null,
  options: ['OW', 'RT'],
  help: 'Leave empty to watch every product the feed carries.',
};

const _WINDOW_TUNABLE = {
  key: 'windows', label: 'Departure windows', type: 'multiselect' as const,
  unit: null, min: null, max: null, step: null,
  options: ['00-07', '08-14', '15-30'],
  help: 'How far ahead of departure to watch, in days.',
};

export function generateAlertPresets(): AlertPreset[] {
  return [
    {
      id: 'ar-undercut_position', rule_key: 'undercut_position',
      name: 'Lost the cheapest position',
      description: 'Our cheapest available fare on a route and departure window fell behind the competition, or recovered.',
      domain: 'airline', rule_type: 'threshold', is_active: true,
      is_preset: true, severity_default: 'warning',
      condition: { max_rank: 1, min_gap_pct: 1.0, notify_on_recovery: true,
                   windows: ['00-07', '08-14', '15-30'], routes: null },
      tunables: [
        { key: 'max_rank', label: 'Alert when our rank falls below', type: 'number',
          unit: 'places', min: 1, max: 5, step: 1, options: null,
          help: '1 means alert as soon as we are no longer cheapest.' },
        { key: 'min_gap_pct', label: 'Ignore gaps smaller than', type: 'number',
          unit: 'percent', min: 0, max: 20, step: 0.5, options: null,
          help: 'Stops being undercut by pennies from raising an alert.' },
        { key: 'notify_on_recovery', label: 'Also tell me when we recover',
          type: 'bool', unit: null, min: null, max: null, step: null,
          options: null, help: null },
        _ROUTES_TUNABLE,
        _WINDOW_TUNABLE,
      ],
      missing_requirements: [], created_at: null, updated_at: null, updated_by: null,
    },
    {
      id: 'ar-comp_price_move', rule_key: 'comp_price_move',
      name: 'Competitor fare moved sharply',
      description: "A competitor's cheapest available fare on a route and departure window moved by more than the threshold since the previous capture.",
      domain: 'airline', rule_type: 'threshold', is_active: true,
      is_preset: true, severity_default: 'warning',
      condition: { move_pct: 10.0, direction: 'both', min_abs_move: 5.0,
                   windows: ['00-07', '08-14', '15-30'], competitors: null, routes: null },
      tunables: [
        { key: 'move_pct', label: 'Move of at least', type: 'number',
          unit: 'percent', min: 1, max: 50, step: 0.5, options: null,
          help: 'Percentage change against the previous capture.' },
        { key: 'min_abs_move', label: 'and at least', type: 'number',
          unit: 'currency', min: 0, max: 500, step: 1, options: null,
          help: 'Ignores large percentages on cheap fares.' },
        { key: 'direction', label: 'Direction', type: 'enum', unit: null,
          min: null, max: null, step: null, options: ['down', 'up', 'both'], help: null },
        { key: 'competitors', label: 'Competitors', type: 'multiselect',
          unit: null, min: null, max: null, step: null, options: null,
          help: 'Leave empty to watch every competitor.' },
        _WINDOW_TUNABLE,
      ],
      missing_requirements: [], created_at: null, updated_at: null, updated_by: null,
    },
    {
      id: 'ar-comp_price_threshold', rule_key: 'comp_price_threshold',
      name: 'Competitor fare crossed a price line',
      description: "A competitor's cheapest available fare crossed an absolute price you set.",
      domain: 'airline', rule_type: 'threshold', is_active: false,
      is_preset: true, severity_default: 'info',
      condition: { operator: 'below', value: null, currency: 'USD',
                   windows: ['00-07'], competitors: null, routes: null },
      tunables: [
        { key: 'operator', label: 'Alert when the fare goes', type: 'enum',
          unit: null, min: null, max: null, step: null,
          options: ['below', 'above'], help: null },
        { key: 'value', label: 'this price', type: 'number', unit: 'currency',
          min: 0, max: 100000, step: 1, options: null, help: null },
        { key: 'routes', label: 'on routes', type: 'multiselect', unit: null,
          min: null, max: null, step: null, options: null, help: null },
        { key: 'competitors', label: 'Competitors', type: 'multiselect',
          unit: null, min: null, max: null, step: null, options: null,
          help: 'Leave empty to watch every competitor.' },
        _WINDOW_TUNABLE,
      ],
      missing_requirements: ['value', 'routes'],
      created_at: null, updated_at: null, updated_by: null,
    },
    {
      id: 'ar-stops_disadvantage', rule_key: 'stops_disadvantage',
      name: 'A competitor flies it in fewer stops',
      description: 'The best itinerary we have on sale for a route and departure window makes more stops than the best a competitor is selling.',
      domain: 'airline', rule_type: 'threshold', is_active: false,
      is_preset: true, severity_default: 'warning',
      condition: { min_stop_gap: 1, min_days: 3, min_day_share: 50.0,
                   notify_on_recovery: true,
                   windows: ['00-07', '08-14', '15-30'],
                   trip_types: null, routes: null, competitors: null },
      tunables: [
        { key: 'min_stop_gap', label: 'Alert when they are ahead by at least',
          type: 'number', unit: 'stops', min: 1, max: 3, step: 1, options: null,
          help: '1 means alert as soon as anyone offers a shorter itinerary.' },
        { key: 'min_days', label: 'over at least this many departure days',
          type: 'number', unit: 'days', min: 1, max: 15, step: 1, options: null,
          help: 'Only days where both sides publish a stop count.' },
        { key: 'min_day_share', label: 'on at least this share of them',
          type: 'number', unit: 'percent', min: 1, max: 100, step: 5,
          options: null, help: null },
        { key: 'notify_on_recovery', label: 'Also tell me when we match them again',
          type: 'bool', unit: null, min: null, max: null, step: null,
          options: null, help: null },
        _ROUTES_TUNABLE, _COMPETITORS_TUNABLE, _TRIP_TYPE_TUNABLE, _WINDOW_TUNABLE,
      ],
      missing_requirements: [], created_at: null, updated_at: null, updated_by: null,
    },
    {
      id: 'ar-service_gap', rule_key: 'service_gap',
      name: 'Nothing of ours on sale while they sell',
      description: 'On several departure days in a window we have no fare on sale -- no flight at all, or a flight with no fare -- while competitors do.',
      domain: 'airline', rule_type: 'threshold', is_active: false,
      is_preset: true, severity_default: 'warning',
      condition: { min_gap_days: 3, min_days_observed: 4, min_competitors: 1,
                   include_sold_out: true, notify_on_recovery: true,
                   windows: ['00-07'],
                   trip_types: null, routes: null, competitors: null },
      tunables: [
        { key: 'min_gap_days', label: 'Alert when we are off sale for',
          type: 'number', unit: 'days', min: 1, max: 30, step: 1, options: null,
          help: 'Clears only when we are back on sale on every observed day.' },
        { key: 'min_days_observed', label: 'Ignore windows with fewer than',
          type: 'number', unit: 'days', min: 1, max: 30, step: 1, options: null,
          help: 'Some feeds sample only a few departure dates per window.' },
        { key: 'min_competitors', label: 'and at least this many competitors selling',
          type: 'number', unit: 'airlines', min: 1, max: 10, step: 1,
          options: null, help: null },
        { key: 'include_sold_out', label: 'Count days we fly but have no fare',
          type: 'bool', unit: null, min: null, max: null, step: null,
          options: null, help: null },
        { key: 'notify_on_recovery', label: 'Also tell me when we are back on sale',
          type: 'bool', unit: null, min: null, max: null, step: null,
          options: null, help: null },
        _ROUTES_TUNABLE, _COMPETITORS_TUNABLE, _TRIP_TYPE_TUNABLE, _WINDOW_TUNABLE,
      ],
      missing_requirements: [], created_at: null, updated_at: null, updated_by: null,
    },
  ];
}






// ── Tenant features ─────────────────
export function generateTenantFeatures(): TenantFeature[] {
  return [
    { code: 'airline', label: 'Airline CPI Module', category: 'module', enabled: true },
    { code: 'cfl', label: 'Cruise / Ferry CPI Module', category: 'module', enabled: true },
    { code: 'alerts', label: 'Alerting Engine', category: 'capability', enabled: true },
    { code: 'exports', label: 'Data Exports', category: 'capability', enabled: true },
    { code: 'saved_views', label: 'Saved Views', category: 'capability', enabled: true },
    { code: 'superset_embed', label: 'Superset Embedded Dashboards', category: 'analytics', enabled: true },
    { code: 'cross_domain', label: 'Cross-Domain Harmonized Views', category: 'analytics', enabled: false },
    { code: 'co_branding', label: 'Tenant Co-Branding', category: 'branding', enabled: false },
  ];
}

// ── Filter metadata ─────────────────
export function airlineFilterMeta(): FilterMetadata[] {
  return [
    { field: 'file_date', label: 'File Date', values: ['2026-03-10', '2026-03-09', '2026-03-08'] },
    { field: 'airline', label: 'Airline', values: ['JY', 'PW'] },
  ];
}

export function cflFilterMeta(): FilterMetadata[] {
  return [
    { field: 'file_date', label: 'File Date', values: ['2026-03-10', '2026-03-09'] },
    { field: 'operator', label: 'Airline / Operator', values: ['FJL'] },
  ];
}

// ── Exported Constants ──────────────
export const mockAirlineSnapshots: AirlineSnapshot[] = [];
export const mockCflSnapshots: CflSnapshot[] = [];
export const mockAlertRules = generateAlertRules();
export const mockAlertEvents = generateAlertEvents();
export const mockAlertPresets = generateAlertPresets();


export const mockTenantFeatures = generateTenantFeatures();

export const mockFilterMetadata = {
  airline: airlineFilterMeta(),
  cfl: cflFilterMeta(),
};
