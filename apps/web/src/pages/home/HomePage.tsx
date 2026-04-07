import React, { useState, useEffect } from 'react';
import { Box, Grid, Typography, Button, Card, CardContent, CardActions, CircularProgress } from '@mui/material';
import { Flight, DirectionsBoat, TrendingUp, ArrowForward } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import DataFreshnessIndicator from '../../components/common/DataFreshnessIndicator';
import { api } from '../../api';
import { DataFreshness } from '../../types';
import { DASHBOARD_LAUNCH_LABEL } from '../../constants/ui';

export default function HomePage() {
  const { session, hasModule } = useSession();
  const navigate = useNavigate();
  const [freshness, setFreshness] = useState<DataFreshness[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadFreshness() {
      try {
        const data = await api.stats.getFreshnessMetrics();
        setFreshness(data);
      } catch (err) {
        console.error('Failed to load freshness metrics:', err);
      } finally {
        setLoading(false);
      }
    }
    loadFreshness();
  }, []);

  return (
    <Box>
      <Box sx={{ mb: 4, display: 'flex', alignItems: 'center', gap: 2 }}>
        <Box
          component="img"
          src="/assets/RTS_Logo.png"
          alt="RTS Logo"
          onError={(e: React.SyntheticEvent<HTMLImageElement>) => {
            const img = e.currentTarget;
            if (img.src.endsWith('.png')) {
              img.src = '/assets/RTS_Logo.svg';
            } else {
              img.style.display = 'none';
            }
          }}
          sx={{ height: 72 }}
        />
        <Box>
          <Typography variant="h4" fontWeight={700}>
            Competitor Pricing Intelligence
          </Typography>
          <Typography variant="subtitle1" color="text.secondary" sx={{ mt: 0.5 }}>
            Welcome back, {session.user.name.split(' ')[0]}  |  {session.tenant_name}
          </Typography>
        </Box>
      </Box>

      {/* Data Freshness / System Status Overview */}
      <Typography variant="subtitle2" sx={{ mb: 1, color: 'text.secondary' }}>
        System Status Overview
      </Typography>
      <Box sx={{ mb: 4 }}>
        {loading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', minHeight: 100 }}>
             <CircularProgress size={24} sx={{ ml: 2 }} />
          </Box>
        ) : (
          <Grid container spacing={2}>
            {freshness.map((df: DataFreshness) => (
              <Grid item xs={12} sm={6} md={4} key={df.domain}>
                <DataFreshnessIndicator data={df} />
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      {/* Quick Access Cards */}
      <Typography variant="subtitle2" sx={{ mb: 1, color: 'text.secondary' }}>Quick Access</Typography>
      <Grid container spacing={2} sx={{ mb: 4 }}>
        {hasModule(['airline_jy']) && (
          <Grid item xs={12} sm={6} md={4}>
            <Card variant="outlined" sx={{ height: '100%', cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }} onClick={() => navigate('/cpi/airline/jy')}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Flight color="primary" />
                  <Typography variant="h6">Airline CPI – JY</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary">
                  Compare fares, routes, and availability for JY airline data. Analyze pricing trends and monitor market positioning.
                </Typography>
              </CardContent>
              <CardActions>
                <Button size="small" endIcon={<ArrowForward />}>Open Module</Button>
              </CardActions>
            </Card>
          </Grid>
        )}
        {hasModule(['airline_pw']) && (
          <Grid item xs={12} sm={6} md={4}>
            <Card variant="outlined" sx={{ height: '100%', cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }} onClick={() => navigate('/cpi/airline/pw')}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Flight color="primary" />
                  <Typography variant="h6">Airline CPI – PW</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary">
                  Access PW airline pricing intelligence. Monitor competitor fares and route availability across the PW network.
                </Typography>
              </CardContent>
              <CardActions>
                <Button size="small" endIcon={<ArrowForward />}>Open Module</Button>
              </CardActions>
            </Card>
          </Grid>
        )}
        {hasModule(['cfl_fjl']) && (
          <Grid item xs={12} sm={6} md={4}>
            <Card variant="outlined" sx={{ height: '100%', cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }} onClick={() => navigate('/cpi/cruise/fjl')}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <DirectionsBoat color="primary" />
                  <Typography variant="h6">Cruise/Ferry CPI – FJL</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary">
                  Monitor FJL cruise and ferry pricing. Track vehicle and passenger fares across routes and equipment types.
                </Typography>
              </CardContent>
              <CardActions>
                <Button size="small" endIcon={<ArrowForward />}>Open Module</Button>
              </CardActions>
            </Card>
          </Grid>
        )}
        <Grid item xs={12} sm={6} md={4}>
          <Card variant="outlined" sx={{ height: '100%', cursor: 'pointer', '&:hover': { borderColor: 'primary.main' } }} onClick={() => navigate('/dashboards')}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <TrendingUp color="primary" />
                <Typography variant="h6">Analytics Dashboards</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Access interactive analytics dashboards. Explore trends, drill down into data, and build custom visualizations.
              </Typography>
            </CardContent>
            <CardActions>
              <Button size="small" endIcon={<ArrowForward />}>{DASHBOARD_LAUNCH_LABEL}</Button>
            </CardActions>
          </Card>
        </Grid>
      </Grid>

    </Box>
  );
}
