/* Headless verification of the Superset zoom fixes (dev).
 * 1. Legend strip pushed left (legendTopRightOffset 115) so toolbox icons are clear.
 * 2. Faithful icon click + drag zooms.
 * 3. Zoom survives a Superset notMerge setOption re-render (patched wrapper).
 * 4. Restore icon resets.
 */
const { chromium } = require('playwright-core');

const URL = 'http://localhost:8088/explore/?slice_id=43&standalone=1';

(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1600, height: 800 } });
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('[_echarts_instance_]', { timeout: 90000 });
  await page.waitForTimeout(3000); // let data + layout settle

  const result = await page.evaluate(async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const el = document.querySelector('[_echarts_instance_]');
    const fiberKey = Object.keys(el).find(k => k.startsWith('__reactInternalInstance$'));
    const isEc = o => o && typeof o === 'object' && typeof o.dispatchAction === 'function' && typeof o.getOption === 'function';
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
    if (!ec) return { error: 'no echarts instance' };

    const zr = ec.getZr();
    const canvas = zr.dom.querySelector('canvas');
    const rect = canvas.getBoundingClientRect();
    const W = ec.getWidth();
    const fire = (type, x, y) => canvas.dispatchEvent(new MouseEvent(type, {
      bubbles: true, cancelable: true,
      clientX: rect.left + x, clientY: rect.top + y,
      button: 0, buttons: (type === 'mouseup' || type === 'click') ? 0 : 1,
    }));
    const dz = () => {
      const d = ec.getOption().dataZoom[0];
      return { start: +(+d.start).toFixed(1), end: +(+d.end).toFixed(1) };
    };

    // instrument setOption to prove a re-render actually happens in step 3
    let setOptCount = 0;
    const origSetOption = ec.setOption.bind(ec);
    ec.setOption = (...a) => { setOptCount++; return origSetOption(...a); };

    // ---- geometry: legend right edge vs toolbox icons ----
    const views = ec._componentsViews || [];
    const byType = t => views.find(v => v.__model && (v.__model.mainType === t || v.__model.type === t));
    const groupRect = v => { const r = v.group.getBoundingRect().clone(); if (v.group.transform) r.applyTransform(v.group.transform); return r; };
    const lgV = byType('legend');
    const tbV = byType('toolbox');
    const lgR = groupRect(lgV);
    const icons = [];
    (function walk(g) { (g._children || []).forEach(ch => { if (ch.isGroup) walk(ch); else if (ch.type === 'path') { const m = ch.getComputedTransform ? ch.getComputedTransform() : null; const r = ch.getBoundingRect().clone(); if (m) r.applyTransform(m); icons.push({ x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) }); } }); })(tbV.group);
    const geometry = {
      canvasW: W,
      legendRightEdge: Math.round(lgR.x + lgR.width),
      legendGapFromRight: Math.round(W - (lgR.x + lgR.width)),
      toolboxIcons: icons,
    };

    // ---- test 1: faithful icon click + drag ----
    const zoomIcon = icons[0], restoreIcon = icons[1];
    const before = dz();
    fire('mousemove', zoomIcon.x, zoomIcon.y);
    fire('mousedown', zoomIcon.x, zoomIcon.y);
    fire('mouseup', zoomIcon.x, zoomIcon.y);
    fire('click', zoomIcon.x, zoomIcon.y);
    await sleep(300);
    fire('mousemove', 600, 400);
    const cursorAfterIcon = canvas.parentElement.style.cursor || 'unset';
    fire('mousedown', 500, 400);
    for (let x = 540; x <= 900; x += 40) fire('mousemove', x, 400);
    fire('mouseup', 900, 400);
    await sleep(400);
    const afterDrag = dz();

    // ---- test 2: zoom survives a Superset re-render (legend item toggle) ----
    // find a legend item (rect with click handler on its parent group) and click it twice
    let legendItem = null;
    (function walk(g) { (g._children || []).forEach(ch => { if (legendItem) return; if (ch.isGroup) walk(ch); else if (ch.type === 'rect' && ch.parent && ch.parent._$handlers && ch.parent._$handlers.click) { const m = ch.getComputedTransform ? ch.getComputedTransform() : null; const r = ch.getBoundingRect().clone(); if (m) r.applyTransform(m); if (r.width < 200) legendItem = { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) }; } }); })(lgV.group);
    let survivedRerender = null, setOptDuringToggle = 0, afterToggle = null;
    if (legendItem) {
      const c0 = setOptCount;
      fire('mousemove', legendItem.x, legendItem.y);
      fire('mousedown', legendItem.x, legendItem.y);
      fire('mouseup', legendItem.x, legendItem.y);
      fire('click', legendItem.x, legendItem.y);
      await sleep(1500);
      // toggle back
      fire('mousedown', legendItem.x, legendItem.y);
      fire('mouseup', legendItem.x, legendItem.y);
      fire('click', legendItem.x, legendItem.y);
      await sleep(1500);
      setOptDuringToggle = setOptCount - c0;
      afterToggle = dz();
      survivedRerender = setOptDuringToggle > 0
        ? (Math.abs(afterToggle.start - afterDrag.start) < 2 && Math.abs(afterToggle.end - afterDrag.end) < 2)
        : 'no-rerender-triggered';
    }

    // ---- test 3: restore icon ----
    fire('mousemove', restoreIcon.x, restoreIcon.y);
    fire('mousedown', restoreIcon.x, restoreIcon.y);
    fire('mouseup', restoreIcon.x, restoreIcon.y);
    fire('click', restoreIcon.x, restoreIcon.y);
    await sleep(400);
    const afterRestore = dz();

    return { geometry, before, cursorAfterIcon, afterDrag, legendItem, setOptDuringToggle, afterToggle, survivedRerender, afterRestore };
  });

  console.log(JSON.stringify(result, null, 2));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
