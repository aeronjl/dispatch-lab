const {test,expect}=require('@playwright/test');
test('autonomous service assumptions are explicit, resettable and invalidate a reviewed preview',async({page})=>{
 await page.goto('/');await page.locator('.m-plant').waitFor();
 await page.getByRole('button',{name:'Simulation menu',exact:true}).click();await page.locator('[data-do=studies]').click();await page.locator('[data-u=open]').click();await page.locator('[data-u=clear]').click();
 const packets=[];page.on('request',r=>{if(r.url().endsWith('/dispatch/studies'))packets.push(r.postDataJSON());});
 await page.locator('[data-u=autonomy]').selectOption('risk-aware');await page.locator('[data-u=preview]').click();
 await expect.poll(()=>packets.some(p=>p.operation==='uncertainty-preview')).toBeTruthy();
 const sent=packets.find(p=>p.operation==='uncertainty-preview');expect(sent.uncertainty.autonomy.mode).toBe('risk-aware');expect(sent.uncertainty.autonomy.duration_bounds.cleaning).toEqual([.5,2]);expect(sent.uncertainty.autonomy.source).toContain('no site calibration');
 await page.locator('[data-u=autonomy]').selectOption('fixed');await expect(page.locator('[data-u=start]')).toBeDisabled();
 await page.locator('[data-u=autonomy]').selectOption('off');await expect(page.locator('[data-u=autonomy]')).toHaveValue('off');await page.setViewportSize({width:390,height:844});expect(await page.locator('.st-workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1)).toBeTruthy();await page.keyboard.press('Escape');
});
