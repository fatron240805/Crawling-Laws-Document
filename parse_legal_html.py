#!/usr/bin/env python3
"""
Parse Vietnamese legal HTML files (from thuvienphapluat.vn) into structured JSON chunks.
Usage: python3 parse_legal_html.py <input_folder> <output_folder>
"""

import os
import re
import json
import sys
from bs4 import BeautifulSoup

# ─── Helpers ──────────────────────────────────────────────────────────────────

ROMAN = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
    "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20,
    "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24, "XXV": 25,
    "XXVI": 26, "XXVII": 27, "XXVIII": 28, "XXIX": 29, "XXX": 30,
    "XXXI": 31, "XXXII": 32, "XXXIII": 33, "XXXIV": 34, "XXXV": 35,
    "XXXVI": 36, "XXXVII": 37, "XXXVIII": 38, "XXXIX": 39, "XL": 40,
    "XLI": 41, "XLII": 42, "XLIII": 43, "XLIV": 44, "XLV": 45,
}

CHU_DE_MAP = {
    # Simple keyword → chủ đề
    "phạm vi": "Quy định chung",
    "đối tượng áp dụng": "Quy định chung",
    "nguyên tắc": "Quy định chung",
    "giải thích": "Quy định chung",
    "quyền": "Quyền và nghĩa vụ",
    "nghĩa vụ": "Quyền và nghĩa vụ",
    "trách nhiệm": "Trách nhiệm pháp lý",
    "hợp đồng": "Hợp đồng",
    "bồi thường": "Bồi thường thiệt hại",
    "tài sản": "Tài sản",
    "sở hữu": "Quyền sở hữu",
    "thừa kế": "Thừa kế",
    "hôn nhân": "Hôn nhân và gia đình",
    "gia đình": "Hôn nhân và gia đình",
    "lao động": "Lao động",
    "hình phạt": "Hình phạt",
    "tội": "Tội phạm",
    "xử phạt": "Xử phạt",
    "hàng hải": "Hàng hải",
    "tàu biển": "Tàu biển",
    "thuyền": "Thuyền viên",
    "cảng": "Cảng biển",
    "vận chuyển": "Vận chuyển hàng hóa",
    "đào tạo": "Đào tạo nghề nghiệp",
    "thuế": "Thuế",
    "doanh nghiệp": "Doanh nghiệp",
    "môi trường": "Môi trường",
    "đất đai": "Đất đai",
    "nhân thân": "Quyền nhân thân",
    "hiến": "Quyền nhân thân",
    "pháp nhân": "Pháp nhân",
    "đại diện": "Đại diện",
    "thời hiệu": "Thời hiệu",
    "thời hạn": "Thời hạn",
    "giám hộ": "Giám hộ",
    "cư trú": "Cư trú",
    "cá nhân": "Cá nhân",
    "thông báo": "Quy định chung",
    "xử lý": "Xử lý vi phạm",
    "tranh chấp": "Giải quyết tranh chấp",
    "giải quyết": "Giải quyết tranh chấp",
    "bảo hiểm": "Bảo hiểm",
    "bảo lãnh": "Bảo lãnh",
    "thế chấp": "Thế chấp",
    "cầm cố": "Cầm cố",
    "cho thuê": "Cho thuê",
    "mua bán": "Mua bán tài sản",
    "tặng cho": "Tặng cho tài sản",
    "vay": "Vay tài sản",
    "ủy quyền": "Ủy quyền",
    "chiếm hữu": "Chiếm hữu",
}

def infer_chu_de(ten_dieu: str) -> str:
    """Infer topic from article title using keyword matching."""
    title_lower = ten_dieu.lower()
    for kw, chu_de in CHU_DE_MAP.items():
        if kw in title_lower:
            return chu_de
    return "Quy định chung"


def clean_text(text: str) -> str:
    """Normalize whitespace."""
    return re.sub(r'\s+', ' ', text).strip()


def roman_to_int(r: str) -> int:
    return ROMAN.get(r.strip().upper(), 0)


def extract_so_hieu(div) -> str:
    """Extract law number like 91/2015/QH13 from header table."""
    for td in div.find_all('td'):
        t = clean_text(td.get_text())
        m = re.search(r'(\d+/\d{4}/\w+)', t)
        if m:
            return m.group(1)
    return ""


