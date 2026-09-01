// Scan all files for Jekyll-specific filters and syntax that liquidjs doesn't validate
const fs = require('fs');
const path = require('path');
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

// Jekyll/Liquid filters that liquidjs doesn't natively support
const jekyllFilters = [
  'markdownify', 'jsonify', 'date_to_xmlschema', 'date_to_string',
  'absolute_url', 'relative_url', 'slugify', 'group_by', 'where_exp',
  'number_of_words', 'where', 'sort_natural', 'escape',
];

const allFilterRegex = /\|\s*(\w+)/g;

for (const f of files) {
  const fp = path.join(process.cwd(), f);
  if (!fs.existsSync(fp)) continue;
  const content = fs.readFileSync(fp, 'utf8');
  const filters = [];
  let m;
  while ((m = allFilterRegex.exec(content))) {
    filters.push(m[1]);
  }
  const unique = [...new Set(filters)];
  const jekyll = unique.filter(x => jekyllFilters.includes(x));
  if (jekyll.length > 0) {
    console.log(`${f}: jekyll filters: ${jekyll.join(', ')}`);
  }
}