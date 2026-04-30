import {
  Box,
  Drawer,
  Typography,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  IconButton,
  Stack,
  Chip,
  Divider,
  Tooltip,
} from '@mui/material';
import {
  FilterList,
  Close,
  RestartAlt,
} from '@mui/icons-material';

interface FilterField {
  key: string;
  label: string;
  type: 'text' | 'select' | 'date' | 'daterange';
  options?: { value: string; label: string }[];
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
}

interface FilterPanelProps {
  title: string;
  fields: FilterField[];
  open: boolean;
  onToggle: () => void;
  onApply?: () => void;
  values: Record<string, string>;
  onValuesChange: (values: Record<string, string>) => void;
  onReset?: () => void;
}

export default function FilterPanel({ title, fields, open, onToggle, onApply, values, onValuesChange, onReset }: FilterPanelProps) {
  const activeCount = Object.values(values).filter(v => v && v.length > 0).length;

  const handleChange = (key: string, value: string) => {
    onValuesChange({ ...values, [key]: value });
  };

  const handleReset = () => {
    if (onReset) {
      onReset();
    } else {
      onValuesChange({});
    }
  };

  const handleApply = () => {
    onApply?.();
  };

  return (
    <>
      {/* Toggle button when closed */}
      {!open && (
        <Tooltip title="Open filters">
          <Button
            variant="outlined"
            startIcon={<FilterList />}
            onClick={onToggle}
            size="small"
            aria-label="Open filter panel"
          >
            Filters{activeCount > 0 ? ` (${activeCount})` : ''}
          </Button>
        </Tooltip>
      )}

      {/* Filter drawer */}
      <Drawer
        variant="persistent"
        anchor="left"
        open={open}
        sx={{
          position: 'relative',
          '& .MuiDrawer-paper': {
            position: 'relative',
            width: 300,
            border: 'none',
            borderRight: 1,
            borderColor: 'divider',
            bgcolor: 'background.default',
          },
        }}
      >
        <Box sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <FilterList fontSize="small" />
              <Typography variant="subtitle1" fontWeight={600}>{title}</Typography>
              {activeCount > 0 && <Chip label={activeCount} size="small" color="primary" />}
            </Box>
            <IconButton size="small" onClick={onToggle} aria-label="Close filter panel">
              <Close fontSize="small" />
            </IconButton>
          </Box>

          <Divider sx={{ mb: 2 }} />

          <Stack spacing={2} sx={{ flex: 1, overflowY: 'auto', overflowX: 'visible', pt: 1.5, px: 0.5, pb: 1 }}>
            {fields.map(field => {
              if (field.type === 'select') {
                return (
                  <FormControl key={field.key} size="small" fullWidth>
                    <InputLabel id={`filter-${field.key}-label`}>{field.label}</InputLabel>
                    <Select
                      labelId={`filter-${field.key}-label`}
                      value={values[field.key] || ''}
                      label={field.label}
                      onChange={e => handleChange(field.key, e.target.value as string)}
                      disabled={field.disabled}
                    >
                      {!field.required && <MenuItem value=""><em>All</em></MenuItem>}
                      {field.options?.map(opt => (
                        <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                );
              }

              if (field.type === 'date' || field.type === 'daterange') {
                return (
                  <TextField
                    key={field.key}
                    label={field.label}
                    type="date"
                    size="small"
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    value={values[field.key] || ''}
                    onChange={e => handleChange(field.key, e.target.value)}
                    disabled={field.disabled}
                  />
                );
              }

              return (
                <TextField
                  key={field.key}
                  label={field.label}
                  size="small"
                  fullWidth
                  placeholder={field.placeholder}
                  value={values[field.key] || ''}
                  onChange={e => handleChange(field.key, e.target.value)}
                  disabled={field.disabled}
                />
              );
            })}
          </Stack>

          <Divider sx={{ my: 2 }} />

          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              startIcon={<RestartAlt />}
              onClick={handleReset}
              size="small"
              fullWidth
            >
              Reset
            </Button>
            <Button
              variant="contained"
              onClick={handleApply}
              size="small"
              fullWidth
            >
              Apply
            </Button>
          </Stack>
        </Box>
      </Drawer>
    </>
  );
}