def extract_van_ban_name(soup) -> str:
    """Extract law name from page title."""
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
        # e.g. "Bộ luật dân sự 2015 số 91/2015/QH13 áp dụng 2025 mới nhất"
        m = re.match(r'^(.+?)\s+(?:số\s+\d|áp dụng|\d{4}\s)', title, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # Fallback: take up to year
        m2 = re.match(r'^(.+?\d{4})', title)
        if m2:
            return m2.group(1).strip()
    return "Không xác định"


def make_prefix(van_ban: str, chuong_label: str, ten_chuong: str) -> str:
    """Build the bracket prefix for text_to_embed."""
    return f"[{van_ban} - {ten_chuong}]"


def make_chunk_id(van_ban: str, chuong_num: str, dieu_num: int, khoan: str, muc_num: str) -> str:
    """
    Build chunk_id like: blds_ci_d1  /  blds_ci_d2_k1  /  blhs_cii_m1_d5_k3
    Abbreviate law name to ~4 chars.
    """
    # abbreviate law name
    abbr = re.sub(r'[^a-zA-Z0-9]', '', van_ban.lower().replace('bộ luật', 'bl').replace('luật', 'l'))[:8]
    abbr = re.sub(r'\s+', '', abbr)

    # chuong part
    c_part = f"c{chuong_num.lower()}" if chuong_num else "c"

    # muc part
    m_part = f"_m{muc_num}" if muc_num else ""

    # dieu part
    d_part = f"_d{dieu_num}" if dieu_num else ""

    # khoan part
    k_part = f"_k{khoan}" if khoan else ""

    return f"{abbr}_{c_part}{m_part}{d_part}{k_part}"


def parse_html_file(filepath: str):
    """Parse one HTML file and return list of chunk dicts."""
    with open(filepath, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    van_ban = extract_van_ban_name(soup)
    nam_ban_hanh = 2015  # from filename convention; could also parse from content

    div = soup.find('div', {'id': 'divContentDoc'})
    if not div:
        print(f"  [WARN] No content div found in {filepath}")
        return []

    so_hieu = extract_so_hieu(div)

    # ── Build an ordered sequence of structural nodes ──────────────────────
    # We walk through all anchor tags in document order and pick out the
    # meaningful ones: phan/chuong, muc, dieu, khoan, diem
    anchors = div.find_all('a', attrs={'name': True})

    # Index anchors by name for quick lookup
    anchor_map = {}
    for a in anchors:
        anchor_map[a['name']] = a

    # Collect structural anchors in order (skip _name and tvpllink_ variants)
    structural = []
    seen = set()
    for a in anchors:
        n = a['name']
        if n in seen:
            continue
        seen.add(n)
        # Only keep structural ones
        if re.match(r'^(chuong_\d|muc_\d|dieu_\d)', n) and '_name' not in n:
            structural.append((n, a))
        elif re.match(r'^khoan_\d', n):
            structural.append((n, a))

    # ── Pre-collect chuong/muc/dieu name texts ─────────────────────────────
    def get_anchor_text(name):
        a = anchor_map.get(name)
        if not a:
            return ""
        p = a.find_parent('p') or a.find_parent()
        return clean_text(p.get_text()) if p else ""

    def get_name_text(name):
        """Get the _name sibling anchor text."""
        a = anchor_map.get(name + "_name")
        if not a:
            return ""
        p = a.find_parent('p') or a.find_parent()
        return clean_text(p.get_text()) if p else ""

    # ── Build phan and chuong lookup ───────────────────────────────────────
    # chuong_1, chuong_2_1 etc. can be "Phần" or "Chương"
    phan_map = {}   # anchor_name -> (phan_label, phan_name)
    chuong_map = {} # anchor_name -> (chuong_label, ten_chuong)

    for n, a in structural:
        if re.match(r'^chuong_', n) and '_name' not in n:
            raw = get_anchor_text(n)
            name_raw = get_name_text(n)
            # Determine if it's Phần or Chương
            if re.search(r'Phần', raw, re.IGNORECASE) or re.search(r'ph[aầ]n', raw, re.IGNORECASE):
                phan_map[n] = (raw, name_raw)
            else:
                # Extract roman numeral
                m = re.search(r'Chương\s+([IVXLCDM]+)', raw, re.IGNORECASE)
                roman = m.group(1) if m else ""
                full_name = f"Chương {roman}. {name_raw}" if roman and name_raw else raw
                chuong_map[n] = (roman, full_name)

    # ── Now walk the document paragraph by paragraph ───────────────────────
    # We'll track state as we go through paragraphs
    state = {
        "chuong_label": "",
        "ten_chuong": "",
        "muc_label": "",
        "ten_muc": "",
        "dieu_num": 0,
        "ten_dieu": "",
    }

    chunks = []
    dieu_paragraphs = []  # buffer for current article body paragraphs
    current_khoan = None
    current_khoan_text = []

    def flush_khoan():
        nonlocal current_khoan, current_khoan_text
        if current_khoan is not None and current_khoan_text:
            body = " ".join(current_khoan_text).strip()
            if body:
                emit_chunk(current_khoan, body)
        current_khoan = None
        current_khoan_text = []

    def flush_dieu_no_khoan():
        """If article has no khoản, emit full body as one chunk."""
        if dieu_paragraphs:
            body = " ".join(dieu_paragraphs).strip()
            if body:
                emit_chunk(None, body)
        dieu_paragraphs.clear()

    def emit_chunk(khoan: str | None, body: str):
        cid = make_chunk_id(
            van_ban,
            state["chuong_label"],
            state["dieu_num"],
            khoan or "",
            state["muc_label"],
        )
        prefix = make_prefix(van_ban, state["chuong_label"], state["ten_chuong"])
        ten_dieu_clean = state["ten_dieu"]

        if khoan:
            text_to_embed = (
                f"{prefix} "
                f"Điều {state['dieu_num']}. {ten_dieu_clean}. "
                f"Khoản {khoan}. {body}"
            )
        else:
            text_to_embed = (
                f"{prefix} "
                f"Điều {state['dieu_num']}. {ten_dieu_clean}. {body}"
            )

        chunk = {
            "chunk_id": cid,
            "text_to_embed": clean_text(text_to_embed),
            "metadata": {
                "van_ban": van_ban,
                "so_hieu": so_hieu,
                "nam_ban_hanh": nam_ban_hanh,
                "chuong": state["chuong_label"],
                "ten_chuong": state["ten_chuong"],
                "dieu": state["dieu_num"],
                "ten_dieu": ten_dieu_clean,
                "khoan": khoan or "",
                "chu_de": infer_chu_de(ten_dieu_clean),
                "muc": state["muc_label"],
                "ten_muc": state["ten_muc"],
            }
        }
        chunks.append(chunk)

    # ── Walk all paragraphs in the content div ─────────────────────────────
    # We iterate over all <p> tags; anchor names inside them tell us
    # what structural element we're entering.

    all_paras = div.find_all('p')
    # Build a set of <p> -> anchor names
    para_anchors = {}
    for a in anchors:
        p = a.find_parent('p')
        if p:
            para_anchors.setdefault(id(p), []).append(a['name'])

    for para in all_paras:
        pid = id(para)
        anch_names = para_anchors.get(pid, [])
        text = clean_text(para.get_text())

        # ── Structural transitions ─────────────────────────────────────────
        hit_chuong = None
        hit_muc = None
        hit_dieu = None

        for n in anch_names:
            if '_name' in n or n.startswith('tvpllink') or n.startswith('tc_') or n.startswith('loai_'):
                continue
            if re.match(r'^chuong_\d', n):
                hit_chuong = n
            elif re.match(r'^muc_\d', n):
                hit_muc = n
            elif re.match(r'^dieu_\d', n):
                hit_dieu = n

        # Process chuong transition
        if hit_chuong:
            flush_khoan()
            flush_dieu_no_khoan()
            info = chuong_map.get(hit_chuong)
            if info:
                state["chuong_label"], state["ten_chuong"] = info
                state["muc_label"] = ""
                state["ten_muc"] = ""
            # (if it's a Phần, we don't update chuong)
            continue

        # Process muc transition
        if hit_muc:
            flush_khoan()
            flush_dieu_no_khoan()
            # Extract muc number
            m = re.search(r'Mục\s+(\d+)\.?\s*(.*)', text, re.IGNORECASE)
            if m:
                state["muc_label"] = m.group(1)
                state["ten_muc"] = f"Mục {m.group(1)}. {clean_text(get_name_text(hit_muc))}"
            else:
                state["muc_label"] = re.sub(r'\D', '', hit_muc.split('_')[1]) if '_' in hit_muc else ""
                state["ten_muc"] = text
            continue

        # Process dieu transition
        if hit_dieu:
            flush_khoan()
            flush_dieu_no_khoan()
            # Parse article number and name
            m = re.search(r'Điều\s+(\d+)\.?\s*(.*)', text, re.IGNORECASE)
            if m:
                state["dieu_num"] = int(m.group(1))
                state["ten_dieu"] = clean_text(m.group(2))
            else:
                num_m = re.search(r'dieu_(\d+)', hit_dieu)
                state["dieu_num"] = int(num_m.group(1)) if num_m else 0
                state["ten_dieu"] = text
            continue

        # ── Content paragraphs ─────────────────────────────────────────────
        if state["dieu_num"] == 0:
            continue  # skip preamble before any Điều

        if not text:
            continue

        # Check if paragraph starts a khoản (e.g. "1. ...", "2. ...")
        khoan_match = re.match(r'^(\d+)\.\s+(.+)', text)
        if khoan_match:
            flush_khoan()
            current_khoan = khoan_match.group(1)
            current_khoan_text = [khoan_match.group(2)]
        elif current_khoan is not None:
            # Continuation of current khoan (could be điểm a, b, c...)
            current_khoan_text.append(text)
        else:
            # No khoản yet — body paragraph for this article
            dieu_paragraphs.append(text)

    # Flush last article
    flush_khoan()
    flush_dieu_no_khoan()

    return chunks


def process_folder(input_folder: str, output_folder: str):
    os.makedirs(output_folder, exist_ok=True)
    all_chunks = []

    html_files = sorted([f for f in os.listdir(input_folder) if f.endswith('.html')])
    print(f"Found {len(html_files)} HTML file(s) in '{input_folder}'")

    for fname in html_files:
        fpath = os.path.join(input_folder, fname)
        print(f"\nProcessing: {fname}")
        chunks = parse_html_file(fpath)
        print(f"  → {len(chunks)} chunks extracted")

        # Write individual JSON
        out_name = os.path.splitext(fname)[0] + ".json"
        out_path = os.path.join(output_folder, out_name)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        print(f"  → Saved to {out_path}")

        all_chunks.extend(chunks)

    # Write combined JSON
    combined_path = os.path.join(output_folder, "_combined_all.json")
    with open(combined_path, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Combined file ({len(all_chunks)} total chunks): {combined_path}")

    return all_chunks


# ─── CẤU HÌNH ĐƯỜNG DẪN ───────────────────────────────────────────────────────

# Thay đổi hai đường dẫn dưới đây theo thư mục thực tế trên máy của bạn.
# Nên sử dụng raw string (thêm 'r' phía trước) để tránh lỗi ký tự đặc biệt (\) trên Windows.
INPUT_DIR = r"D:\BACHELOR\JUNIOR\TERM2\CSC15011 - INTRODUCTION TO STATISTICAL LINGUISTICS AND APPLICATION\PAPER\output"
OUTPUT_DIR = r"D:\BACHELOR\JUNIOR\TERM2\CSC15011 - INTRODUCTION TO STATISTICAL LINGUISTICS AND APPLICATION\PAPER\output_json"

if __name__ == "__main__":
    import sys # Bạn có thể xóa import sys ở đầu file nếu không dùng đến nữa
    
    print(f"Bắt đầu quá trình phân tách dữ liệu:")
    print(f"  - Thư mục nguồn (Input) : {INPUT_DIR}")
    print(f"  - Thư mục đích (Output) : {OUTPUT_DIR}\n")
    
    process_folder(INPUT_DIR, OUTPUT_DIR)