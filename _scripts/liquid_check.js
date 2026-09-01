// Register Jekyll-specific tags (seo, jsonify, etc) as no-ops for syntax validation
const { Liquid, Tag, TagToken } = require('liquidjs');

class SeoTag extends Tag {
  render() { return ''; }
}

const engine = new Liquid({
  strictFilters: false,
  strictVariables: false,
});
engine.registerTag('seo', { render: () => '' });

const fs = require('fs');
const path = require('path');

const site = {
  posts: [],
  recipes: [],
  ingredients: [],
  pages: [],
  url: 'https://healthy-recipes.pages.dev',
  baseurl: '',
  title: 'Healthy Western Recipes',
  description: 'Low-calorie Mediterranean recipes',
  lang: 'en',
  twitter: { username: 'healthyrecipes' },
  time: new Date(),
  data: {},
};

function readFile(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const fmMatch = raw.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (!fmMatch) return { fm: {}, body: raw };
  const fm = {};
  const lines = fmMatch[1].split('\n');
  for (const line of lines) {
    if (line.match(/^[a-zA-Z_]+:/)) {
      const [k, v] = line.split(':', 2);
      fm[k.trim()] = v.trim().replace(/^["']|["']$/g, '');
    }
  }
  return { fm, body: fmMatch[2] };
}

const files = [
  'index.html', 'recipes.html', 'ingredients.html', 'about.md',
  'editorial-policy.md', 'ai-disclosure.md',
  '_layouts/default.html', '_layouts/recipe.html', '_layouts/ingredient_page.html',
  '_recipes/2026-08-27-one-pot-parmesan-chicken-white-beans.md',
  '_recipes/2026-08-28-italian-chicken-soup-lemon-caper.md',
  '_recipes/2026-08-29-garlic-chicken-broccoli-stir-fry.md',
  '_recipes/2026-08-30-lemon-herb-roasted-chicken-breast.md',
  '_recipes/2026-08-31-lemon-dill-white-fish-soup.md',
  '_ingredients/chicken-breast.md',
];

let errs = 0;
const promises = [];
for (const f of files) {
  const filePath = path.join(process.cwd(), f);
  if (!fs.existsSync(filePath)) { continue; }
  const { fm, body } = readFile(filePath);
  const ctx = {
    page: { ...fm, content: body, url: '/' + f.replace(/\.(md|html)$/, '/'), layout: fm.layout || 'default' },
    site,
  };
  promises.push(
    engine.parseAndRender(body, ctx).then(() => console.log(`OK  ${f}`))
    .catch(err => { console.log(`ERR ${f}\n  ${err.message}`); errs++; })
  );
}

Promise.all(promises).then(() => process.exit(errs > 0 ? 1 : 0));