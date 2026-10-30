"""Build current model-card HTML using the shared PDF content."""
from model_card_content import ROOT,SECTIONS,SOURCES,HEADERS,ROWS,RESULT_NOTE
from html import escape
parts=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FRA WindLab model card</title><style>body{font:14px/1.6 system-ui;color:#234036;background:#edf1ed;margin:0}main{max-width:880px;background:white;margin:30px auto;padding:36px}h1{font-size:30px}h2{font-size:18px;margin-top:26px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px;border-bottom:1px solid #dce5df;text-align:left}th{background:#edf3e9}a{color:#356646}.scroll{overflow:auto}@media print{body{font-size:9px}main{margin:0;padding:0}h2{font-size:12px;margin-top:12px}table{font-size:9px}th,td{padding:5px}}@media(max-width:600px){main{padding:18px;margin:0}}</style><main><a href="./">Dashboard</a> · <a href="model-card.pdf">One-page PDF</a><h1>FRA WindLab · Model card</h1><p>Direction v2 + closure v1 · 30 October 2026 · Submission partial</p>']
parts+=['<p>'+escape(SECTIONS[0][1])+'</p>','<h2>Held-out DFLD direction quality</h2><div class="scroll"><table>']
for i,row in enumerate([HEADERS]+ROWS):
 tag='th' if i==0 else 'td';parts.append('<tr>'+''.join('<'+tag+'>'+escape(x)+'</'+tag+'>' for x in row)+'</tr>')
parts+=['</table></div><p>'+escape(RESULT_NOTE)+'</p>']
for title,body in SECTIONS[1:]:parts+=['<h2>'+escape(title)+'</h2><p>'+escape(body)+'</p>']
parts+=['<h2>Sources</h2><p>'+' · '.join('<a href="'+escape(url,quote=True)+'">'+label+'</a>' for label,url in SOURCES)+'</p></main></html>']
(ROOT/'dist/model-card.html').write_text(''.join(parts),encoding='utf-8')
print('Updated HTML model card')
