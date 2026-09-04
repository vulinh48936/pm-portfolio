"""Ticker metadata (name, sector) and the canonical order of TICKERS_FTSE.

TICKERS_FTSE is the single definition of the basket: the daily job fetches exactly these
tickers and index_build lays out the benchmark columns in this order.
"""


# Ticker -> company name and sector

TICKER_META: dict[str, dict] = {
    # Banks
    "BID": {"name": "BIDV",           "sector": "Ngân hàng"},
    "VCB": {"name": "Vietcombank",     "sector": "Ngân hàng"},
    "STB": {"name": "Sacombank",       "sector": "Ngân hàng"},
    "SHB": {"name": "SHB",            "sector": "Ngân hàng"},
    # Real estate
    "VIC": {"name": "Vingroup",        "sector": "Bất động sản"},
    "VHM": {"name": "Vinhomes",        "sector": "Bất động sản"},
    "KDH": {"name": "Khang Điền",      "sector": "Bất động sản"},
    "NVL": {"name": "Novaland",        "sector": "Bất động sản"},
    "VRE": {"name": "Vincom Retail",   "sector": "Bất động sản"},
    "KBC": {"name": "KCN Kinh Bắc",   "sector": "Bất động sản"},
    # Technology
    "FPT": {"name": "FPT Corp",        "sector": "Công nghệ"},
    # Steel and materials
    "HPG": {"name": "Hòa Phát",        "sector": "Thép & vật liệu"},
    # Oil and gas
    "BSR": {"name": "Lọc Hóa Dầu Bình Sơn", "sector": "Dầu khí"},
    # Chemicals
    "DGC": {"name": "Hóa chất Đức Giang", "sector": "Hóa chất"},
    # Utilities
    "GEE": {"name": "GEE",            "sector": "Tiện ích"},
    # Industrials
    "GEX": {"name": "GELEX",          "sector": "Công nghiệp"},
    # Consumer
    "MSN": {"name": "Masan",           "sector": "Tiêu dùng"},
    "VNM": {"name": "Vinamilk",        "sector": "Tiêu dùng"},
    # Brokers
    "SSI": {"name": "SSI Securities",  "sector": "Chứng khoán"},
    "VCI": {"name": "VCI",            "sector": "Chứng khoán"},
    "VIX": {"name": "VIX Securities",  "sector": "Chứng khoán"},
    "VND": {"name": "VNDIRECT",        "sector": "Chứng khoán"},
    # Airlines
    "VJC": {"name": "Vietjet Air",     "sector": "Hàng không"},
    # Additional FTSE members used by the dynamic universe
    "BVH": {"name": "Bảo Việt",          "sector": "Bảo hiểm"},
    "DIG": {"name": "DIC Corp",          "sector": "Bất động sản"},
    "DPM": {"name": "Đạm Phú Mỹ",        "sector": "Hóa chất"},
    "EIB": {"name": "Eximbank",          "sector": "Ngân hàng"},
    "FTS": {"name": "FPTS",              "sector": "Chứng khoán"},
    "HAG": {"name": "Hoàng Anh Gia Lai", "sector": "Nông nghiệp"},
    "HDB": {"name": "HDBank",            "sector": "Ngân hàng"},
    "HUT": {"name": "Tasco",             "sector": "Công nghiệp"},
    "HVN": {"name": "Vietnam Airlines",  "sector": "Hàng không"},
    "IDC": {"name": "IDICO",             "sector": "Bất động sản"},
    "MSB": {"name": "MSB",               "sector": "Ngân hàng"},
    "MCH": {"name": "Masan Consumer",    "sector": "Tiêu dùng"},
    "PDR": {"name": "Phát Đạt",          "sector": "Bất động sản"},
    "POW": {"name": "PV Power",          "sector": "Tiện ích"},
    "SAB": {"name": "Sabeco",            "sector": "Tiêu dùng"},
    "SBT": {"name": "TTC AgriS",         "sector": "Tiêu dùng"},
    "SIP": {"name": "Sài Gòn VRG",       "sector": "Bất động sản"},
    "SJS": {"name": "Sudico",            "sector": "Bất động sản"},
    "TCB": {"name": "Techcombank",       "sector": "Ngân hàng"},
    "THD": {"name": "Thaiholdings",      "sector": "Bất động sản"},
    "VHC": {"name": "Vĩnh Hoàn",         "sector": "Thủy sản"},
    "VPB": {"name": "VPBank",            "sector": "Ngân hàng"},
    "VPI": {"name": "Văn Phú Invest",    "sector": "Bất động sản"},
    # Further FTSE members added in later review periods
    "APH": {"name": "An Phát Holdings",  "sector": "Hóa chất"},
    "HCM": {"name": "HSC Securities",    "sector": "Chứng khoán"},
    "HSG": {"name": "Hoa Sen Group",     "sector": "Thép & vật liệu"},
    "KDC": {"name": "KIDO Group",        "sector": "Tiêu dùng"},
    "NAB": {"name": "Nam A Bank",        "sector": "Ngân hàng"},
    "PVD": {"name": "PV Drilling",       "sector": "Dầu khí"},
    "TCH": {"name": "Hoàng Huy (HHS)",   "sector": "Bất động sản"},
    "TCX": {"name": "TCX",               "sector": "Chứng khoán"},
    "VCG": {"name": "Vinaconex",         "sector": "Bất động sản"},
    "VCK": {"name": "VCK",               "sector": "Chứng khoán"},
    "VPX": {"name": "VPX",               "sector": "Chứng khoán"},
}

# Canonical ticker order


# Union of every period in weight.json; the dynamic universe picks a subset per period.
# Order: latest period by descending weight, then the rest alphabetically. This is the
# single source for the basket and the benchmark column order.
TICKERS_FTSE: list[str] = [
    "VIC", "VHM", "HPG", "STB", "VCB", "FPT", "TCX", "VCK", "BID", "SHB",
    "SSI", "VJC", "MSN", "VPX", "MCH", "VNM", "VIX", "VRE", "VCI", "VND",
    "HDB", "MSB", "VPB",
    "APH", "BVH", "DGC", "DIG", "DPM", "EIB", "FTS", "GEX", "HSG", "KBC",
    "KDC", "NVL", "PDR", "POW", "SAB", "SIP", "VCG", "VHC", "VPI",
]
