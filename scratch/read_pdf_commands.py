import pypdf
import re

def search_pdf(pdf_path, keywords, output_path):
    print(f"Searching PDF: {pdf_path}")
    reader = pypdf.PdfReader(pdf_path)
    print(f"Total pages: {len(reader.pages)}")
    
    results = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue
        
        # Look for pages with at least 2 keywords
        matches = [kw for kw in keywords if re.search(re.escape(kw), text, re.IGNORECASE)]
        if len(matches) >= 2:
            results.append((i + 1, matches, text))
            
    print(f"Found matches on {len(results)} pages. Writing to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        for page_num, matches, text in results:
            f.write("=" * 60 + "\n")
            f.write(f"Page {page_num} matches: {matches}\n")
            f.write("-" * 60 + "\n")
            f.write(text)
            f.write("\n\n")
            
if __name__ == "__main__":
    pdf_path = r"c:\Users\marconi\OneDrive - Science Tokyo\Python Scripts\libs\R6244-gpib-Control\6253-6254-ope-fow-00000184a01-j.pdf"
    output_path = r"c:\Users\marconi\OneDrive - Science Tokyo\Python Scripts\libs\R6244-gpib-Control\scratch\pdf_search_results_range.txt"
    # Search for R1 and レンジ
    search_pdf(pdf_path, ["R1", "レンジ"], output_path)
