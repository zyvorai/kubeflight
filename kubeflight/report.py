from __future__ import annotations
import html,json
from .models import Assessment
_ORDER={'critical':0,'high':1,'medium':2,'low':3,'info':4}

def text_report(a:Assessment)->str:
 d=a.to_dict(); lines=[f"KubeFlight — {d['decision']}",f"Safety score: {d['score']}/100",f"Resources: {d['resources']}  Findings: {len(d['findings'])}",f"Estimated monthly workload cost: ${d['monthly_cost']:.2f}"]
 if d['cost_delta'] is not None:lines.append(f"Cost delta: ${d['cost_delta']:+.2f}")
 lines.append("")
 for f in sorted(d['findings'],key=lambda x:_ORDER[x['severity']]):
  lines.append(f"[{f['severity'].upper():8}] {f['category']:12} {f['resource']} — {f['title']}")
  lines.append(f"           ↳ {f['recommendation']}")
 if d['schedule']:
  lines += ["","Scheduling:"]
  for s in d['schedule']:lines.append(f"  {'✓' if s['schedulable'] else '✕'} {s['workload']}: {len(s['placements'])}/{s['replicas']} replicas placed on {', '.join(s['placements']) or 'none'}")
 if d['blast_radius']: lines += ["",f"Blast radius ({len(d['blast_radius'])}): "+", ".join(d['blast_radius'])]
 return "\n".join(lines)+"\n"

def json_report(a:Assessment)->str:return json.dumps(a.to_dict(),indent=2)+"\n"

def markdown_report(a:Assessment)->str:
 d=a.to_dict(); icon='✅' if d['decision']=='SAFE TO DEPLOY' else ('⚠️' if d['decision']=='REVIEW REQUIRED' else '⛔')
 lines=[f"## ✈️ KubeFlight — {icon} {d['decision']}","",f"**Safety score:** {d['score']}/100 · **Resources:** {d['resources']} · **Cost:** ${d['monthly_cost']:.2f}/mo","", "| Severity | Category | Resource | Finding |","|---|---|---|---|"]
 for f in sorted(d['findings'],key=lambda x:_ORDER[x['severity']])[:25]:lines.append(f"| {f['severity'].upper()} | {f['category']} | `{f['resource']}` | {f['title']} |")
 if d['blast_radius']:lines += ["",f"**Blast radius:** {len(d['blast_radius'])} dependent resource(s)."]
 lines += ["","_KubeFlight is a preflight simulator, not a substitute for Kubernetes admission controls or production validation._"]
 return "\n".join(lines)+"\n"

def sarif_report(a:Assessment)->str:
 d=a.to_dict(); rules={}; results=[]
 level={'critical':'error','high':'error','medium':'warning','low':'note','info':'note'}
 for f in d['findings']:
  rules.setdefault(f['id'],{"id":f['id'],"shortDescription":{"text":f['title']},"help":{"text":f['recommendation']}})
  results.append({"ruleId":f['id'],"level":level[f['severity']],"message":{"text":f"{f['resource']}: {f['title']}. {f['evidence']}"}})
 sarif={"version":"2.1.0","$schema":"https://json.schemastore.org/sarif-2.1.0.json","runs":[{"tool":{"driver":{"name":"KubeFlight","informationUri":"https://github.com/zyvorai/kubeflight","rules":list(rules.values())}},"results":results}]}
 return json.dumps(sarif,indent=2)+"\n"

def html_report(a:Assessment)->str:
 d=a.to_dict(); rows="".join(f"<tr><td><span class='sev {html.escape(f['severity'])}'>{html.escape(f['severity'])}</span></td><td>{html.escape(f['category'])}</td><td><code>{html.escape(f['resource'])}</code></td><td><b>{html.escape(f['title'])}</b><br><small>{html.escape(f['evidence'])}</small><br><em>{html.escape(f['recommendation'])}</em></td></tr>" for f in sorted(d['findings'],key=lambda x:_ORDER[x['severity']]))
 sched="".join(f"<li>{'✓' if s['schedulable'] else '✕'} <code>{html.escape(s['workload'])}</code> — {len(s['placements'])}/{s['replicas']} placed</li>" for s in d['schedule'])
 return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>KubeFlight report</title><style>*{{box-sizing:border-box}}body{{font:15px -apple-system,BlinkMacSystemFont,"SF Pro Text",Segoe UI,sans-serif;max-width:1180px;margin:0 auto;padding:64px 28px;color:#1d1d1f;background:#fbfbfd}}h1{{font-size:56px;letter-spacing:-.04em;margin:0}}.hero{{padding:52px 0}}.score{{font-size:96px;font-weight:700;letter-spacing:-.06em}}.card{{background:white;border-radius:24px;padding:28px;margin:20px 0;box-shadow:0 10px 40px #0000000a}}table{{width:100%;border-collapse:collapse}}td{{padding:14px;border-bottom:1px solid #eee;vertical-align:top}}small{{color:#6e6e73}}em{{color:#424245}}code{{background:#f5f5f7;padding:2px 5px;border-radius:6px}}.sev{{font-weight:700;text-transform:uppercase;font-size:11px}}@media(max-width:700px){{h1{{font-size:42px}}.score{{font-size:72px}}td:nth-child(2),td:nth-child(3){{display:none}}}}</style></head><body><div class="hero"><h1>KubeFlight</h1><div class="score">{d['score']}</div><h2>{html.escape(d['decision'])}</h2><p>{d['resources']} resources · ${d['monthly_cost']:.2f}/month normalized estimate · Kubernetes {html.escape(d['target_kubernetes'])}</p></div><div class="card"><h2>Scheduling</h2><ul>{sched or '<li>No cluster snapshot supplied</li>'}</ul></div><div class="card"><h2>Findings</h2><table>{rows or '<tr><td>No findings.</td></tr>'}</table></div></body></html>'''
