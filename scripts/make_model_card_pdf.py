"""Build and verify the current one-page jury model card."""
from model_card_content import ROOT,SECTIONS,SOURCES,HEADERS,ROWS,RESULT_NOTE
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from pypdf import PdfReader
styles={
 'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=24,leading=28,textColor=colors.HexColor('#17372b'),spaceAfter=5),
 'sub':ParagraphStyle('sub',fontName='Helvetica',fontSize=8,leading=11,textColor=colors.HexColor('#60776a'),spaceAfter=10),
 'h':ParagraphStyle('h',fontName='Helvetica-Bold',fontSize=9.3,leading=12,spaceBefore=8,spaceAfter=3,textColor=colors.HexColor('#375f42')),
 'p':ParagraphStyle('p',fontName='Helvetica',fontSize=8,leading=10.7,spaceAfter=4,textColor=colors.HexColor('#304858')),
 'small':ParagraphStyle('small',fontName='Helvetica',fontSize=7.2,leading=9.4,textColor=colors.HexColor('#52685d'))}
story=[]
def para(text,style='p'):story.append(Paragraph(text,styles[style]))
para('FRA WindLab | Model card','title')
para('AIW-AIRWAYS / Direction v2 + closure v1 / 30 October 2026 / Submission partial','sub')
para(SECTIONS[0][1])
para('Held-out DFLD direction quality','h')
table=Table([HEADERS]+ROWS,colWidths=[28,47,69,130,61,113],hAlign='LEFT')
table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f0e8')),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),7.2),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#dce5df'))]))
story.append(table);story.append(Spacer(1,5));para(RESULT_NOTE,'small')
for title,body in SECTIONS[1:]:para(title,'h');para(body)
para('Sources and reproduction','h')
para(' | '.join(f'<link href="{url}" color="#375f42">{label}</link>' for label,url in SOURCES),'small')
para('Full URLs, retrieval times, hashes, model coefficients, paired comparisons and prediction rows are downloadable from the dashboard. Reproduce direction fitting: model/train_dfld.py; audit: tests/direction-model.mjs. DFLD raw pages and aircraft identifiers are not redistributed. Numeric challenge rules: supplied FraAlliance case PDF.','small')
dest=ROOT/'dist/model-card.pdf'
SimpleDocTemplate(str(dest),pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=12*mm,bottomMargin=12*mm,title='FRA WindLab - DFLD model card',author='AIW-AIRWAYS').build(story)
assert len(PdfReader(dest).pages)==1,'Model card must fit exactly one A4 page'
print('Built and verified one-page model-card.pdf')
