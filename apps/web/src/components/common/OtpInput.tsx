import React, { useRef, useMemo, useCallback } from 'react';
import { Box, useTheme } from '@mui/material';

export type OtpCharset = 'numeric' | 'hex';

export interface OtpInputProps {
  groups: number[];
  value: string;
  onChange: (value: string) => void;
  charset?: OtpCharset;
  separator?: string;
  autoFocus?: boolean;
  disabled?: boolean;
  onComplete?: (value: string) => void;
  ariaLabelPrefix?: string;
}

const sanitize = (s: string, charset: OtpCharset): string =>
  charset === 'hex'
    ? s.replace(/[^0-9a-fA-F]/g, '').toLowerCase()
    : s.replace(/[^0-9]/g, '');

const OtpInput: React.FC<OtpInputProps> = ({
  groups,
  value,
  onChange,
  charset = 'numeric',
  separator = '-',
  autoFocus = false,
  disabled = false,
  onComplete,
  ariaLabelPrefix = 'Digit',
}) => {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const accent = isDark ? '#90CAF9' : '#1565C0';
  const borderIdle = isDark ? 'rgba(255,255,255,0.23)' : 'rgba(0,0,0,0.23)';

  const total = useMemo(() => groups.reduce((a, b) => a + b, 0), [groups]);
  const offsets = useMemo(() => {
    const out: number[] = [];
    let acc = 0;
    for (const size of groups) { out.push(acc); acc += size; }
    return out;
  }, [groups]);

  const inputsRef = useRef<Array<HTMLInputElement | null>>([]);

  const chars = useMemo(() => {
    const stripped = value.split('').filter((c) => c !== separator);
    const arr: string[] = new Array(total).fill('');
    for (let i = 0; i < Math.min(stripped.length, total); i += 1) arr[i] = stripped[i];
    return arr;
  }, [value, total, separator]);

  const assemble = useCallback(
    (flat: string[]): string => {
      const parts: string[] = [];
      let idx = 0;
      for (const size of groups) {
        parts.push(flat.slice(idx, idx + size).join(''));
        idx += size;
      }
      return parts.join(separator);
    },
    [groups, separator],
  );

  const emit = useCallback(
    (flat: string[]) => {
      const next = assemble(flat);
      onChange(next);
      if (onComplete && flat.filter(Boolean).length === total) onComplete(next);
    },
    [assemble, onChange, onComplete, total],
  );

  const focusBox = (i: number) => {
    const el = inputsRef.current[i];
    if (el) { el.focus(); el.select(); }
  };

  const handleChange = (i: number, raw: string) => {
    const clean = sanitize(raw, charset);
    const flat = [...chars];
    if (clean === '') { flat[i] = ''; emit(flat); return; }
    flat[i] = clean.slice(-1);
    emit(flat);
    if (i < total - 1) focusBox(i + 1);
  };

  const handleKeyDown = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      const flat = [...chars];
      if (chars[i]) { flat[i] = ''; emit(flat); }
      else if (i > 0) { e.preventDefault(); flat[i - 1] = ''; emit(flat); focusBox(i - 1); }
    } else if (e.key === 'ArrowLeft' && i > 0) { e.preventDefault(); focusBox(i - 1); }
    else if (e.key === 'ArrowRight' && i < total - 1) { e.preventDefault(); focusBox(i + 1); }
  };

  const handlePaste = (i: number, e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = sanitize(e.clipboardData.getData('text'), charset);
    if (!pasted) return;
    const flat = [...chars];
    let idx = i;
    for (const ch of pasted) { if (idx >= total) break; flat[idx] = ch; idx += 1; }
    emit(flat);
    focusBox(Math.min(idx, total - 1));
  };

  return (
    <Box
      role="group"
      aria-label={`${ariaLabelPrefix} input`}
      sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}
    >
      {groups.map((size, g) => (
        <React.Fragment key={`g-${g}`}>
          {g > 0 && (
            <Box aria-hidden sx={{ color: 'text.secondary', fontSize: 22, px: 0.25, userSelect: 'none' }}>
              {separator}
            </Box>
          )}
          <Box sx={{ display: 'flex', gap: 1 }}>
            {Array.from({ length: size }, (_, k) => offsets[g] + k).map((i) => (
              <Box
                key={i}
                component="input"
                ref={(el: HTMLInputElement | null) => { inputsRef.current[i] = el; }}
                inputMode={charset === 'numeric' ? 'numeric' : 'text'}
                autoComplete={i === 0 ? 'one-time-code' : 'off'}
                disabled={disabled}
                autoFocus={autoFocus && i === 0}
                value={chars[i] || ''}
                aria-label={`${ariaLabelPrefix} ${i + 1}`}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleChange(i, e.target.value)}
                onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => handleKeyDown(i, e)}
                onPaste={(e: React.ClipboardEvent<HTMLInputElement>) => handlePaste(i, e)}
                onFocus={(e: React.FocusEvent<HTMLInputElement>) => e.target.select()}
                sx={{
                  width: 44, height: 54, textAlign: 'center', fontSize: 22, fontWeight: 500,
                  fontFamily: charset === 'hex' ? 'monospace' : 'inherit',
                  color: 'text.primary', background: 'transparent',
                  border: `1px solid ${borderIdle}`, borderRadius: 1, outline: 'none',
                  transition: 'border-color 120ms, box-shadow 120ms',
                  '&:hover': { borderColor: accent },
                  '&:focus': { borderColor: accent, boxShadow: `0 0 0 2px ${accent}33` },
                  '&:disabled': { opacity: 0.5, cursor: 'not-allowed' },
                }}
              />
            ))}
          </Box>
        </React.Fragment>
      ))}
    </Box>
  );
};

export default OtpInput;
