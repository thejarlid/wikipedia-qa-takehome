#!/usr/bin/env python3
"""Generate a self-contained HTML dashboard from eval result JSON files.

Usage:
  python generate_dashboard.py
  python generate_dashboard.py --out my_dashboard.html
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

RESULTS_DIR = Path("results")


# Weights must match evals/runner.py JUDGE_WEIGHTS exactly.
_WEIGHTS = {"groundedness": 0.35, "correctness": 0.35, "search_strategy": 0.20, "completeness": 0.10}


def _composite(judges: dict) -> float:
    """Compute composite 0–100 from a judges dict, matching runner.py logic."""
    total = 0.0
    for name, weight in _WEIGHTS.items():
        jr = judges.get(name) or {}
        score = jr.get("score", 0) if isinstance(jr, dict) else 0
        total += max(0.0, (score - 1) / 4.0) * 100 * weight
    return round(total, 1)


# ── Data loading ──────────────────────────────────────────────────────────────

def load_runs() -> dict:
    runs = {}
    for f in sorted(RESULTS_DIR.glob("*_results.json")):
        version = f.stem.replace("_results", "")
        try:
            cases = json.loads(f.read_text())
            synthesis = ""
            report_f = RESULTS_DIR / f"{version}_report.md"
            if report_f.exists():
                synthesis = report_f.read_text().strip()
            runs[version] = {
                "version": version,
                "cases": cases,
                "synthesis": synthesis,
                "stats": compute_stats(cases),
            }
        except Exception as e:
            print(f"Warning: could not load {f}: {e}")
    return runs


def compute_stats(cases: list) -> dict:
    total = len(cases)
    passed = sum(1 for c in cases if c.get("overall_passed"))

    by_cat: dict = defaultdict(lambda: {"passed": 0, "total": 0})
    for c in cases:
        cat = c.get("category", "unknown")
        by_cat[cat]["total"] += 1
        if c.get("overall_passed"):
            by_cat[cat]["passed"] += 1

    by_ret: dict = defaultdict(lambda: {"passed": 0, "total": 0})
    for c in cases:
        ret = c.get("retrievability", "unknown")
        by_ret[ret]["total"] += 1
        if c.get("overall_passed"):
            by_ret[ret]["passed"] += 1

    # Per-judge averages on 0–100 scale (normalised from 1–5)
    judge_scores: dict = defaultdict(list)
    for c in cases:
        for name, jr in c.get("judges", {}).items():
            if isinstance(jr, dict) and "score" in jr:
                normalised = max(0.0, (jr["score"] - 1) / 4.0) * 100
                judge_scores[name].append(normalised)

    judge_avgs = {
        name: round(sum(s) / len(s), 1)
        for name, s in judge_scores.items() if s
    }

    # Weighted composite: use stored field if present, otherwise compute from judges.
    composite_scores = []
    for c in cases:
        cs = c.get("composite_score")
        if cs is None:
            cs = _composite(c.get("judges", {}))
        composite_scores.append(cs)
    avg_score = round(sum(composite_scores) / len(composite_scores), 1) if composite_scores else 0.0

    all_tags: list = []
    for c in cases:
        all_tags.extend(c.get("failure_tags", []))

    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "avg_score": avg_score,
        "by_category": {k: {"passed": v["passed"], "total": v["total"],
                            "rate": round(v["passed"] / v["total"] * 100, 1) if v["total"] else 0}
                        for k, v in sorted(by_cat.items())},
        "by_retrievability": {k: {"passed": v["passed"], "total": v["total"],
                                  "rate": round(v["passed"] / v["total"] * 100, 1) if v["total"] else 0}
                              for k, v in sorted(by_ret.items())},
        "judge_averages": judge_avgs,
        "tag_counts": Counter(all_tags).most_common(15),
        "early_stop": {
            "correctly_declined": sum(1 for c in cases if c.get("early_stop_outcome") == "correctly_declined"),
            "scope_violations": sum(1 for c in cases if c.get("early_stop_outcome") == "scope_violation"),
        },
    }


# ── HTML generation ───────────────────────────────────────────────────────────

def generate_html(runs: dict) -> str:
    versions = list(runs.keys())
    # Escape </script> so the HTML parser doesn't terminate the script block
    # early when Wikipedia content contains that string.
    runs_json = json.dumps(runs, ensure_ascii=False).replace("</script>", "<\\/script>")
    versions_json = json.dumps(versions)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wikipedia QA Eval Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #f1f5f9; --surface: #fff; --border: #e2e8f0;
    --text: #1e293b; --muted: #64748b;
    --primary: #2563eb; --primary-light: #eff6ff;
    --green: #16a34a; --green-bg: #f0fdf4;
    --amber: #d97706; --amber-bg: #fffbeb;
    --red: #dc2626; --red-bg: #fef2f2;
    --radius: 8px; --shadow: 0 1px 3px rgba(0,0,0,.1);
  }}
  body {{ font-family: system-ui,-apple-system,sans-serif; background: var(--bg); color: var(--text); font-size: 14px; }}
  a {{ color: var(--primary); text-decoration: none; }}

  /* ── Layout ── */
  .container {{ max-width: 1400px; margin: 0 auto; padding: 0 24px; }}
  header {{ background: var(--surface); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 100; }}
  .header-inner {{ display: flex; align-items: center; gap: 24px; padding: 12px 0; }}
  .logo {{ font-weight: 700; font-size: 16px; color: var(--text); white-space: nowrap; }}
  .logo span {{ color: var(--primary); }}
  .tabs {{ display: flex; gap: 4px; overflow-x: auto; }}
  .tab {{ padding: 6px 16px; border-radius: 6px; border: none; background: none; cursor: pointer; font-size: 14px; font-weight: 500; color: var(--muted); transition: all .15s; white-space: nowrap; }}
  .tab:hover {{ background: var(--bg); color: var(--text); }}
  .tab.active {{ background: var(--primary-light); color: var(--primary); }}
  .tab-compare {{ margin-left: auto; }}

  main {{ padding: 24px 0 48px; }}
  .view {{ display: none; }}
  .view.active {{ display: block; }}

  /* ── Tiles ── */
  .tiles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
  .tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); }}
  .tile-label {{ font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }}
  .tile-value {{ font-size: 28px; font-weight: 700; line-height: 1; }}
  .tile-sub {{ font-size: 12px; color: var(--muted); margin-top: 6px; }}
  .green {{ color: var(--green); }}
  .amber {{ color: var(--amber); }}
  .red {{ color: var(--red); }}

  /* ── Charts ── */
  .charts-row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; box-shadow: var(--shadow); }}
  .chart-title {{ font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 16px; }}
  .chart-wrap {{ position: relative; height: 260px; }}

  /* ── Synthesis ── */
  .synthesis-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; box-shadow: var(--shadow); margin-bottom: 24px; }}
  .synthesis-card h2 {{ font-size: 15px; font-weight: 600; margin-bottom: 16px; color: var(--text); }}
  .synthesis-body {{ max-height: 520px; overflow-y: auto; line-height: 1.7; color: var(--text); overflow-wrap: break-word; word-break: break-word; padding-right: 6px; }}
  .synthesis-body h1 {{ font-size: 15px; font-weight: 700; margin: 16px 0 8px; }}
  .synthesis-body h2 {{ font-size: 14px; font-weight: 600; margin: 16px 0 6px; color: var(--text); }}
  .synthesis-body h3 {{ font-size: 13px; font-weight: 600; margin: 12px 0 4px; color: var(--text); }}
  .synthesis-body p {{ margin-bottom: 10px; }}
  .synthesis-body ul {{ padding-left: 20px; margin-bottom: 10px; }}
  .synthesis-body li {{ margin-bottom: 4px; }}
  .synthesis-body strong {{ font-weight: 600; }}
  .synthesis-body hr {{ border: none; border-top: 1px solid var(--border); margin: 16px 0; }}
  .synthesis-body code {{ background: var(--bg); padding: 1px 5px; border-radius: 3px; font-family: monospace; font-size: 11px; }}
  .synthesis-empty {{ color: var(--muted); font-style: italic; }}
  .md-table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin: 10px 0 16px; }}
  .md-table th {{ background: var(--bg); padding: 6px 10px; text-align: left; font-weight: 600; border: 1px solid var(--border); white-space: nowrap; }}
  .md-table td {{ padding: 5px 10px; border: 1px solid var(--border); }}
  .md-table tr:nth-child(even) td {{ background: #fafafa; }}

  /* ── Table ── */
  .cases-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }}
  .table-controls {{ display: flex; gap: 10px; padding: 16px; border-bottom: 1px solid var(--border); flex-wrap: wrap; align-items: center; }}
  .table-controls h2 {{ font-size: 15px; font-weight: 600; margin-right: 8px; }}
  .search-input {{ flex: 1; min-width: 200px; padding: 7px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; outline: none; }}
  .search-input:focus {{ border-color: var(--primary); }}
  select.filter {{ padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; background: var(--surface); cursor: pointer; }}
  .btn-clear {{ padding: 7px 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); font-size: 13px; cursor: pointer; color: var(--muted); }}
  .btn-clear:hover {{ background: var(--bg); }}

  .cases-table {{ width: 100%; border-collapse: collapse; }}
  .cases-table th {{ padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; border-bottom: 1px solid var(--border); background: var(--bg); white-space: nowrap; }}
  .cases-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  .case-row {{ cursor: pointer; transition: background .1s; }}
  .case-row:hover {{ background: var(--primary-light); }}
  .case-row.expanded {{ background: var(--primary-light); }}
  .detail-row {{ display: none; }}
  .detail-row.open {{ display: table-row; }}
  .detail-cell {{ padding: 0 !important; }}
  .detail-inner {{ padding: 20px; background: #fafbff; border-bottom: 1px solid var(--border); }}

  .q-text {{ max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
  .badge-green {{ background: var(--green-bg); color: var(--green); }}
  .badge-amber {{ background: var(--amber-bg); color: var(--amber); }}
  .badge-red {{ background: var(--red-bg); color: var(--red); }}
  .badge-blue {{ background: var(--primary-light); color: var(--primary); }}
  .badge-gray {{ background: var(--bg); color: var(--muted); }}
  .pass-icon {{ font-size: 16px; }}
  .tag-list {{ display: flex; flex-wrap: wrap; gap: 4px; max-width: 220px; }}
  .tag {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 11px; background: var(--bg); color: var(--muted); border: 1px solid var(--border); white-space: nowrap; }}

  /* ── Detail panel ── */
  .detail-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }}
  .detail-section {{ margin-bottom: 16px; }}
  .detail-section h3 {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 8px; }}
  .detail-section p, .detail-section pre {{ font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; overflow-wrap: break-word; }}
  .search-item {{ font-size: 13px; padding: 4px 0; display: flex; gap: 8px; align-items: baseline; }}
  .search-query {{ color: var(--muted); font-style: italic; }}
  .search-arrow {{ color: var(--muted); }}
  .search-title {{ color: var(--text); font-weight: 500; }}
  .search-error {{ color: var(--red); }}

  .judges-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 4px; }}
  .judge-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 14px; }}
  .judge-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }}
  .judge-name {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }}
  .judge-score {{ font-size: 20px; font-weight: 700; }}
  .score-bar {{ height: 4px; background: var(--border); border-radius: 2px; margin-bottom: 8px; }}
  .score-fill {{ height: 100%; border-radius: 2px; transition: width .3s; }}
  .judge-reasoning {{ font-size: 12px; color: var(--muted); line-height: 1.5; overflow-wrap: break-word; word-break: break-word; max-height: 160px; overflow-y: auto; }}
  .judge-tags {{ margin-top: 6px; display: flex; flex-wrap: wrap; gap: 3px; }}

  .checks-grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .check-item {{ font-size: 11px; padding: 3px 8px; border-radius: 4px; display: flex; align-items: center; gap: 4px; }}
  .check-pass {{ background: var(--green-bg); color: var(--green); }}
  .check-fail {{ background: var(--red-bg); color: var(--red); }}

  /* ── Compare ── */
  .compare-controls {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 24px; box-shadow: var(--shadow); display: flex; gap: 16px; align-items: flex-end; flex-wrap: wrap; }}
  .compare-controls label {{ display: block; font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; text-transform: uppercase; }}
  .compare-controls select {{ padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px; background: var(--surface); min-width: 120px; }}
  .btn-primary {{ padding: 8px 20px; background: var(--primary); color: #fff; border: none; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; }}
  .btn-primary:hover {{ background: #1d4ed8; }}
  .delta-tile .tile-value {{ font-size: 20px; }}
  .delta {{ font-size: 13px; font-weight: 600; margin-left: 6px; }}
  .delta.pos {{ color: var(--green); }}
  .delta.neg {{ color: var(--red); }}
  .compare-table td:nth-child(5), .compare-table td:nth-child(6) {{ background: #fafafa; }}
  .compare-placeholder {{ color: var(--muted); font-style: italic; padding: 40px 0; text-align: center; }}

  /* ── Responsive ── */
  @media (max-width: 900px) {{
    .tiles {{ grid-template-columns: repeat(2, 1fr); }}
    .charts-row {{ grid-template-columns: 1fr; }}
    .detail-grid {{ grid-template-columns: 1fr; }}
    .judges-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<header>
  <div class="container">
    <div class="header-inner">
      <div class="logo">Wikipedia QA <span>Evals</span></div>
      <div class="tabs" id="tabs"></div>
    </div>
  </div>
</header>

<main>
  <div class="container">
    <div id="views"></div>
    <div id="compare-view" class="view"></div>
  </div>
</main>

<script>
// ── Embedded data ─────────────────────────────────────────────────────────────
const RUNS = {runs_json};
const VERSIONS = {versions_json};

// ── Charts registry ───────────────────────────────────────────────────────────
const charts = {{}};

// ── Utils ─────────────────────────────────────────────────────────────────────
function scoreColor(v) {{
  if (v >= 4) return 'var(--green)';
  if (v >= 3) return 'var(--amber)';
  return 'var(--red)';
}}
function rateColor(v) {{
  if (v >= 70) return 'green';
  if (v >= 50) return 'amber';
  return 'red';
}}
function avgScoreClass(v) {{
  // v is 0–100 composite score
  if (v >= 70) return 'green';
  if (v >= 50) return 'amber';
  return 'red';
}}
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}
function trunc(s, n=80) {{
  return s && s.length > n ? s.slice(0, n) + '…' : (s || '');
}}
function inlineFmt(t) {{
  return t
    .replace(/[*][*](.+?)[*][*]/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}}
function md(text) {{
  if (!text) return '<em class="synthesis-empty">No synthesis available for this run.</em>';
  const lines = text.split('\\n');
  const out = [];
  let i = 0, inP = false;
  const closeP = () => {{ if (inP) {{ out.push('</p>'); inP = false; }} }};
  while (i < lines.length) {{
    const line = lines[i];
    // Table: row starts with |, next line is separator |---|
    if (line.startsWith('|') && i+1 < lines.length && /^[|][-| :]+[|]/.test(lines[i+1])) {{
      closeP();
      const hdrs = line.split('|').slice(1,-1).map(c => `<th>${{inlineFmt(c.trim())}}</th>`).join('');
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].startsWith('|')) {{
        const cells = lines[i].split('|').slice(1,-1).map(c => `<td>${{inlineFmt(c.trim())}}</td>`).join('');
        rows.push(`<tr>${{cells}}</tr>`);
        i++;
      }}
      out.push(`<table class="md-table"><thead><tr>${{hdrs}}</tr></thead><tbody>${{rows.join('')}}</tbody></table>`);
      continue;
    }}
    if (/^### /.test(line)) {{ closeP(); out.push(`<h3>${{inlineFmt(line.slice(4))}}</h3>`); i++; continue; }}
    if (/^## /.test(line))  {{ closeP(); out.push(`<h2>${{inlineFmt(line.slice(3))}}</h2>`); i++; continue; }}
    if (/^# /.test(line))   {{ closeP(); out.push(`<h1>${{inlineFmt(line.slice(2))}}</h1>`); i++; continue; }}
    if (/^---+$/.test(line.trim())) {{ closeP(); out.push('<hr>'); i++; continue; }}
    if (/^[*-] /.test(line)) {{
      closeP();
      const items = [];
      while (i < lines.length && /^[*-] /.test(lines[i])) {{
        items.push(`<li>${{inlineFmt(lines[i].slice(2))}}</li>`); i++;
      }}
      out.push(`<ul>${{items.join('')}}</ul>`);
      continue;
    }}
    if (line.trim() === '') {{ closeP(); i++; continue; }}
    if (!inP) {{ out.push('<p>'); inP = true; }} else {{ out.push(' '); }}
    out.push(inlineFmt(line));
    i++;
  }}
  closeP();
  return out.join('');
}}

// ── Navigation ─────────────────────────────────────────────────────────────────
function buildNav() {{
  const tabs = document.getElementById('tabs');
  VERSIONS.forEach((v, i) => {{
    const btn = document.createElement('button');
    btn.className = 'tab' + (i === 0 ? ' active' : '');
    btn.textContent = v;
    btn.onclick = () => showVersion(v);
    tabs.appendChild(btn);
  }});
  const cmp = document.createElement('button');
  cmp.className = 'tab tab-compare';
  cmp.textContent = 'Compare';
  cmp.onclick = () => showCompare();
  tabs.appendChild(cmp);
}}

function showVersion(v) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => {{ if(t.textContent === v) t.classList.add('active'); }});
  document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
  const el = document.getElementById('view-' + v);
  if (el) el.classList.add('active');
  // Resize charts after show
  setTimeout(() => Object.values(charts).forEach(c => c.resize && c.resize()), 50);
}}

function showCompare() {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => {{ if(t.textContent === 'Compare') t.classList.add('active'); }});
  document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
  document.getElementById('compare-view').classList.add('active');
}}

// ── Metric tiles ──────────────────────────────────────────────────────────────
function renderTiles(v) {{
  const s = RUNS[v].stats;
  const rc = rateColor(s.pass_rate);
  const sc = avgScoreClass(s.avg_score);
  return `
    <div class="tile"><div class="tile-label">Cases</div><div class="tile-value">${{s.total}}</div><div class="tile-sub">eval cases</div></div>
    <div class="tile"><div class="tile-label">Passed</div><div class="tile-value">${{s.passed}} <span style="font-size:16px;font-weight:400;color:var(--muted)">/ ${{s.total}}</span></div></div>
    <div class="tile"><div class="tile-label">Pass Rate</div><div class="tile-value ${{rc}}">${{s.pass_rate}}%</div></div>
    <div class="tile"><div class="tile-label">Composite Score</div><div class="tile-value ${{sc}}">${{s.avg_score}}<span style="font-size:14px;font-weight:400;color:var(--muted)">/100</span></div><div class="tile-sub" style="font-size:10px;color:var(--muted)">G×35 · C×35 · S×20 · CP×10</div></div>`;
}}

// ── Radar chart ───────────────────────────────────────────────────────────────
function renderRadar(v, canvasId) {{
  const ja = RUNS[v].stats.judge_averages;  // already 0–100
  const labels = ['Groundedness','Correctness','Completeness','Search Strategy'];
  const keys = ['groundedness','correctness','completeness','search_strategy'];
  const weights = {{ groundedness:'35%', correctness:'35%', search_strategy:'20%', completeness:'10%' }};
  const data = keys.map(k => ja[k] || 0);
  const ctx = document.getElementById(canvasId).getContext('2d');
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(ctx, {{
    type: 'radar',
    data: {{
      labels,
      datasets: [{{ label: v, data, borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,.12)', pointBackgroundColor: '#2563eb', borderWidth: 2 }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{ r: {{ min: 0, max: 100, ticks: {{ stepSize: 25, font: {{ size: 10 }} }}, pointLabels: {{ font: {{ size: 12 }} }} }} }},
      plugins: {{ legend: {{ display: false }} }}
    }}
  }});
}}

// ── Bar chart ─────────────────────────────────────────────────────────────────
function renderBar(v, canvasId) {{
  const bc = RUNS[v].stats.by_category;
  const labels = Object.keys(bc);
  const data = labels.map(k => bc[k].rate);
  const colors = data.map(r => r >= 70 ? 'rgba(22,163,74,.7)' : r >= 50 ? 'rgba(217,119,6,.7)' : 'rgba(220,38,38,.7)');
  const ctx = document.getElementById(canvasId).getContext('2d');
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(ctx, {{
    type: 'bar',
    data: {{ labels, datasets: [{{ label: 'Pass Rate %', data, backgroundColor: colors, borderRadius: 3 }}] }},
    options: {{
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      scales: {{
        x: {{ min: 0, max: 100, ticks: {{ font: {{ size: 11 }} }} }},
        y: {{ ticks: {{ font: {{ size: 11 }} }} }}
      }},
      plugins: {{ legend: {{ display: false }} }}
    }}
  }});
}}

// ── Trend line chart (shared, shows all versions) ─────────────────────────────
function renderTrend(canvasId) {{
  const dims = ['groundedness','correctness','completeness','search_strategy'];
  const dimLabels = ['Groundedness','Correctness','Completeness','Search Strategy'];
  const colors = ['#2563eb','#16a34a','#d97706','#7c3aed'];
  const vLabels = VERSIONS;

  // Composite
  const compositeData = VERSIONS.map(v => RUNS[v].stats.avg_score);
  const dimData = dims.map((d, i) => ({{
    label: dimLabels[i],
    data: VERSIONS.map(v => RUNS[v].stats.judge_averages[d] || 0),
    borderColor: colors[i], backgroundColor: colors[i] + '22',
    borderWidth: 2, pointRadius: 4, tension: 0.3,
  }}));

  const ctx = document.getElementById(canvasId).getContext('2d');
  if (charts[canvasId]) charts[canvasId].destroy();
  charts[canvasId] = new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: vLabels,
      datasets: [
        {{ label: 'Composite', data: compositeData, borderColor: '#0f172a', backgroundColor: '#0f172a22', borderWidth: 2.5, pointRadius: 5, tension: 0.3, borderDash: [5,3] }},
        ...dimData
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      scales: {{ y: {{ min: 0, max: 100, ticks: {{ stepSize: 25, font: {{ size: 11 }} }} }}, x: {{ ticks: {{ font: {{ size: 11 }} }} }} }},
      plugins: {{ legend: {{ position: 'bottom', labels: {{ font: {{ size: 11 }} }} }} }}
    }}
  }});
}}

// ── Test case table ───────────────────────────────────────────────────────────
function renderTable(v, containerId) {{
  const cases = RUNS[v].cases;
  const categories = [...new Set(cases.map(c => c.category))].sort();
  const catOptions = categories.map(c => `<option value="${{esc(c)}}">${{esc(c)}}</option>`).join('');
  const tableId = `tbl-${{v}}`;

  const html = `
    <div class="cases-card">
      <div class="table-controls">
        <h2>Test Cases</h2>
        <input class="search-input" type="search" placeholder="Search question…" oninput="filterTable('${{v}}')" id="search-${{v}}">
        <select class="filter" id="filter-cat-${{v}}" onchange="filterTable('${{v}}')">
          <option value="">All categories</option>${{catOptions}}
        </select>
        <select class="filter" id="filter-pass-${{v}}" onchange="filterTable('${{v}}')">
          <option value="">All results</option>
          <option value="pass">Passed</option>
          <option value="fail">Failed</option>
        </select>
        <button class="btn-clear" onclick="clearFilters('${{v}}')">Clear</button>
      </div>
      <div style="overflow-x:auto">
        <table class="cases-table" id="${{tableId}}">
          <thead><tr>
            <th>ID</th><th>Question</th><th>Category</th><th>Scope</th>
            <th>Retrieve</th><th>Passed</th><th>Avg Score</th><th>Failure Tags</th>
          </tr></thead>
          <tbody>${{cases.map(c => caseRow(c, v)).join('')}}</tbody>
        </table>
      </div>
    </div>`;
  document.getElementById(containerId).innerHTML = html;
}}

function caseRow(c, v) {{
  const passed = c.overall_passed;
  const passIcon = passed ? '<span class="pass-icon" style="color:var(--green)">✓</span>' : '<span class="pass-icon" style="color:var(--red)">✗</span>';

  const avgScore = (() => {{
    const WEIGHTS = {{groundedness:0.35, correctness:0.35, search_strategy:0.20, completeness:0.10}};
    let cs = (c.composite_score !== undefined && c.composite_score !== null)
      ? c.composite_score
      : (() => {{
          let t = 0;
          const judges = c.judges || {{}};
          for (const [k, w] of Object.entries(WEIGHTS)) {{
            const jr = judges[k] || {{}};
            t += Math.max(0, ((jr.score || 0) - 1) / 4) * 100 * w;
          }}
          return Math.round(t * 10) / 10;
        }})();
    if (!Object.keys(c.judges || {{}}).length && !c.composite_score) return '—';
    const cls = cs >= 70 ? 'badge-green' : cs >= 50 ? 'badge-amber' : 'badge-red';
    return `<span class="badge ${{cls}}">${{cs.toFixed(0)}}</span>`;
  }})();

  const tags = (c.failure_tags || []).slice(0,3).map(t => `<span class="tag">${{esc(t)}}</span>`).join('');
  const moreTags = c.failure_tags && c.failure_tags.length > 3 ? `<span class="tag">+${{c.failure_tags.length-3}}</span>` : '';

  const scope = c.early_stop
    ? (c.early_stop_outcome === 'correctly_declined' ? '<span class="badge badge-green">Declined ✓</span>' : '<span class="badge badge-red">Scope Violation</span>')
    : '<span class="badge badge-gray">In Scope</span>';

  return `
    <tr class="case-row${{passed ? '' : ' fail-row'}}" onclick="toggleDetail('${{esc(c.case_id)}}','${{v}}')" data-cat="${{esc(c.category)}}" data-pass="${{passed ? 'pass' : 'fail'}}">
      <td style="font-family:monospace;font-size:12px;white-space:nowrap">${{esc(c.case_id)}}</td>
      <td><div class="q-text" title="${{esc(c.question)}}">${{esc(trunc(c.question))}}</div></td>
      <td><span class="badge badge-blue">${{esc(c.category)}}</span></td>
      <td>${{scope}}</td>
      <td><span class="badge badge-gray">${{esc(c.retrievability || '—')}}</span></td>
      <td style="text-align:center">${{passIcon}}</td>
      <td style="text-align:center">${{avgScore}}</td>
      <td><div class="tag-list">${{tags}}${{moreTags}}</div></td>
    </tr>
    <tr class="detail-row" id="detail-${{esc(c.case_id)}}-${{v}}">
      <td colspan="8" class="detail-cell">${{renderDetail(c)}}</td>
    </tr>`;
}}

function toggleDetail(caseId, v) {{
  const row = document.getElementById(`detail-${{caseId}}-${{v}}`);
  if (!row) return;
  row.classList.toggle('open');
  const caseRow = row.previousElementSibling;
  caseRow.classList.toggle('expanded');
}}

function renderDetail(c) {{
  // Answer + reasoning
  const confBadge = `<span class="badge ${{c.confidence === 'high' ? 'badge-green' : c.confidence === 'medium' ? 'badge-amber' : 'badge-red'}}">${{esc(c.confidence || '—')}}</span>`;
  const sources = (c.sources_used || []).map(s => `<a href="https://en.wikipedia.org/wiki/${{encodeURIComponent(s.replace(/ /g,'_'))}}" target="_blank">${{esc(s)}}</a>`).join(', ');
  const ansHtml = `
    <div class="detail-section">
      <h3>Answer ${{confBadge}}</h3>
      <p style="margin-bottom:8px">${{esc(c.answer || '(none)')}}</p>
      ${{sources ? `<p style="font-size:12px;color:var(--muted)">Sources: ${{sources}}</p>` : ''}}
      ${{c.limitations ? `<p style="font-size:12px;color:var(--amber);margin-top:4px">⚠ ${{esc(c.limitations)}}</p>` : ''}}
      ${{c.reasoning ? `<details style="margin-top:8px"><summary style="font-size:12px;cursor:pointer;color:var(--muted)">Model reasoning</summary><p style="font-size:12px;margin-top:6px;color:var(--muted)">${{esc(c.reasoning)}}</p></details>` : ''}}
    </div>`;

  // Agent trace timeline — model reasoning + tool calls as a step-by-step flow
  const traceSteps = (c.trace || []).map(t => {{
    const toolColor = t.tool_name === 'submit_answer' ? 'var(--green)' : 'var(--primary)';
    const toolIcon = t.tool_name === 'submit_answer' ? '✓' : '🔍';
    let toolLine = '';
    if (t.tool_name === 'search_wikipedia') {{
      const q = (t.tool_input || {{}}).query || '';
      // Find matching search result
      const sr = (c.searches || []).find(s => s.query === q);
      const article = sr ? (sr.error ? `<span style="color:var(--red)">${{esc(sr.error)}}</span>` : `<a href="${{esc(sr.url||'#')}}" target="_blank" style="font-weight:500">${{esc(sr.title||'?')}}</a>`) : '?';
      toolLine = `<div style="margin-top:4px;padding:5px 8px;background:var(--primary-light);border-radius:4px;font-size:12px">
        <span style="color:var(--primary);font-weight:600">search_wikipedia</span>
        <span style="color:var(--muted)"> query=</span><em>"${{esc(q)}}"</em>
        <span style="color:var(--muted)"> → </span>${{article}}
      </div>`;
    }} else if (t.tool_name === 'submit_answer') {{
      toolLine = `<div style="margin-top:4px;padding:5px 8px;background:var(--green-bg);border-radius:4px;font-size:12px;color:var(--green);font-weight:600">✓ submit_answer</div>`;
    }}
    return `
      <div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
        <div style="flex:0 0 28px;height:28px;border-radius:50%;background:var(--bg);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--muted);margin-top:2px">${{t.step}}</div>
        <div style="flex:1;min-width:0">
          ${{t.model_text ? `<p style="font-size:12px;color:var(--text);margin-bottom:4px;font-style:italic">"${{esc(t.model_text.slice(0,300))}}${{t.model_text.length>300?'…':''}}"</p>` : ''}}
          ${{toolLine}}
        </div>
      </div>`;
  }}).join('');
  const traceHtml = `
    <div class="detail-section">
      <h3>Agent Trace (${{(c.trace||[]).length}} steps)</h3>
      ${{traceSteps || '<p style="color:var(--muted);font-size:12px">No trace available</p>'}}
    </div>`;

  // Judges
  const judgeOrder = ['groundedness','correctness','completeness','search_strategy'];
  const judgeNames = {{ groundedness:'Groundedness', correctness:'Correctness', completeness:'Completeness', search_strategy:'Search Strategy' }};
  const judgesHtml = `
    <div class="detail-section">
      <h3>Judge Panel</h3>
      <div class="judges-grid">
        ${{judgeOrder.map(jk => {{
          const jr = (c.judges || {{}})[jk];
          if (!jr) return `<div class="judge-card" style="color:var(--muted);font-size:12px">No result for ${{jk}}</div>`;
          const sc = scoreColor(jr.score);
          const pct = (jr.score / 5 * 100).toFixed(0);
          const tags = (jr.failure_tags || []).map(t => `<span class="tag">${{esc(t)}}</span>`).join('');
          return `
            <div class="judge-card">
              <div class="judge-header">
                <span class="judge-name">${{judgeNames[jk] || jk}}</span>
                <span class="judge-score" style="color:${{sc}}">${{jr.score}}<span style="font-size:12px;color:var(--muted)">/5</span></span>
              </div>
              <div class="score-bar"><div class="score-fill" style="width:${{pct}}%;background:${{sc}}"></div></div>
              <div class="judge-reasoning">${{esc(jr.reasoning || '—')}}</div>
              ${{tags ? `<div class="judge-tags">${{tags}}</div>` : ''}}
            </div>`;
        }}).join('')}}
      </div>
    </div>`;

  // Deterministic checks
  const checksHtml = (() => {{
    const checks = c.checks || {{}};
    const items = Object.values(checks).map(ch =>
      `<div class="check-item ${{ch.passed ? 'check-pass' : 'check-fail'}}" title="${{esc(ch.detail||'')}}">${{ch.passed ? '✓' : '✗'}} ${{esc(ch.name)}}</div>`
    ).join('');
    return items ? `<div class="detail-section"><h3>Deterministic Checks</h3><div class="checks-grid">${{items}}</div></div>` : '';
  }})();

  return `<div class="detail-inner">
    <div class="detail-grid">
      <div>${{ansHtml}}${{checksHtml}}</div>
      <div>${{traceHtml}}</div>
    </div>
    ${{judgesHtml}}
  </div>`;
}}

function filterTable(v) {{
  const q = (document.getElementById(`search-${{v}}`).value || '').toLowerCase();
  const cat = document.getElementById(`filter-cat-${{v}}`).value;
  const pass = document.getElementById(`filter-pass-${{v}}`).value;
  const tbl = document.getElementById(`tbl-${{v}}`);
  if (!tbl) return;
  tbl.querySelectorAll('.case-row').forEach(row => {{
    const question = (row.querySelector('.q-text')?.textContent || '').toLowerCase();
    const rowCat = row.dataset.cat || '';
    const rowPass = row.dataset.pass || '';
    const visible = (!q || question.includes(q)) && (!cat || rowCat === cat) && (!pass || rowPass === pass);
    row.style.display = visible ? '' : 'none';
    // Also hide the detail row when parent is hidden
    const detail = row.nextElementSibling;
    if (detail?.classList.contains('detail-row')) detail.style.display = visible ? '' : 'none';
  }});
}}

function clearFilters(v) {{
  document.getElementById(`search-${{v}}`).value = '';
  document.getElementById(`filter-cat-${{v}}`).value = '';
  document.getElementById(`filter-pass-${{v}}`).value = '';
  filterTable(v);
}}

// ── Compare view ──────────────────────────────────────────────────────────────
function buildCompareView() {{
  const opts = VERSIONS.map(v => `<option value="${{v}}">${{v}}</option>`).join('');
  const aOpts = opts;
  const bOpts = VERSIONS.length > 1 ? VERSIONS.map((v,i) => `<option value="${{v}}"${{i===1?' selected':''}}>${{v}}</option>`).join('') : opts;
  document.getElementById('compare-view').innerHTML = `
    <div class="compare-controls">
      <div><label>Run A (baseline)</label><select id="cmp-a">${{aOpts}}</select></div>
      <div><label>Run B (new)</label><select id="cmp-b">${{bOpts}}</select></div>
      <button class="btn-primary" onclick="loadCompare()">Compare</button>
    </div>
    <div id="compare-content"><p class="compare-placeholder">Select two runs and click Compare.</p></div>`;
}}

function loadCompare() {{
  const vA = document.getElementById('cmp-a').value;
  const vB = document.getElementById('cmp-b').value;
  if (vA === vB) {{ alert('Select two different runs.'); return; }}
  const sA = RUNS[vA].stats, sB = RUNS[vB].stats;

  function delta(a, b, pct=false) {{
    const d = (b - a);
    const fmt = pct ? d.toFixed(1) + '%' : d.toFixed(2);
    const cls = d > 0 ? 'pos' : d < 0 ? 'neg' : '';
    const sign = d > 0 ? '+' : '';
    return `<span class="delta ${{cls}}">${{sign}}${{fmt}}</span>`;
  }}

  const tiles = `
    <div class="tiles" style="margin-bottom:24px">
      <div class="tile delta-tile"><div class="tile-label">Cases</div><div class="tile-value">${{sA.total}} → ${{sB.total}}</div></div>
      <div class="tile delta-tile"><div class="tile-label">Passed (${{vB}})</div><div class="tile-value">${{sB.passed}} / ${{sB.total}} ${{delta(sA.passed/sA.total*100, sB.passed/sB.total*100, true)}}</div></div>
      <div class="tile delta-tile"><div class="tile-label">Pass Rate</div><div class="tile-value ${{rateColor(sB.pass_rate)}}">${{sB.pass_rate}}% ${{delta(sA.pass_rate, sB.pass_rate, true)}}</div></div>
      <div class="tile delta-tile"><div class="tile-label">Avg Score</div><div class="tile-value ${{avgScoreClass(sB.avg_score)}}">${{sB.avg_score}} ${{delta(sA.avg_score, sB.avg_score)}}</div></div>
    </div>`;

  // Comparison table
  const casesA = {{}};
  RUNS[vA].cases.forEach(c => casesA[c.case_id] = c);
  const casesB = {{}};
  RUNS[vB].cases.forEach(c => casesB[c.case_id] = c);
  const allIds = [...new Set([...Object.keys(casesA), ...Object.keys(casesB)])].sort();

  const rows = allIds.map(id => {{
    const a = casesA[id] || {{}}, b = casesB[id] || {{}};
    const passA = a.overall_passed ? '<span style="color:var(--green)">✓</span>' : '<span style="color:var(--red)">✗</span>';
    const passB = b.overall_passed ? '<span style="color:var(--green)">✓</span>' : '<span style="color:var(--red)">✗</span>';
    const improved = !a.overall_passed && b.overall_passed;
    const regressed = a.overall_passed && !b.overall_passed;
    const rowStyle = improved ? 'background:#f0fdf4' : regressed ? 'background:#fef2f2' : '';
    return `<tr style="${{rowStyle}}">
      <td style="font-family:monospace;font-size:12px">${{id}}</td>
      <td><div class="q-text" title="${{esc(a.question||b.question||'')}}">${{esc(trunc(a.question||b.question||'',80))}}</div></td>
      <td><span class="badge badge-blue" style="font-size:10px">${{esc(a.category||b.category||'')}}</span></td>
      <td style="text-align:center">${{passA}}</td>
      <td style="text-align:center">${{passB}}</td>
      <td style="text-align:center;font-size:13px;font-weight:600">
        ${{improved ? '<span style="color:var(--green)">↑ improved</span>' : regressed ? '<span style="color:var(--red)">↓ regressed</span>' : '<span style="color:var(--muted)">—</span>'}}
      </td>
      <td><div class="tag-list">${{(b.failure_tags||[]).map(t=>`<span class="tag">${{esc(t)}}</span>`).join('')}}</div></td>
    </tr>`;
  }}).join('');

  const table = `
    <div class="cases-card">
      <div class="table-controls"><h2>Case Comparison: ${{vA}} → ${{vB}}</h2></div>
      <div style="overflow-x:auto">
        <table class="cases-table compare-table">
          <thead><tr>
            <th>ID</th><th>Question</th><th>Category</th>
            <th>${{vA}}</th><th>${{vB}}</th><th>Delta</th><th>Tags (${{vB}})</th>
          </tr></thead>
          <tbody>${{rows}}</tbody>
        </table>
      </div>
    </div>`;

  document.getElementById('compare-content').innerHTML = tiles + table;
}}

// ── Build run views ───────────────────────────────────────────────────────────
function buildViews() {{
  const container = document.getElementById('views');
  VERSIONS.forEach((v, i) => {{
    const div = document.createElement('div');
    div.id = 'view-' + v;
    div.className = 'view' + (i === 0 ? ' active' : '');
    div.innerHTML = `
      <div class="tiles">${{renderTiles(v)}}</div>
      <div class="charts-row">
        <div class="chart-card"><div class="chart-title">Score by Dimension</div><div class="chart-wrap"><canvas id="radar-${{v}}"></canvas></div></div>
        <div class="chart-card"><div class="chart-title">Pass Rate by Category</div><div class="chart-wrap"><canvas id="bar-${{v}}"></canvas></div></div>
        <div class="chart-card"><div class="chart-title">Score Trends Over Runs</div><div class="chart-wrap"><canvas id="trend-${{v}}"></canvas></div></div>
      </div>
      <div class="synthesis-card"><h2>Diagnostic Analysis</h2><div class="synthesis-body">${{md(RUNS[v].synthesis)}}</div></div>
      <div id="table-${{v}}"></div>`;
    container.appendChild(div);
  }});
}}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {{
  if (!VERSIONS.length) {{
    document.querySelector('main .container').innerHTML =
      '<p style="padding:60px;text-align:center;color:var(--muted)">No eval results found. Run <code>python run_evals.py run --prompt v1</code> first.</p>';
    return;
  }}
  buildNav();
  buildViews();
  buildCompareView();
  VERSIONS.forEach(v => {{
    renderRadar(v, `radar-${{v}}`);
    renderBar(v, `bar-${{v}}`);
    renderTrend(`trend-${{v}}`);
    renderTable(v, `table-${{v}}`);
  }});
}});
</script>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate eval dashboard HTML")
    parser.add_argument("--out", default="dashboard.html", help="Output file (default: dashboard.html)")
    args = parser.parse_args()

    runs = load_runs()
    if not runs:
        print("No result files found in results/. Run evals first.")
        return

    html = generate_html(runs)
    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard written to: {out}")
    print(f"Loaded {len(runs)} run(s): {', '.join(runs.keys())}")


if __name__ == "__main__":
    main()
