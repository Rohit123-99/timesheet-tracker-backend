import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime, timedelta

def generate_weekly_pdf(filepath, start_date_str, end_date_str, tasks, metrics, chart_path=None):
    """Generates a professional PDF report."""
    
    doc = SimpleDocTemplate(filepath, pagesize=letter,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.alignment = 1 # Center
    
    subtitle_style = styles['Heading3']
    subtitle_style.alignment = 1 # Center
    
    normal_style = styles['Normal']
    
    # Custom tight style for summary
    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6
    )

    flowables = []

    # Title Page / Header
    flowables.append(Paragraph("Personal Work Timesheet Report", title_style))
    flowables.append(Spacer(1, 10))
    flowables.append(Paragraph(f"Week: {start_date_str} to {end_date_str}", subtitle_style))
    flowables.append(Spacer(1, 20))

    # Summary Section
    flowables.append(Paragraph("<b>Summary Section</b>", styles['Heading2']))
    flowables.append(Spacer(1, 10))
    
    flowables.append(Paragraph(f"<b>Total Hours Worked:</b> {metrics.get('total', 0):.1f}h", summary_style))
    flowables.append(Paragraph(f"<b>Target Hours / Day:</b> {metrics.get('target', 0):.1f}h", summary_style))
    flowables.append(Paragraph(f"<b>Weekly Average / Day:</b> {metrics.get('average', 0):.1f}h", summary_style))
    flowables.append(Spacer(1, 20))

    # Graph
    if chart_path and os.path.exists(chart_path):
        flowables.append(Paragraph("<b>Work Hours Distribution</b>", styles['Heading2']))
        flowables.append(Spacer(1, 10))
        img = Image(chart_path, width=400, height=300)
        flowables.append(img)
        flowables.append(Spacer(1, 20))

    # Task Table
    flowables.append(Paragraph("<b>Task Log</b>", styles['Heading2']))
    flowables.append(Spacer(1, 10))
    
    table_data = [['Date', 'Task', 'Hours', 'Notes']]
    for task in tasks:
        # Prevent very long notes breaking table
        notes = task.get('notes', '')
        if len(notes) > 50: notes = notes[:47] + '...'
        
        table_data.append([
            task.get('date', ''),
            task.get('task_name', ''),
            f"{task.get('hours', 0):.1f}h",
            notes
        ])

    table = Table(table_data, colWidths=[80, 150, 60, 240])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2E2E2E')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F9F9F9')),
        ('TEXTCOLOR', (0,1), (-1,-1), colors.black),
        ('ALIGN', (0,1), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#DDDDDD')),
        ('ALIGN', (2,0), (2,-1), 'RIGHT'), # Hours column right-aligned
    ]))
    
    flowables.append(table)

    # Build PDF
    doc.build(flowables)
