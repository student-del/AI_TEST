const c=require('fs').readFileSync('C:/Users/juwei/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/cli.js','utf8');

const pats = ['fresh','frozen','mustReapply','persistedOutput','persisted-output','toolResultBudget',
              'DEFAULT_MAX_RESULT','freeze','outcome:','MAX_TOOL_RESULTS'];

pats.forEach(p=>{
  const re = new RegExp('.{0,250}' + p.replace(/[.*+?^${}()|[\]\\\/]/g, '\\$&') + '.{0,250}', 'gi');
  const matches = c.match(re) || [];
  console.log('=== ' + p + ' (' + matches.length + ' matches) ===');
  matches.slice(0, 2).forEach(m => console.log(m.slice(0, 400) + '\n'));
});
