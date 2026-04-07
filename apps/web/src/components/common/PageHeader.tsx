import React from 'react';
import { Box, Typography, Breadcrumbs, Link } from '@mui/material';
import { NavigateNext } from '@mui/icons-material';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  breadcrumbs?: { label: string; href?: string }[];
  actions?: React.ReactNode;
}

export default function PageHeader({ title, subtitle, breadcrumbs, actions }: PageHeaderProps) {
  return (
    <Box sx={{ mb: 3 }}>
      {breadcrumbs && (
        <Breadcrumbs separator={<NavigateNext fontSize="small" />} sx={{ mb: 1 }}>
          {breadcrumbs.map((bc, i) =>
            bc.href ? (
              <Link key={i} underline="hover" color="inherit" href={bc.href} sx={{ fontSize: 13 }}>{bc.label}</Link>
            ) : (
              <Typography key={i} color="text.primary" sx={{ fontSize: 13 }}>{bc.label}</Typography>
            )
          )}
        </Breadcrumbs>
      )}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
        <Box>
          <Typography variant="h5">{title}</Typography>
          {subtitle && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{subtitle}</Typography>}
        </Box>
        {actions && <Box sx={{ display: 'flex', gap: 1 }}>{actions}</Box>}
      </Box>
    </Box>
  );
}
