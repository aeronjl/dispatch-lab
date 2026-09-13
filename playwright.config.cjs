const {defineConfig}=require('@playwright/test');
module.exports=defineConfig({
  testDir:'tests/browser',testMatch:'*.spec.cjs',workers:1,timeout:60000,
  snapshotPathTemplate:'{testDir}/snapshots/{arg}{ext}',
  use:{baseURL:process.env.DISPATCH_TEST_URL||'http://127.0.0.1:7861',viewport:{width:1440,height:1000},reducedMotion:'reduce',trace:'retain-on-failure'},
  reporter:[['list'],['json',{outputFile:'build/engineering/browser-tests.json'}]],
  webServer:process.env.DISPATCH_TEST_URL?undefined:{command:'.venv/bin/python tests/browser/server.py',url:'http://127.0.0.1:7861',reuseExistingServer:!process.env.CI,timeout:120000},
});
