#!/usr/bin/env python3
"""Generate self-hosted GitHub profile SVGs from GitHub GraphQL data."""

import os
import html
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USERNAME", "PT-FLAYY")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = Path("dist")
OUT.mkdir(exist_ok=True)

BG = "#0d1117"
PANEL = "#111820"
BORDER = "#26313d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#8bafff"
GREEN = "#7ee787"
PINK = "#f0a6ca"

def esc(value):
    return html.escape(str(value), quote=True)

def api(query, variables):
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing. Run this script through the GitHub Actions workflow.")
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "flayy-profile-dashboard",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail[:500]}") from exc
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL error: " + "; ".join(e.get("message", "Unknown error") for e in result["errors"]))
    return result["data"]["user"]

def svg_start(width, height, title):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        '<defs><linearGradient id="accent" x1="0" x2="1"><stop offset="0" stop-color="#7ee787"/><stop offset="1" stop-color="#8bafff"/></linearGradient></defs>',
        f'<rect width="{width}" height="{height}" rx="16" fill="{BG}"/>',
        f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="15" fill="none" stroke="{BORDER}"/>',
    ]

def txt(x, y, value, size=14, color=TEXT, weight=400):
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif" font-size="{size}" font-weight="{weight}">{esc(value)}</text>'

def save(name, parts):
    parts.append("</svg>")
    (OUT / name).write_text("\n".join(parts), encoding="utf-8")

