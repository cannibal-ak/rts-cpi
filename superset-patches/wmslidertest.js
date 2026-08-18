/* Verify WM-ZOOM-SLIDER-RED: dash 6 sliders carry the brand-red style. */
const { chromium } = require('playwright-core');
const URL = process.env.TARGET || 'http://localhost:8088/superset/dashboard/6/?standalone=1';
(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 2400 } });
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('[_echarts_instance_]', { timeout: 90000 });
  await page.waitForTimeout(6000);
  const res = await page.evaluate(() => {
    const out = [];
    const isEc = o => o && typeof o === 'object' && typeof o.dispatchAction === 'function' && typeof o.getOption === 'function';
    document.querySelectorAll('[_echarts_instance_]').forEach(el => {
      const fiberKey = Object.keys(el).find(k => k.startsWith('__reactInternalInstance$'));
      let ec = null;
      for (let f = el[fiberKey]; f && !ec; f = f.return) {
        let hook = f.memoizedState, hops = 0;
        while (hook && typeof hook === 'object' && 'memoizedState' in hook && hops < 60) {
          const v = hook.memoizedState;
          if (v && isEc(v.current)) { ec = v.current; break; }
          if (isEc(v)) { ec = v; break; }
          hook = hook.next; hops++;
        }
      }
      if (!ec) return;
      (ec.getOption().dataZoom || []).filter(d => d.type === 'slider').forEach(d =>
        out.push({ filler: d.fillerColor || null, handle: (d.handleStyle && d.handleStyle.color) || null }));
    });
    return { path: location.pathname, sliderCount: out.length, sliders: out };
  });
  console.log(JSON.stringify(res));
  await browser.close();
})().catch(e => { console.error('FAIL', e.message); process.exit(1); });
