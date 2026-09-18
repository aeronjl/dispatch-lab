const {test}=require('node:test');
const assert=require('node:assert/strict');
const {workflowMatches,workspaceReturnLabel}=require('../assets/workflow.js');
test('tool discovery requires all entered words and handles empty or mixed-case search',()=>{
 assert.equal(workflowMatches('Saved Weather Sources','weather sources'),true);
 assert.equal(workflowMatches('Saved Weather Sources','  WEATHER   '),true);
 assert.equal(workflowMatches('Saved Weather Sources','weather prices'),false);
 assert.equal(workflowMatches('Model',''),true);
});
test('return wording follows the originating context instead of claiming a simulation return',()=>{
 const inWorkspace=selector=>({closest:s=>s===selector?{}:null});
 assert.equal(workspaceReturnLabel(inWorkspace('.pj-workspace')),'Back to project');
 assert.equal(workspaceReturnLabel(inWorkspace('.iv-workspace')),'Back to investigation');
 assert.equal(workspaceReturnLabel(null),'Back to simulation');
});
