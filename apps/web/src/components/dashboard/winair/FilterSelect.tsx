import { Autocomplete, TextField, Checkbox, Chip, Tooltip, Box, Typography } from '@mui/material';
import { CheckBoxOutlineBlank, CheckBox as CheckBoxIcon, KeyboardArrowDown } from '@mui/icons-material';
import {
  BANNER_HEADER_BG,
  FIELD_BG,
  FIELD_BG_ACTIVE,
  FIELD_LINE,
  FIELD_LINE_ACTIVE,
  LABEL_INK,
  MUTED_INK,
} from '../bannerTheme';

export interface FilterSelectProps {
  label: string;
  options: string[];
  value: string[];
  onChange: (next: string[]) => void;
  multiple?: boolean;
  disabled?: boolean;
  description?: string | null;
  /** Rendered on a dark surface (the WinAir banner) — inverts text/borders. */
  onDark?: boolean;
  /** Ties the label to the input. Native filter ids are unique per dashboard. */
  id?: string;
  minWidth?: number;
}

/**
 * One native-filter control for the out-of-iframe filter bar.
 *
 * Autocomplete rather than a plain Select because these option lists come
 * straight from the data and some are long — Flight Number alone has ~95
 * entries — so type-to-filter matters. Empty selection renders as "All",
 * which is exactly what an unset Superset native filter means.
 *
 * The label sits above the field rather than in MUI's floating notch: the
 * notch reserves horizontal space proportional to the label text, so fields
 * sharing a minWidth still rendered at different widths — the reason the bar
 * never lined up. With the label outside, the grid alone decides width.
 */
export default function FilterSelect({
  label,
  options,
  value,
  onChange,
  multiple = true,
  disabled = false,
  description,
  onDark = false,
  id,
  minWidth = 0,
}: FilterSelectProps) {
  const ink = onDark ? '#ffffff' : undefined;
  const active = value.length > 0;
  const fieldId = id ? `filter-${id}` : undefined;

  const control = (
    // minWidth 0 lets the grid track shrink — without it a long option value
    // sets the track's min-content width and blows the column out.
    <Box sx={{ minWidth: minWidth || 0 }}>
      <Typography
        component="label"
        htmlFor={fieldId}
        noWrap
        sx={{
          display: 'block',
          fontSize: 11,
          fontWeight: 500,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          color: onDark ? (active ? '#ffffff' : LABEL_INK) : 'text.secondary',
          mb: '5px',
        }}
      >
        {label}
      </Typography>

      <Autocomplete
        id={fieldId}
        multiple={multiple}
        size="small"
        fullWidth
        disableCloseOnSelect={multiple}
        limitTags={1}
        getLimitTagsText={more => `+${more}`}
        popupIcon={<KeyboardArrowDown fontSize="small" />}
        options={options}
        value={multiple ? value : (value[0] ?? null) as never}
        onChange={(_, next) => {
          if (multiple) onChange((next as string[]) ?? []);
          else onChange(next ? [next as string] : []);
        }}
        disabled={disabled || options.length === 0}
        renderOption={(props, option, { selected }) => {
          const { key, ...rest } = props as { key?: string } & Record<string, unknown>;
          return (
            <li key={key ?? option} {...rest} style={{ fontSize: 13 }}>
              {multiple && (
                <Checkbox
                  icon={<CheckBoxOutlineBlank fontSize="small" />}
                  checkedIcon={<CheckBoxIcon fontSize="small" />}
                  checked={selected}
                  size="small"
                  sx={{ mr: 0.75, p: 0.25 }}
                />
              )}
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
                  height: 20,
                  maxWidth: 120,
                  fontSize: 11,
                  m: 0,
                  bgcolor: onDark ? 'rgba(255,255,255,0.22)' : undefined,
                  color: ink,
                  '& .MuiChip-label': { px: 0.75 },
                  '& .MuiChip-deleteIcon': { color: onDark ? 'rgba(255,255,255,0.7)' : undefined },
                }}
              />
            );
          })
        }
        renderInput={(params) => (
          <TextField
            {...params}
            placeholder={value.length === 0 ? 'All' : undefined}
            variant="outlined"
          />
        )}
        sx={{
          '& .MuiInputBase-root': {
            minHeight: 34,
            py: '2px !important',
            pl: '8px',
            pr: '52px !important',
            gap: '3px',
            fontSize: 12,
            color: ink,
            borderRadius: '8px',
            // Chips must not wrap: a second chip row would make this field
            // taller than its neighbours and break the grid's baseline.
            flexWrap: 'nowrap',
            overflow: 'hidden',
            bgcolor: onDark ? (active ? FIELD_BG_ACTIVE : FIELD_BG) : undefined,
          },
          '& .MuiOutlinedInput-notchedOutline': {
            borderColor: onDark ? (active ? FIELD_LINE_ACTIVE : FIELD_LINE) : undefined,
          },
          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: onDark ? '#ffffff' : undefined },
          '& .Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: onDark ? '#ffffff' : undefined },
          '& .MuiSvgIcon-root': { color: onDark ? MUTED_INK : undefined },
          '& input::placeholder': { color: onDark ? 'rgba(255,255,255,0.55)' : undefined, opacity: 1 },
          '& .MuiAutocomplete-input': { minWidth: '30px !important' },
          '& .MuiAutocomplete-endAdornment': { right: 6 },
          '& .MuiAutocomplete-tag': { m: 0 },
          // MUI's own "+N" overflow marker, restyled as a count pill. Scoped to
          // the span: the class is on the chips as well, and a descendant
          // selector here outranks the chips' own sx.
          '& span.MuiAutocomplete-tag': {
            ...(onDark && {
              bgcolor: '#ffffff',
              color: BANNER_HEADER_BG,
              fontSize: 11,
              fontWeight: 500,
              lineHeight: '18px',
              height: 18,
              borderRadius: '20px',
              px: 0.75,
              flexShrink: 0,
            }),
          },
        }}
      />
    </Box>
  );

  // Tooltip on the whole cell, so hovering the label also surfaces the
  // filter's description.
  return description ? <Tooltip title={description} placement="top">{control}</Tooltip> : control;
}
