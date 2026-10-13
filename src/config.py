"""Central configuration: paths, business rules, and reference tables.

Everything that is an *assumption* lives here so it can be reviewed in one place.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw" / "ask_a_manager_2021.csv"
DB_PATH = ROOT / "warehouse" / "salary_survey.db"
REPORT_DIR = ROOT / "reports"
FIG_DIR = REPORT_DIR / "figures"
SQL_DIR = ROOT / "sql"

SOURCE_URL = (
    "https://raw.githubusercontent.com/rfordatascience/tidytuesday/master/"
    "data/2021/2021-05-18/survey.csv"
)

RANDOM_STATE = 42

# --------------------------------------------------------------------------
# Salary validity rules (applied in USD after conversion)
# --------------------------------------------------------------------------
SALARY_USD_MIN = 10_000       # below this: part-time / unit error / unpaid -> excluded
SALARY_USD_MAX = 1_000_000    # above this: too sparse to learn from, excluded
AMBIGUOUS_UNIT_MAX_LOCAL = 999  # 1..999 in a major currency: thousands? hourly? -> excluded
OTHER_COMP_TO_SALARY_MAX = 5.0  # bonus > 5x base salary -> treated as data-entry error
DUPLICATE_MAX_GAP_HOURS = 48    # identical answers inside this window = re-submission

# --------------------------------------------------------------------------
# FX: APPROXIMATE USD per 1 unit, snapshot around mid-May 2021 (survey window).
# Hard-coded on purpose (the sandbox has no FX API) and ONLY used for descriptive
# cross-country comparison. The predictive model uses US/USD rows only, so FX
# error cannot leak into it.
# --------------------------------------------------------------------------
FX_TO_USD = {
    "USD": 1.0, "EUR": 1.21, "GBP": 1.41, "CAD": 0.83, "AUD": 0.78, "NZD": 0.72,
    "CHF": 1.11, "SEK": 0.12, "NOK": 0.12, "DKK": 0.163, "JPY": 0.0092,
    "ZAR": 0.0725, "HKD": 0.129, "SGD": 0.75, "MYR": 0.2425, "INR": 0.0137,
    "BRL": 0.19, "CZK": 0.047, "ILS": 0.31, "MXN": 0.05, "PHP": 0.0208,
    "CNY": 0.155, "IDR": 0.00007, "PLN": 0.265, "KRW": 0.00088, "TWD": 0.036,
    "COP": 0.00027, "ARS": 0.0106, "TTD": 0.147, "KWD": 3.3, "BDT": 0.0118,
    "AED": 0.272, "THB": 0.032, "RUB": 0.0135, "TRY": 0.12, "HUF": 0.0033,
    "RON": 0.245,
}

# Free-text currency spellings found in `currency_other`
CURRENCY_TEXT_ALIASES = {
    "CANADIAN": "CAD", "CANADIAN DOLLARS": "CAD", "MEXICAN PESOS": "MXN",
    "NTD": "TWD", "NT$": "TWD", "INDIAN RUPEES": "INR", "RUPEES": "INR",
    "PESO ARGENTINO": "ARS", "BRL (R$)": "BRL", "BR$": "BRL", "R$": "BRL",
    "RMB": "CNY", "EURO": "EUR", "EUROS": "EUR", "US DOLLARS": "USD", "$": "USD",
}

# --------------------------------------------------------------------------
# Experience / age bands -> ordinal + midpoint (years)
# --------------------------------------------------------------------------
EXPERIENCE_BANDS = {
    "1 year or less": (0, 0.5, 0, 1),
    "2 - 4 years": (1, 3.0, 2, 4),
    "5-7 years": (2, 6.0, 5, 7),
    "8 - 10 years": (3, 9.0, 8, 10),
    "11 - 20 years": (4, 15.5, 11, 20),
    "21 - 30 years": (5, 25.5, 21, 30),
    "31 - 40 years": (6, 35.5, 31, 40),
    "41 years or more": (7, 43.0, 41, 60),
}  # label: (ordinal, midpoint, low, high)

AGE_BANDS = {
    "under 18": (0, 17.0, 0, 17),
    "18-24": (1, 21.0, 18, 24),
    "25-34": (2, 29.5, 25, 34),
    "35-44": (3, 39.5, 35, 44),
    "45-54": (4, 49.5, 45, 54),
    "55-64": (5, 59.5, 55, 64),
    "65 or over": (6, 67.0, 65, 90),
}
MIN_WORKING_AGE = 14  # an exp. band whose LOW bound exceeds (age_high - 14) is impossible

EDUCATION_LEVELS = {
    "High School": 1,
    "Some college": 2,
    "College degree": 3,
    "Master's degree": 4,
    "Professional degree (MD, JD, etc.)": 4,
    "PhD": 5,
}

RACE_OPTIONS = [  # survey answer options (several contain commas -> never split on ",")
    "Asian or Asian American",
    "Black or African American",
    "Hispanic, Latino, or Spanish origin",
    "Middle Eastern or Northern African",
    "Native American or Alaska Native",
    "White",
    "Another option not listed here or prefer not to answer",
]

# --------------------------------------------------------------------------
# Geography
# --------------------------------------------------------------------------
COUNTRY_DISPLAY_OVERRIDES = {
    "Korea, Republic of": "South Korea", "Russian Federation": "Russia",
    "Türkiye": "Turkey", "Taiwan, Province of China": "Taiwan", "Viet Nam": "Vietnam",
    "Czechia": "Czechia", "Iran, Islamic Republic of": "Iran", "Bolivia, Plurinational State of": "Bolivia",
    "Venezuela, Bolivarian Republic of": "Venezuela", "Tanzania, United Republic of": "Tanzania",
    "Moldova, Republic of": "Moldova", "Syrian Arab Republic": "Syria",
    "Brunei Darussalam": "Brunei", "Lao People's Democratic Republic": "Laos",
    "Netherlands": "Netherlands", "United States": "United States",
    "United Kingdom": "United Kingdom", "Hong Kong": "Hong Kong",
}

COUNTRY_ALIASES = {  # normalised key -> canonical display name
    "us": "United States", "usa": "United States", "u s": "United States",
    "u s a": "United States", "america": "United States", "the us": "United States",
    "uk": "United Kingdom", "u k": "United Kingdom", "great britain": "United Kingdom",
    "britain": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "northern ireland": "United Kingdom",
    "england uk": "United Kingdom", "nz": "New Zealand", "uae": "United Arab Emirates",
    "holland": "Netherlands", "the netherlands": "Netherlands", "czech republic": "Czechia",
    "south korea": "South Korea", "korea": "South Korea", "mexico": "Mexico", "méxico": "Mexico",
    "luxemburg": "Luxembourg", "hong kong": "Hong Kong", "puerto rico": "Puerto Rico",
    "san francisco": "United States", "california": "United States",
    "isle of man": "Isle of Man", "europe": "Unresolved", "australian": "Australia",
    "canadian": "Canada", "ua": "Ukraine", "us of a": "United States", "u sa": "United States",
    "turkey": "Turkey", "russia": "Russia", "nl": "Netherlands", "usaa": "United States",
    "usab": "United States", "usat": "United States",
}

# Hand-checked overrides for sentences typed into the country field
COUNTRY_MANUAL_OVERRIDES = {
    "i work for a uae based organization though i am personally in the us": "United States",
    "uk but for globally fully remote company": "United Kingdom",
    "from new zealand but on projects across apac": "New Zealand",
    "argentina but my org is in thailand": "Argentina",
    "usa but for foreign gov t": "United States",
    "usa virgin islands": "United States",
}

US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "District of Columbia", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois",
    "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
    "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana",
    "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
    "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah",
    "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
]
US_STATE_OTHER = ["Puerto Rico", "Guam", "Virgin Islands", "American Samoa", "Northern Mariana Islands"]
