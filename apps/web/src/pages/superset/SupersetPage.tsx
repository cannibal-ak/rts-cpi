import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Typography, Grid, Card, Button, Avatar, alpha, Theme
} from '@mui/material';
import { OpenInNew, Flight, DirectionsBoat } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import { useSession } from '../../context/SessionContext';
import { DASHBOARD_LAUNCH_LABEL } from '../../constants/ui';

const dashboardPacks = [
  {
    title: 'Airline CPI – JY',
    id: '1',
    icon: <Flight />,
    tenant: 'JY',
  },
  {
    title: 'Airline CPI – PW',
    id: '2',
    icon: <Flight />,
    tenant: 'PW',
  },
  {
    title: 'Cruise/Ferry CPI – FJL',
    id: '3',
    icon: <DirectionsBoat />,
    tenant: 'FJL',
  },
];

export default function SupersetPage() {
  const navigate = useNavigate();
  const { session } = useSession();
  const isAdmin = session.user.roles.includes('TENANT_ADMIN');

  const filteredPacks = dashboardPacks.filter(pack => {
    if (isAdmin) return true;
    
    // User identifier derived from name (e.g., 'Airline_JY' -> 'JY')
    const name = session.user.name || '';
    const userIdentifier = name.includes('_') ? name.split('_')[1].toUpperCase() : name.toUpperCase();
    
    return pack.tenant === userIdentifier;
  });

  return (
    <Box>
      <PageHeader
        title="Dashboards"
        subtitle="Access interactive analytics and trend visualizations"
        breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Dashboards' }]}
      />

      <Grid container spacing={4} sx={{ mb: 6, pt: 2 }}>
        {filteredPacks.map(pack => (
          <Grid item xs={12} sm={6} md={4} key={pack.title}>
            <Card 
              variant="elevation"
              elevation={0}
              onClick={() => navigate(`/dashboards/${pack.id}`)}
              sx={{ 
                height: '100%', 
                display: 'flex', 
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
                p: 4,
                cursor: 'pointer',
                borderRadius: 4,
                border: '1px solid',
                borderColor: 'divider',
                backgroundColor: 'background.paper',
                transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                '&:hover': {
                  transform: 'translateY(-12px)',
                  boxShadow: '0 24px 48px rgba(0,0,0,0.06)',
                  borderColor: 'primary.main',
                  '& .launch-btn': {
                    boxShadow: (theme: Theme) => `0 8px 16px ${alpha(theme.palette.primary.main, 0.3)}`,
                  },
                  '& .icon-avatar': {
                    bgcolor: 'primary.main',
                    color: 'white',
                    transform: 'rotate(5deg) scale(1.1)'
                  }
                }
              }}
            >
              <Avatar 
                className="icon-avatar"
                sx={{ 
                  width: 80, 
                  height: 80, 
                  bgcolor: (theme: Theme) => alpha(theme.palette.primary.main, 0.1), 
                  color: 'primary.main',
                  mb: 4,
                  transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)'
                }}
              >
                {React.cloneElement(pack.icon as React.ReactElement, { sx: { fontSize: 40 } })}
              </Avatar>

              <Typography variant="h6" fontWeight={800} sx={{ mb: 1, px: 2, height: '3.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'text.primary' }}>
                {pack.title}
              </Typography>
              
              <Box sx={{ mt: 4, width: '100%' }}>
                <Button
                  className="launch-btn"
                  variant="contained"
                  fullWidth
                  disableElevation
                  startIcon={<OpenInNew />}
                  sx={{
                    py: 1.5,
                    borderRadius: 3,
                    fontWeight: 700,
                    textTransform: 'none',
                    letterSpacing: 0.5,
                    fontSize: '0.95rem',
                    transition: 'all 0.3s ease',
                  }}
                >
                  {DASHBOARD_LAUNCH_LABEL}
                </Button>
              </Box>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}

