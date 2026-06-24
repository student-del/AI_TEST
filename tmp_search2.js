const fs = require('fs');
const c = fs.readFileSync('C:/Users/juwei/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/cli.js','utf8');

const terms = ['contextCollapseCommit','drain','snapshot','replay','compact_boundary','contextCollapse','commit_threshold','collapse_commit'];
terms.forEach(t => {
  let count = 0;
  let idx = 0;
  while ((idx = c.indexOf(t, idx)) !== -1 && count < 3) {
    const start = Math.max(0, idx - 30);
    const end = Math.min(c.length, idx + 400);
    console.log('=== ' + t + ' #' + (count+1) + ' ===');
    console.log(c.slice(start, end));
    console.log();
    idx += t.length + 100;
    count++;
  }
  if (count === 0) console.log('=== ' + t + ': not found ===\n');
});
