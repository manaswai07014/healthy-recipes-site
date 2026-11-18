---
title: "Healthy Thanksgiving Recipes: Light Sides & Mains Under 600 Calories"
layout: pillar
permalink: /healthy-thanksgiving/
pillar: thanksgiving
season: "October–December"
description: "38 lightened-up Thanksgiving recipes — all under 600 kcal with 15 g+ protein. Light sides, turkey mains, and salads that fit a healthy holiday plate without giving up tradition."
keywords: ["healthy thanksgiving recipes", "low calorie thanksgiving sides", "healthy thanksgiving main dishes", "light thanksgiving recipes under 600 calories", "high protein thanksgiving recipes"]
---

## The healthy Thanksgiving plate

A traditional Thanksgiving dinner can easily top 3,000 calories. You do not have to give up the holiday to eat well: build your plate around **lean turkey and vegetable-forward sides**, keep portions of the rich classics, and most plates land between 700 and 900 calories — with more protein and fiber than the standard spread.

Every recipe below follows the Waimind standard: **400–600 kcal per serving and at least 15 g of protein**, so a full plate of two sides plus a main stays reasonable while tasting like the holiday you know.

## Light Thanksgiving sides (under 300 kcal)

Roasted vegetables and salads carry the light side of the table — most of these come in at 150–300 kcal per serving:

<ul>
{%- assign side_recipes = site.recipes | where: 'category', 'Side' -%}
{%- for r in side_recipes -%}
<li><a href="{{ r.url | relative_url }}">{{ r.title }}</a> — {{ r.calories }} kcal, {{ r.protein }}g protein</li>
{%- endfor -%}
</ul>

Brussels sprouts, green beans, cauliflower, and roasted sweet potatoes are the classic light-side anchors; a Dietitian-recommended swap is simple — cube sweet potatoes, toss with olive oil and spices, roast at high heat instead of building a marshmallow casserole, and you keep the holiday flavor while cutting most of the added sugar.

## Turkey mains that stay lean

Turkey breast is one of the leanest holiday proteins. These mains keep the 15 g+ protein bar while staying inside 600 kcal:

<ul>
{%- assign main_recipes = site.recipes | where: 'category', 'Main' | where_exp: 'r', 'r.protein >= 25' -%}
{%- for r in main_recipes limit: 8 -%}
<li><a href="{{ r.url | relative_url }}">{{ r.title }}</a> — {{ r.calories }} kcal, {{ r.protein }}g protein</li>
{%- endfor -%}
</ul>

## Salads worth a serving bowl

A bright, crunchy salad is the easiest upgrade to a heavy table — citrus, pomegranate, and shaved vegetables are the seasonal pattern across the best healthy-Thanksgiving menus:

<ul>
{%- assign salad_recipes = site.recipes | where: 'category', 'Salad' -%}
{%- for r in salad_recipes -%}
<li><a href="{{ r.url | relative_url }}">{{ r.title }}</a> — {{ r.calories }} kcal, {{ r.protein }}g protein</li>
{%- endfor -%}
</ul>

## Soups to start

A broth-based starter takes the edge off hunger so the rich dishes stay at tasting portions:

<ul>
{%- assign soup_recipes = site.recipes | where: 'category', 'Soup' -%}
{%- for r in soup_recipes limit: 6 -%}
<li><a href="{{ r.url | relative_url }}">{{ r.title }}</a> — {{ r.calories }} kcal, {{ r.protein }}g protein</li>
{%- endfor -%}
</ul>

## Plan the day, not just the plate

The free <a href="{{ '/assets/downloads/7-day-mediterranean-meal-plan.pdf' | relative_url }}">7-Day Mediterranean Meal Plan</a> covers the week around the holiday too — lighter dinners before and after the big meal. Want new healthy recipes weekly? <a href="#newsletter-signup">Join the newsletter</a>.

*Happy Thanksgiving — eat well, enjoy fully.*
