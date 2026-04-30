import React, { useState, useEffect } from 'react';
import { Box, Grid, Typography, CircularProgress } from '@mui/material';
import { useSession } from '../../context/SessionContext';
import DataFreshnessIndicator from '../../components/common/DataFreshnessIndicator';
import { api } from '../../api';
import { DataFreshness } from '../../types';

export default function HomePage() {
  const { session } = useSession();
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



    </Box>
  );
}
