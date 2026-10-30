"""Temporal input and baseline checks; no model fitting or test-set tuning."""
import sys,unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'model'))
from train import observations
from train_dfld import rule_predictions

class TemporalInputs(unittest.TestCase):
 def test_origin_metar_and_trends(self):
  obs,_=observations();eligible=obs[['east','north','gust','eastTrend3h','northTrend3h']].notna().all(axis=1)
  times=obs.index[eligible];actual=pd.to_datetime(obs.loc[eligible,'valid'],utc=True)
  self.assertTrue(((times-actual)>=pd.Timedelta(0)).all())
  self.assertTrue(((times-actual)<=pd.Timedelta(minutes=40)).all())
  self.assertTrue(obs.loc[obs.drct.isna(),'east'].isna().all())
  np.testing.assert_allclose(obs.eastTrend3h,obs.east-obs.east.shift(3),equal_nan=True)
 def test_rules_start_at_first_future_hour(self):
  times=pd.date_range('2026-10-01T00:00Z',periods=4,freq='h')
  # Small adverse wind must persist >30 min; origin must not count as future step.
  nwp=pd.DataFrame({'wind_speed_10m_previous_day1':[3]*4,'wind_direction_10m_previous_day1':[70]*4},index=times)
  p,missing=rule_predictions(nwp,times[1:2],np.array([0]),1,1);self.assertEqual(p[0],0);self.assertFalse(missing[0])
  p,missing=rule_predictions(nwp,times[2:3],np.array([0]),2,1);self.assertEqual(p[0],1)
  nwp.loc[times[1],'wind_speed_10m_previous_day1']=np.nan
  _,missing=rule_predictions(nwp,times[2:3],np.array([0]),2,1);self.assertTrue(missing[0])

if __name__=='__main__':unittest.main()
