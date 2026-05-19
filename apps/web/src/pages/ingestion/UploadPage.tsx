import React, { useState, useRef } from 'react';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, IconButton,
  CircularProgress, Divider, List, ListItem, ListItemText, ListItemIcon, Tooltip,
} from '@mui/material';
import {
  CloudUpload, InsertDriveFile, Close, CheckCircle, Warning, ErrorOutline,
  ContentCopy, ArrowForward,
} from '@mui/icons-material';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import PageHeader from '../../components/common/PageHeader';
import { api } from '../../api';
import { useSession } from '../../context/SessionContext';
import { isSuperAdmin } from '../../utils/access';
import type { IngestionUploadResponse } from '../../types';

const FILENAME_EXAMPLES = [
  { tenant: 'JY', domain: 'AIRLINE', pattern: 'JY_DDMMYY.xlsx', example: 'JY_010426.xlsx' },
  { tenant: 'JY', domain: 'VELOCITY', pattern: 'JYVelocityData_DD.MM.YYYY.csv', example: 'JYVelocityData_01.04.2026.csv' },
  { tenant: 'PW', domain: 'AIRLINE', pattern: 'PW_DDMMYY.csv', example: 'PW_010426.csv' },
  { tenant: 'PW', domain: 'VELOCITY', pattern: 'PWVelocityData_DD.MM.YYYY.csv', example: 'PWVelocityData_01.04.2026.csv' },
  { tenant: 'FJL', domain: 'CFL', pattern: 'FJL_DDMMYY.csv', example: 'FJL_010426.csv' },
];

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_FILES = 20;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadPage() {
  const { session } = useSession();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<IngestionUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isSuperAdmin(session)) {
    return (
      <Box>
        <PageHeader
          title="Upload Files"
          breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Ingestion Jobs', href: '/ingestion' }, { label: 'Upload' }]}
        />
        <Alert severity="warning" sx={{ mt: 2 }}>
          RTS platform admin access required. The upload pipeline is restricted to platform administrators.
        </Alert>
      </Box>
    );
  }

  const addFiles = (newOnes: File[]) => {
    setError(null);
    const tooBig = newOnes.filter(f => f.size > MAX_FILE_BYTES);
    if (tooBig.length > 0) {
      setError(`${tooBig.length} file(s) exceed the 50 MB limit and were skipped: ${tooBig.map(f => f.name).join(', ')}`);
    }
    const accepted = newOnes.filter(f => f.size <= MAX_FILE_BYTES);
    setFiles(prev => {
      const map = new Map(prev.map(f => [`${f.name}::${f.size}`, f]));
      accepted.forEach(f => map.set(`${f.name}::${f.size}`, f));
      const combined = Array.from(map.values()).slice(0, MAX_FILES);
      if (Array.from(map.values()).length > MAX_FILES) {
        setError(`Limit is ${MAX_FILES} files per request; extra files were trimmed.`);
      }
      return combined;
    });
  };

  const removeFile = (idx: number) => {
    setFiles(prev => prev.filter((_, i) => i !== idx));
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = Array.from(e.dataTransfer.files);
    if (dropped.length) addFiles(dropped);
  };

  const onPickFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(Array.from(e.target.files));
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const triggerPicker = () => fileInputRef.current?.click();

  const upload = async () => {
    setUploading(true);
    setError(null);
    setResults(null);
    try {
      const r = await api.ingestion.upload(files);
      setResults(r);
      setFiles([]);
    } catch (e: any) {
      setError(e.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Box>
      <PageHeader
        title="Upload Files"
        subtitle="Stage one or more files; validate and commit on the Jobs page"
        breadcrumbs={[
          { label: 'Home', href: '/' },
          { label: 'Ingestion Jobs', href: '/ingestion' },
          { label: 'Upload' },
        ]}
        actions={
          <Button
            size="small"
            variant="outlined"
            component={RouterLink}
            to="/ingestion"
            startIcon={<ArrowForward />}
          >
            Go to Jobs
          </Button>
        }
      />

      {/* Drop zone */}
      <Paper
        variant="outlined"
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        sx={{
          mt: 2,
          p: 6,
          textAlign: 'center',
          borderStyle: 'dashed',
          borderWidth: 2,
          borderColor: dragOver ? 'primary.main' : 'divider',
          bgcolor: dragOver ? 'action.hover' : 'background.paper',
          transition: 'all 0.15s ease-in-out',
          cursor: 'pointer',
        }}
        onClick={triggerPicker}
        role="button"
        aria-label="File drop zone — click or drag files here"
      >
        <CloudUpload sx={{ fontSize: 64, color: dragOver ? 'primary.main' : 'text.secondary', mb: 1 }} />
        <Typography variant="h6" sx={{ mb: 0.5 }}>
          {dragOver ? 'Drop files to add' : 'Drag & drop files here'}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          or <Typography component="span" color="primary.main" sx={{ textDecoration: 'underline' }}>click to browse</Typography>
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Up to {MAX_FILES} files per request · max 50 MB each · .csv or .xlsx
        </Typography>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".csv,.xlsx"
          style={{ display: 'none' }}
          onChange={onPickFiles}
          aria-hidden="true"
        />
      </Paper>

      {error && (
        <Alert severity="warning" sx={{ mt: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Selected files (pre-upload) */}
      {files.length > 0 && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="subtitle2">Selected files ({files.length})</Typography>
            <Stack direction="row" spacing={1}>
              <Button size="small" variant="text" onClick={() => setFiles([])} disabled={uploading}>
                Clear
              </Button>
              <Button
                size="small"
                variant="contained"
                startIcon={uploading ? <CircularProgress size={14} color="inherit" /> : <CloudUpload />}
                onClick={upload}
                disabled={uploading || files.length === 0}
              >
                {uploading ? 'Uploading…' : `Upload ${files.length} file${files.length > 1 ? 's' : ''}`}
              </Button>
            </Stack>
          </Stack>
          <List dense>
            {files.map((f, idx) => (
              <ListItem
                key={`${f.name}-${idx}`}
                secondaryAction={
                  <IconButton edge="end" size="small" onClick={() => removeFile(idx)} disabled={uploading} aria-label="Remove file">
                    <Close fontSize="small" />
                  </IconButton>
                }
              >
                <ListItemIcon><InsertDriveFile fontSize="small" color="action" /></ListItemIcon>
                <ListItemText
                  primary={f.name}
                  secondary={formatBytes(f.size)}
                  primaryTypographyProps={{ variant: 'body2', fontFamily: 'monospace' }}
                />
              </ListItem>
            ))}
          </List>
        </Paper>
      )}

      {/* Results panel */}
      {results && (
        <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Upload results</Typography>
          <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
            <Chip label={`Accepted: ${results.summary.accepted}`} color="success" size="small" />
            <Chip label={`Duplicate: ${results.summary.duplicate}`} color="default" size="small" />
            <Chip label={`Conflict: ${results.summary.conflict}`} color="warning" size="small" />
            <Chip label={`Rejected: ${results.summary.rejected}`} color="error" size="small" />
          </Stack>
          <Divider sx={{ mb: 1 }} />
          <List dense>
            {results.files.map((r, idx) => {
              const status = r.duplicate ? 'duplicate' : r.conflict ? 'conflict' : r.error_code ? 'rejected' : 'accepted';
              const icon =
                status === 'accepted' ? <CheckCircle color="success" fontSize="small" /> :
                status === 'duplicate' ? <ContentCopy color="action" fontSize="small" /> :
                status === 'conflict' ? <Warning color="warning" fontSize="small" /> :
                <ErrorOutline color="error" fontSize="small" />;
              return (
                <ListItem key={idx} alignItems="flex-start">
                  <ListItemIcon sx={{ mt: 0.5 }}>{icon}</ListItemIcon>
                  <ListItemText
                    primary={
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" fontWeight={600} fontFamily="monospace">{r.filename}</Typography>
                        <Chip label={status} size="small" />
                        {r.job?.tenant_code && <Chip label={r.job.tenant_code} size="small" variant="outlined" />}
                        {r.job?.domain && <Chip label={r.job.domain} size="small" variant="outlined" />}
                      </Stack>
                    }
                    secondary={
                      <Stack spacing={0.25} sx={{ mt: 0.5 }}>
                        {r.job && (
                          <Typography variant="caption" color="text.secondary">
                            job <Typography component="span" fontFamily="monospace" variant="caption">{r.job.id.slice(0, 8)}…</Typography>
                            {' '}· file_date {r.job.file_date} · {formatBytes(r.job.file_size_bytes)}
                          </Typography>
                        )}
                        {r.duplicate && r.existing_job_id && (
                          <Typography variant="caption" color="text.secondary">
                            Already committed as job <Typography component="span" fontFamily="monospace" variant="caption">{r.existing_job_id.slice(0, 8)}…</Typography>
                          </Typography>
                        )}
                        {r.conflict && r.existing_job_id && (
                          <Typography variant="caption" color="warning.main">
                            A different file was already committed for this date — existing job <Typography component="span" fontFamily="monospace" variant="caption">{r.existing_job_id.slice(0, 8)}…</Typography>. Use “replace existing” on commit (next phase).
                          </Typography>
                        )}
                        {r.error_message && (
                          <Typography variant="caption" color="error.main">{r.error_message}</Typography>
                        )}
                      </Stack>
                    }
                  />
                </ListItem>
              );
            })}
          </List>
          {results.summary.accepted > 0 && (
            <Alert severity="success" sx={{ mt: 2 }} action={
              <Button color="inherit" size="small" onClick={() => navigate('/ingestion')}>
                View Jobs
              </Button>
            }>
              {results.summary.accepted} file{results.summary.accepted > 1 ? 's' : ''} staged. Validate and commit from the Jobs page (or wait for the validate/commit buttons in the next phase).
            </Alert>
          )}
        </Paper>
      )}

      {/* Filename helper */}
      <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Filename conventions</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
          The server parses tenant, domain, and file_date from the filename. Files outside these patterns are rejected with an explicit reason.
        </Typography>
        <List dense>
          {FILENAME_EXAMPLES.map(ex => (
            <ListItem key={`${ex.tenant}-${ex.domain}`} sx={{ py: 0.25 }}>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ width: '100%' }}>
                <Chip label={ex.tenant} size="small" variant="outlined" sx={{ minWidth: 48 }} />
                <Chip label={ex.domain} size="small" variant="outlined" sx={{ minWidth: 84 }} />
                <Typography variant="body2" fontFamily="monospace">{ex.pattern}</Typography>
                <Typography variant="caption" color="text.secondary">e.g. {ex.example}</Typography>
              </Stack>
            </ListItem>
          ))}
        </List>
      </Paper>
    </Box>
  );
}
