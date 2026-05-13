/**
 * API client barrel export.
 *
 * When VITE_API_BASE_URL is set → uses the real HTTP client (talks to FastAPI).
 * Otherwise → falls back to the in-memory mock client.
 */
export type { CpiApiClient, SnapshotQuery, JobQuery } from './client';

import { mockClient } from './mockClient';
import { httpClient } from './httpClient';

const useRealApi = !!import.meta.env.VITE_API_BASE_URL;

export const api = useRealApi ? httpClient : mockClient;