now = datetime.now(timezone.utc)
start = now - timedelta(days=365)
query = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    name
    followers { totalCount }
    repositories(privacy: PUBLIC, isFork: false) { totalCount }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
    repositories(
      first: 100
      ownerAffiliations: OWNER
      privacy: PUBLIC
      isFork: false
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      nodes {
        name
        nameWithOwner
        url
        description
        stargazerCount
        forkCount
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""
user = api(query, {
    "login": USERNAME,
    "from": start.isoformat().replace("+00:00", "Z"),
    "to": now.isoformat().replace("+00:00", "Z"),
})

cc = user["contributionsCollection"]
repos = user["repositories"]["nodes"]
stars = sum(r["stargazerCount"] for r in repos)
forks = sum(r["forkCount"] for r in repos)
days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
total_contrib = cc["contributionCalendar"]["totalContributions"]

# Overview card
p = svg_start(900, 220, "GitHub statistics")
p += [txt(28, 38, "FLAYY / GITHUB OVERVIEW", 13, MUTED, 650),
      txt(28, 73, "A year of building and contributing", 22, TEXT, 650)]
metrics = [
    ("PUBLIC REPOSITORIES", user["repositories"]["totalCount"]),
    ("STARS EARNED", stars),
    ("FOLLOWERS", user["followers"]["totalCount"]),
    ("COMMITS · 1 YEAR", cc["totalCommitContributions"]),
    ("PULL REQUESTS", cc["totalPullRequestContributions"]),
    ("CONTRIBUTIONS · 1 YEAR", total_contrib),
]
for i, (label, value) in enumerate(metrics):
    col, row = i % 3, i // 3
    x, y = 28 + col * 292, 112 + row * 62
    p.append(f'<rect x="{x}" y="{y-25}" width="270" height="51" rx="9" fill="{PANEL}" stroke="{BORDER}"/>')
    p.append(txt(x+13, y-5, f"{value:,}", 21, TEXT, 700))
    p.append(txt(x+13, y+14, label, 9, MUTED, 600))
save("stats.svg", p)

# Language share from actual public repository byte counts returned by GraphQL.
language_totals = {}
language_colors = {}
for repo in repos:
    for edge in repo["languages"]["edges"]:
        name = edge["node"]["name"]
        language_totals[name] = language_totals.get(name, 0) + edge["size"]
        language_colors[name] = edge["node"]["color"] or ACCENT
sorted_langs = sorted(language_totals.items(), key=lambda item: item[1], reverse=True)[:6]
p = svg_start(900, 230, "Most used languages in public repositories")
p += [txt(28, 38, "LANGUAGE BREAKDOWN", 13, MUTED, 650),
      txt(28, 73, "Based on source-code size across public, non-fork repositories", 17, TEXT, 600)]
total_bytes = sum(language_totals.values())
if total_bytes:
    x, y, bar_w = 28, 100, 844
    used = 0
    for name, amount in sorted_langs:
        w = bar_w * amount / total_bytes
        p.append(f'<rect x="{x+used:.1f}" y="{y}" width="{max(w,1):.1f}" height="13" fill="{esc(language_colors[name])}"/>')
        used += w
    for i, (name, amount) in enumerate(sorted_langs):
        col, row = i % 3, i // 3
        xx, yy = 28 + col * 285, 151 + row * 34
        pct = amount / total_bytes * 100
        p.append(f'<circle cx="{xx+5}" cy="{yy-5}" r="5" fill="{esc(language_colors[name])}"/>')
        p.append(txt(xx+17, yy, name, 13, TEXT, 600))
        p.append(txt(xx+245, yy, f"{pct:.1f}%", 12, MUTED, 500))
else:
    p.append(txt(28, 125, "No language data available in the public repositories returned by GitHub.", 14, MUTED))
save("languages.svg", p)

# Repository ranking by stars, with honest empty state.
top_repos = sorted(repos, key=lambda r: (r["stargazerCount"], r["forkCount"], r["name"].lower()), reverse=True)[:5]
p = svg_start(900, 300, "Top public repositories")
p += [txt(28, 38, "REPOSITORY SPOTLIGHT", 13, MUTED, 650),
      txt(28, 73, "Public projects ranked by stars", 19, TEXT, 650)]
if top_repos:
    for i, repo in enumerate(top_repos):
        y = 112 + i * 35
        name = repo["name"][:35]
        desc = (repo.get("description") or "No description provided")[:65]
        lang = repo["primaryLanguage"]["name"] if repo.get("primaryLanguage") else "—"
        p.append(f'<line x1="28" y1="{y+12}" x2="872" y2="{y+12}" stroke="{BORDER}"/>')
        p.append(txt(30, y, f"{i+1:02d}", 11, MUTED, 600))
        p.append(f'<a href="{esc(repo["url"])}" target="_blank">')
        p.append(txt(67, y, name, 14, ACCENT, 650))
        p.append("</a>")
        p.append(txt(370, y, lang, 11, MUTED))
        p.append(txt(690, y, f"★ {repo['stargazerCount']}   Forks {repo['forkCount']}", 11, TEXT, 500))
else:
    p.append(txt(28, 125, "No public, non-fork repositories were returned by GitHub.", 14, MUTED))
save("repositories.svg", p)

# Contribution rhythm: actual daily counts from GitHub's contribution calendar.
p = svg_start(900, 190, "Contribution rhythm over the last year")
p += [txt(28, 38, "CONTRIBUTION RHYTHM", 13, MUTED, 650),
      txt(28, 70, f"{total_contrib:,} contributions in the last year", 19, TEXT, 650)]
grid_x, grid_y, cell, gap = 29, 91, 10, 3
counts = [d["contributionCount"] for d in days]
max_count = max(counts) if counts else 0
# Calendar API returns weeks; render each day in its week column.
weeks = cc["contributionCalendar"]["weeks"]
for wi, week in enumerate(weeks[-53:]):
    for di, day in enumerate(week["contributionDays"]):
        count = day["contributionCount"]
        if count == 0:
            color = "#18212b"
        else:
            ratio = count / max(max_count, 1)
            color = "#0e4429" if ratio < .25 else "#006d32" if ratio < .5 else "#26a641" if ratio < .75 else "#39d353"
        x = grid_x + wi * (cell + gap)
        y = grid_y + di * (cell + gap)
        p.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}"><title>{esc(day["date"])}: {count} contributions</title></rect>')
p.append(txt(28, 178, "Less", 9, MUTED))
for j, color in enumerate(["#18212b", "#0e4429", "#006d32", "#26a641", "#39d353"]):
    p.append(f'<rect x="{72+j*16}" y="168" width="11" height="9" rx="2" fill="{color}"/>')
p.append(txt(162, 178, "More", 9, MUTED))
save("rhythm.svg", p)

print(f"Generated dashboard SVGs for {USERNAME}: {len(repos)} repositories, {total_contrib} contributions.")
