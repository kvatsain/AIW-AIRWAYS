"""Build the one-page jury model card. Optional dependencies: reportlab, pypdf."""
from pathlib import Path
import json
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
report=json.loads((ROOT/'dist/data/deliverables.json').read_text())
dest=ROOT/'dist/model-card.pdf'
styles={
    'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=25,leading=29,textColor=colors.HexColor('#172b3a'),spaceAfter=5),
    'sub':ParagraphStyle('sub',fontName='Helvetica',fontSize=9,leading=13,textColor=colors.HexColor('#647b7d'),spaceAfter=10),
    'h':ParagraphStyle('h',fontName='Helvetica-Bold',fontSize=10,leading=14,spaceBefore=9,spaceAfter=4,textColor=colors.HexColor('#375f42')),
    'p':ParagraphStyle('p',fontName='Helvetica',fontSize=8.7,leading=12,spaceAfter=5,textColor=colors.HexColor('#304858')),
    'small':ParagraphStyle('small',fontName='Helvetica',fontSize=7.3,leading=10,textColor=colors.HexColor('#61747b')),
}
story=[]
def para(text,style='p'):
    story.append(Paragraph(text,styles[style]))

para('FRA WindLab | Model card','title')
para('AIW-AIRWAYS / FraAlliance AI Week 2026 / Audited 30 October 2026','sub')
para('<b>Status: research prototype; challenge submission partial.</b> Targets are weather-derived proxies, not airport operating logs. No actual-operations accuracy or validated switch-time score is available. Jury dates are pending.')
para('Purpose and outputs','h')
para('Hourly forecasts through 48h: RWY18 wind-usability probability, OD07/25 probabilities, predicted direction, direction score, and the next predicted change hour. Scores are not calibrated operational certainty. A first-hour switch is included; no crossing means none signalled within the window. Intermediate leads reuse the nearest 1/6/24/48h model.')
para('Held-out direction-proxy quality','h')
rows=[['Lead','Test hours','ML accuracy','Rule baseline','Gain (pp)','ML / rules Brier']]
for h in report['horizons']:
    t=h['targets']['od07']
    rows.append([f'{h["horizonHours"]}h',f'{h["testRows"]:,}',f'{t["modelAccuracy"]:.2%}',f'{t["rulesAccuracy"]:.2%}',f'{t["accuracyGainPercentagePoints"]:+.2f}',f'{t["modelBrier"]:.4f} / {t["rulesBrier"]:.4f}'])
table=Table(rows,colWidths=[31,57,76,76,59,140],hAlign='LEFT')
table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f0e8')),('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#304858')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),('LINEBELOW',(0,0),(-1,-1),0.4,colors.HexColor('#dce5df'))]))
story.append(table);story.append(Spacer(1,5))
para('Lower Brier is better. ML improves direction probability error at every lead; classification improves at 1h/6h and loses at 24h/48h. Frozen-model scores were independently recomputed from raw inputs; no fitting or test-driven tuning in this revision.','small')
para('RWY18 closure detection and alert trade-off','h')
para('At 50%, every model detects <b>0/5</b> positive test hours. Only 28-34 positive training hours and 0-1 validation positives exist. For scheduled hours at 1h, <b>catch more</b> (1%) detects 3/3 with 116 false alarms; <b>reduce false alarms</b> (10%) detects 0/3 with 4 false alarms. Both override on forecast wind-limit exceedance. These are fixed sensitivity choices on a known holdout; rare, correlated hours do not establish reliable closure skill.')
para('Data, learning and key drivers','h')
para('49,600 EDDF METAR reports (Jan 2024-Oct 2026) from IEM; archived DWD ICON forecasts via Open-Meteo Previous Runs. Latest METAR from NOAA AWC; current direction context from Umwelthaus/DFS. Separate L2 logistic classifiers use forecast wind vectors, speed/gusts, runway components, origin wind/direction, 3h trends and seasonal/hour cycles. Scaling uses training rows; regularization uses validation Brier. Missing/variable direction is excluded. Missing gust uses sustained wind; only 1.36% of reports explicitly contain gusts.')
para('Evaluation chronology and availability limits','h')
para('Train: 2024-2025. Validation: 4 Jan-31 Mar 2026. Test: 4 Apr-29 Oct 2026; 72h split gaps. Features use origin-or-earlier observations without future interpolation, at most 40min old. Forecast archive offsets are 24/48/72h and predate origin by at least 18h. Exact run delivery and METAR arrival timestamps are unavailable. Live ICON is fresher than backtest inputs. Retrospective replay is not evidence of an as-issued forecast.')
para('Challenge rules and airport schedule','h')
para('RWY18: sustained tailwind >=15 kt or gust crosswind >40 kt restricts use. OD: >=10 kt tailwind forces a switch; smaller adverse wind must persist >30min. True challenge headings: 180/070/250 degrees. Fraport public landing guidance uses a different 5 kt threshold. Scheduled flights: 05:00-23:00 Europe/Berlin, with DST. Night restrictions are separate from wind; conditional delays before midnight and statutory exemptions do not imply individual permission.')
para('Submission and sources','h')
para('Repository: <link href="https://github.com/kvatsain/AIW-AIRWAYS" color="#375f42">github.com/kvatsain/AIW-AIRWAYS</link>. Reproduce: model/audit_deliverables.py; replay: model/predict.py --issue-time ... --hours 48. Supply jury dates and verified actual direction/RWY18 histories; freeze forecasts prospectively and score operational outcomes separately.','small')
para('<link href="https://mesonet.agron.iastate.edu/request/download.phtml">IEM METAR</link> | <link href="https://open-meteo.com/en/docs/previous-runs-api">Open-Meteo Previous Runs</link> | <link href="https://open-meteo.com/en/docs/dwd-api">DWD ICON</link> | <link href="https://aviationweather.gov/data/api/">NOAA AWC</link> | <link href="https://www.umwelthaus.org/fluglaerm/anwendungen-service/aktuelle-betriebsrichtung-und-prognose/">Umwelthaus / DFS</link> | <link href="https://www.fraport.com/en/sustainability/dialog-with-neighbors/noise-and-air/flight-operations/runway-system-and-operating-hours.html">Fraport hours</link>. Numeric rules: user-supplied FraAlliance case PDF, section 3. Full sources, metrics and limitations are in the repository and dashboard.','small')
doc=SimpleDocTemplate(str(dest),pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=13*mm,bottomMargin=12*mm,title='FRA WindLab - one-page model card',author='AIW-AIRWAYS')
doc.build(story)
assert len(PdfReader(dest).pages)==1,'Model card must fit exactly one A4 page'
print('Built and verified one-page model-card.pdf')
