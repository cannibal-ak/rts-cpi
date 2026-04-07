import React, { createContext, useContext, useState, useMemo, ReactNode } from 'react';
import { ThemeProvider as MuiThemeProvider, createTheme, CssBaseline } from '@mui/material';

type ThemeMode = 'light' | 'dark';

interface ThemeContextType {
  mode: ThemeMode;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType>({ mode: 'light', toggleTheme: () => {} });

const getTheme = (mode: ThemeMode) => createTheme({
  palette: {
    mode,
    primary: { main: '#1a5276', light: '#2980b9', dark: '#0e2f44' },
    secondary: { main: '#e67e22', light: '#f39c12', dark: '#d35400' },
    background: mode === 'light'
      ? { default: '#f5f7fa', paper: '#ffffff' }
      : { default: '#0f1419', paper: '#1a2332' },
    success: { main: '#27ae60' },
    warning: { main: '#f39c12' },
    error: { main: '#e74c3c' },
    info: { main: '#2980b9' },
  },
  typography: {
    fontFamily: '"Inter", "Roboto", "Helvetica Neue", Arial, sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiButton: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600 } } },
    MuiPaper: { defaultProps: { elevation: 0 }, styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiTableCell: { styleOverrides: { head: { fontWeight: 700 } } },
    MuiDrawer: { styleOverrides: { paper: { borderRight: 'none' } } },
  },
});

export function ThemeContextProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(() => {
    try { return (localStorage.getItem('rts-theme') as ThemeMode) || 'light'; } catch { return 'light'; }
  });

  const toggleTheme = () => {
    setMode(prev => {
      const next = prev === 'light' ? 'dark' : 'light';
      try { localStorage.setItem('rts-theme', next); } catch {}
      return next;
    });
  };

  const theme = useMemo(() => getTheme(mode), [mode]);

  return (
    <ThemeContext.Provider value={{ mode, toggleTheme }}>
      <MuiThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </MuiThemeProvider>
    </ThemeContext.Provider>
  );
}

export function useThemeMode() { return useContext(ThemeContext); }
