---
title: "Healthy Christmas Recipes: Festive Mains & Sides Under 600 Calories"
layout: pillar
permalink: /healthy-christmas-dinner/
pillar: christmas
season: "November–December"
description: "Lightened-up Christmas dinner recipes — roast mains, seasonal sides and make-ahead soups, all under 600 kcal with 15g+ protein per serving. A festive plate that doesn't need a January apology."
keywords: ["healthy christmas recipes", "low calorie christmas dinner", "healthy christmas mains", "light christmas sides", "healthy holiday recipes under 600 calories", "high protein christmas dinner"]
---

## The healthy Christmas plate

A traditional Christmas dinner — roast with all the trimmings, gravy, pudding — can quietly pass 2,500 calories in a single sitting. You don't have to skip the feast to stay on track: build the plate around **a lean roasted main and two vegetable-forward sides**, keep the rich classics to tasting portions, and the whole plate lands between **700 and 900 calories** with more protein and fiber than the standard spread.

Every recipe below follows the Waimind standard: **400–600 kcal per serving and at least 15 g of protein**, so a main plus two sides stays firmly in control while still tasting like Christmas.

## Roast mains that carry the table

Lean proteins roasted with herbs do the heavy lifting — these mains come in at 400–600 kcal per serving with 30 g+ protein:

<ul>
{%- assign mains = site.recipes | where: 'category', 'Main' | where_exp: 'r', 'r.title contains "Roast" or r.title contains "Braised" or r.title contains "Turkey" or r.title contains "Lamb"' -%}
{%- for r in mains limit: 12 -%}
<li><a href="{{ r.url | relative_url }}">{{ r.title }}</a> — {{ r.calories }} kcal, {{ r.protein }}g protein, {{ r.total_time }} min</li>
{%- endfor -%}
</ul>

Roast timing is the only real stress on Christmas Day. Take the joint out of the fridge an hour before roasting, rest it 20 minutes before carving, and use the resting juices to finish the pan vegetables — flavour without extra fat.

## Lighter sides under 300 kcal

Vegetable-forward sides keep the plate balanced. Roasted greens, braised beans and fresh salads do the refreshing work between the rich bites:

<ul>
{%- assign sides = site.recipes | where: 'category', 'Side' -%}
{%- assign salads = site.recipes | where: 'category', 'Salad' -%}
{%- for r in sides -%}
<li><a href="{{ r.url | relative_url }}">{{ r.title }}</a> — {{ r.calories }} kcal, {{ r.protein }}g protein</li>
{%- endfor -%}
{%- for r in salads -%}
<li><a href="{{ r.url | relative_url }}">{{ r.title }}</a> — {{ r.calories }} kcal, {{ r.protein }}g protein</li>
{%- endfor -%}
</ul>

## Starters and soups you can make ahead

Christmas morning belongs to the oven, not the stove. These soups improve overnight and reheat in minutes:

<ul>
{%- assign soups = site.recipes | where: 'category', 'Soup' -%}
{%- for r in soups limit: 10 -%}
<li><a href="{{ r.url | relative_url }}">{{ r.title }}</a> — {{ r.calories }} kcal, {{ r.protein }}g protein, {{ r.total_time }} min</li>
{%- endfor -%}
</ul>

## Three swaps that save 800 calories

1. **Roast potatoes → roasted root vegetables.** Cube celeriac, carrots and parsnips, toss in olive oil instead of dripping, roast at high heat. Same crunch, a fraction of the fat.
2. **Bread sauce → Greek yogurt herb sauce.** Strained yogurt with garlic and lemon does everything bread sauce does for a roast, with protein instead of starch.
3. **Pudding → poached fruit and yogurt.** Keep the pudding for the table, but plate a poached pear with spiced yogurt as your own dessert — nobody notices, and you stay in range.

## Plan the day like a pro

- **Christmas Eve:** make the soup and any braised sides. Both improve overnight.
- **Christmas morning:** vegetables prepped, joint out of the fridge, table set by 11:00.
- **One hour before:** roast in, sides in behind it, sauces assembled cold.
- **Twenty minutes before:** rest the joint, finish the pans, warm the soup.

The result: a full festive plate around **750 kcal** with 50 g+ protein — and no January regret.

Browse every recipe on the site in the [full recipe index]({{ '/recipes/' | relative_url }}), or start with the [Mediterranean favourites]({{ '/cuisines/' | relative_url }}) that inspired this collection.
