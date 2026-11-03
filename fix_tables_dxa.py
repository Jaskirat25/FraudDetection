"""
Script to apply exact 3.48-inch column-width formatting to all tables and figure boxes
in IEEE_Project_Report_IDShield_Draft.docx:
- Fixed table layout (w:tblLayout fixed)
- Explicit table width (w:tblW 5000 dxa = 3.47 in)
- Explicit cell width on EVERY CELL (w:tcW matching exact column dxa)
- Small inner padding (w:tcMar)
- cantSplit on every row
- tblHeader on header row
- Clean single line-spacing (1.0) and 0 pt before / 1 pt after in all table cells
"""

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def apply_table_formatting(table, col_widths_dxa, alignment=WD_TABLE_ALIGNMENT.CENTER):
    """
    Apply fixed layout and explicit per-cell widths to a table so it NEVER overflows.
    col_widths_dxa: list of integers representing column widths in dxa.
    """
    total_w_dxa = sum(col_widths_dxa)
    table.alignment = alignment
    table.autofit = False
    
    # 1. Table Properties
    tblPr = table._tbl.tblPr
    
    # Set fixed layout
    layout_elm = tblPr.find(qn('w:tblLayout'))
    if layout_elm is None:
        layout_elm = OxmlElement('w:tblLayout')
        tblPr.append(layout_elm)
    layout_elm.set(qn('w:type'), 'fixed')
    
    # Set explicit table width
    tblW_elm = tblPr.find(qn('w:tblW'))
    if tblW_elm is None:
        tblW_elm = OxmlElement('w:tblW')
        tblPr.append(tblW_elm)
    tblW_elm.set(qn('w:w'), str(total_w_dxa))
    tblW_elm.set(qn('w:type'), 'dxa')
    
    # Table cell margins (padding) in dxa: top/bottom=25, left/right=35
    cell_mar = parse_xml(
        f'<w:tblCellMar {nsdecls("w")}>'
        f'  <w:top w:w="25" w:type="dxa"/>'
        f'  <w:bottom w:w="25" w:type="dxa"/>'
        f'  <w:left w:w="35" w:type="dxa"/>'
        f'  <w:right w:w="35" w:type="dxa"/>'
        f'</w:tblCellMar>'
    )
    # Remove existing tblCellMar if any
    old_mar = tblPr.find(qn('w:tblCellMar'))
    if old_mar is not None:
        tblPr.remove(old_mar)
    tblPr.append(cell_mar)
    
    # 2. Grid Columns in tblGrid
    tblGrid = table._tbl.tblGrid
    if tblGrid is not None:
        # Clear existing grid cols
        for gc in list(tblGrid):
            tblGrid.remove(gc)
        for w in col_widths_dxa:
            gc = OxmlElement('w:gridCol')
            gc.set(qn('w:w'), str(w))
            tblGrid.append(gc)
            
    # 3. Apply width to EVERY cell in EVERY row
    for row_idx, row in enumerate(table.rows):
        trPr = row._tr.get_or_add_trPr()
        
        # cantSplit on every row
        if trPr.find(qn('w:cantSplit')) is None:
            trPr.append(OxmlElement('w:cantSplit'))
            
        # tblHeader on header row
        if row_idx == 0 and trPr.find(qn('w:tblHeader')) is None:
            trPr.append(OxmlElement('w:tblHeader'))
            
        for col_idx, cell in enumerate(row.cells):
            tcPr = cell._tc.get_or_add_tcPr()
            
            # Explicit tcW
            tcW = tcPr.find(qn('w:tcW'))
            if tcW is None:
                tcW = OxmlElement('w:tcW')
                tcPr.append(tcW)
            tcW.set(qn('w:w'), str(col_widths_dxa[col_idx]))
            tcW.set(qn('w:type'), 'dxa')
            
            # Cell paragraph formatting
            for p in cell.paragraphs:
                p.paragraph_format.line_spacing = 1.0
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(1)

def format_all_tables_in_doc(src_path, dst_path):
    doc = docx.Document(src_path)
    print(f"Loaded {src_path} with {len(doc.tables)} tables.")
    
    # Column width allocations for 5000 dxa total (~3.47 inches):
    # Table 0: Author Block (Header, across 1 column = 7.25 in = 10440 dxa)
    # 3 cols of 3480 dxa each
    apply_table_formatting(doc.tables[0], [3480, 3480, 3480])
    
    # Figure Box 1 (index 1) -> 5000 dxa
    apply_table_formatting(doc.tables[1], [5000])
    
    # Table I: Technology Stack (index 2) -> 3 cols: [1400, 1600, 2000] = 5000 dxa
    apply_table_formatting(doc.tables[2], [1400, 1600, 2000])
    
    # Figure Box 2 (index 3) -> 5000 dxa
    apply_table_formatting(doc.tables[3], [5000])
    
    # Figure Box 3 (index 4) -> 5000 dxa
    apply_table_formatting(doc.tables[4], [5000])
    
    # Figure Box 4 (index 5) -> 5000 dxa
    apply_table_formatting(doc.tables[5], [5000])
    
    # Table II: Attack Vector Benchmark (index 6) -> 6 cols:
    # [380, 1720, 600, 450, 650, 1200] = 5000 dxa
    apply_table_formatting(doc.tables[6], [380, 1720, 600, 450, 650, 1200])
    
    # Table III: Confusion Matrix (index 7) -> 6 cols:
    # [1800, 640, 640, 640, 640, 640] = 5000 dxa
    apply_table_formatting(doc.tables[7], [1800, 640, 640, 640, 640, 640])
    
    # Table IV: Layer Ablation (index 8) -> 4 cols:
    # [1450, 650, 900, 2000] = 5000 dxa
    apply_table_formatting(doc.tables[8], [1450, 650, 900, 2000])
    
    # Figure Box 5 (index 9) -> 5000 dxa
    apply_table_formatting(doc.tables[9], [5000])
    
    # Table V: Latency Profile (index 10) -> 4 cols:
    # [1600, 1650, 1050, 700] = 5000 dxa
    apply_table_formatting(doc.tables[10], [1600, 1650, 1050, 700])
    
    # Figure Box 6 (index 11) -> 5000 dxa
    apply_table_formatting(doc.tables[11], [5000])
    
    doc.save(dst_path)
    print(f"All tables successfully formatted with exact fixed dxa widths to {dst_path}!")

if __name__ == "__main__":
    src = r"c:\Users\HP\Desktop\FraudDetection\IEEE_Project_Report_IDShield_Draft.docx"
    dst = r"c:\Users\HP\Desktop\FraudDetection\IEEE_Project_Report_IDShield_Formatted.docx"
    format_all_tables_in_doc(src, dst)
