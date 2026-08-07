import { Autocomplete, TextField, Checkbox, Chip, Tooltip } from '@mui/material';
import { CheckBoxOutlineBlank, CheckBox as CheckBoxIcon } from '@mui/icons-material';

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
  minWidth?: number;
}

/**
 * One native-filter control for the out-of-iframe filter bar.
 *
 * Autocomplete rather than a plain Select because these option lists come
 * straight from the data and some are long — Flight Number alone has ~95
 * entries — so type-to-filter matters. Empty selection renders as "All",
 * which is exactly what an unset Superset native filter means.
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
  minWidth = 180,
}: FilterSelectProps) {
  const ink = onDark ? '#ffffff' : undefined;
  const line = onDark ? 'rgba(255,255,255,0.35)' : undefined;

  const control = (
    <Autocomplete
      multiple={multiple}
      size="small"
      disableCloseOnSelect={multiple}
      limitTags={1}
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
                fontSize: 11,
                bgcolor: onDark ? 'rgba(255,255,255,0.22)' : undefined,
                color: ink,
                '& .MuiChip-deleteIcon': { color: onDark ? 'rgba(255,255,255,0.7)' : undefined },
              }}
            />
          );
        })
      }
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={value.length === 0 ? 'All' : undefined}
          variant="outlined"
        />
      )}
      sx={{
        minWidth,
        maxWidth: 300,
        '& .MuiInputBase-root': { py: '2px !important', fontSize: 12, color: ink },
        '& .MuiInputLabel-root': { fontSize: 12, color: onDark ? 'rgba(255,255,255,0.8)' : undefined },
        '& .MuiInputLabel-root.Mui-focused': { color: ink },
        '& .MuiOutlinedInput-notchedOutline': { borderColor: line },
        '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: onDark ? '#ffffff' : undefined },
        '& .Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: onDark ? '#ffffff' : undefined },
        '& .MuiSvgIcon-root': { color: onDark ? 'rgba(255,255,255,0.8)' : undefined },
        '& input::placeholder': { color: onDark ? 'rgba(255,255,255,0.65)' : undefined, opacity: 1 },
      }}
    />
  );

  return description ? <Tooltip title={description}>{control}</Tooltip> : control;
}
