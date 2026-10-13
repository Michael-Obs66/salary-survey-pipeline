"""Industry and job-title standardisation (rule-based, auditable, no black box)."""
from __future__ import annotations

import re

import pandas as pd

# ---------------------------------------------------------------------------
# INDUSTRY: 1,068 raw spellings -> ~30 standard categories
# ---------------------------------------------------------------------------
CANONICAL_INDUSTRIES = [
    "Computing or Tech", "Education (Higher Education)", "Nonprofits",
    "Government and Public Administration", "Health care", "Accounting, Banking & Finance",
    "Engineering or Manufacturing", "Marketing, Advertising & PR", "Law",
    "Education (Primary/Secondary)", "Business or Consulting", "Media & Digital",
    "Insurance", "Retail", "Recruitment or HR", "Property or Construction", "Art & Design",
    "Utilities & Telecommunications", "Transport or Logistics", "Sales", "Social Work",
    "Hospitality & Events", "Entertainment", "Agriculture or Forestry",
    "Leisure, Sport & Tourism", "Publishing", "Libraries & Archives",
    "Biotech & Pharma", "Law Enforcement & Security", "Research & Science",
    "Environment & Sustainability",
]
_CANON_LOWER = {c.lower(): c for c in CANONICAL_INDUSTRIES}

_INDUSTRY_SYNONYMS = {  # exact (lower-cased) variants seen in the data
    "library": "Libraries & Archives", "libraries": "Libraries & Archives",
    "public library": "Libraries & Archives", "public libraries": "Libraries & Archives",
    "manufacturing": "Engineering or Manufacturing", "real estate": "Property or Construction",
    "architecture": "Property or Construction", "biotechnology": "Biotech & Pharma",
    "biotech": "Biotech & Pharma", "pharmaceutical": "Biotech & Pharma",
    "pharmaceuticals": "Biotech & Pharma", "pharma": "Biotech & Pharma",
    "research": "Research & Science", "it": "Computing or Tech", "tech": "Computing or Tech",
    "technology": "Computing or Tech", "software": "Computing or Tech",
    "healthcare": "Health care", "higher education": "Education (Higher Education)",
    "higher ed": "Education (Higher Education)", "university": "Education (Higher Education)",
    "non profit": "Nonprofits", "nonprofit": "Nonprofits", "non-profit": "Nonprofits",
    "finance": "Accounting, Banking & Finance", "banking": "Accounting, Banking & Finance",
}

# ordered: first match wins. (regex, canonical)
_INDUSTRY_RULES: list[tuple[str, str]] = [
    (r"librar|archiv|museum", "Libraries & Archives"),
    (r"pharma|biotech|bitech|biolog|drug|clinical trial|life science", "Biotech & Pharma"),
    (r"environment|enviro|conserv|ecolog|sustainab|climate|wildlife", "Environment & Sustainability"),
    (r"aerospace", "Engineering or Manufacturing"),
    (r"law enforcement|police|corrections|security", "Law Enforcement & Security"),
    (r"military|defen[cs]e", "Government and Public Administration"),
    (r"\blaw\b|legal|attorney|paralegal", "Law"),
    (r"insur", "Insurance"),
    (r"bank|financ|account|invest|credit|wealth|fintech|audit|tax\b", "Accounting, Banking & Finance"),
    (r"software|saas|\bit\b|cyber|information tech|computer|\bdata\b|internet|\bweb\b|\bapps?\b|\btech\b|technolog", "Computing or Tech"),
    (r"publish|editor|journal|newspaper|\bnews\b", "Publishing"),
    (r"k-?12|primary|secondary|elementary|high school|school|teach|prek|preschool|daycare", "Education (Primary/Secondary)"),
    (r"universit|college|higher|academi|campus|student affairs", "Education (Higher Education)"),
    (r"educat|training|e-?learning|online learning|tutor", "Education (Primary/Secondary)"),
    (r"hospital|medic|health|nurs|dental|clinic|pharmacy|veterin|therap|psycholog|public health", "Health care"),
    (r"social work|child|youth|family|counsel|case manag|foster|homeless|disabilit", "Social Work"),
    (r"non-?profit|charit|ngo|foundation|advocacy|philanthrop|religio|church|ministry|faith", "Nonprofits"),
    (r"government|public sector|public admin|municipal|federal|state agency|city of|county|policy|politic|civic", "Government and Public Administration"),
    (r"construct|architect|real estate|property|landscap|interior|land development|surveying", "Property or Construction"),
    (r"energy|oil|gas|utilit|telecom|electric|water|power|solar|wireless", "Utilities & Telecommunications"),
    (r"transport|logistic|shipping|aviation|airline|supply chain|freight|trucking|rail|maritime|warehouse", "Transport or Logistics"),
    (r"market|advertis|\bpr\b|public relation|communicat|brand|seo\b", "Marketing, Advertising & PR"),
    (r"media|digital|broadcast|video|film|tv\b|podcast|radio|social media", "Media & Digital"),
    (r"entertain|music|game|gaming|theat|theater|performing", "Entertainment"),
    (r"art\b|arts|design|creative|photo|fashion", "Art & Design"),
    (r"hospitality|restaurant|hotel|food|beverage|event|catering|wedding", "Hospitality & Events"),
    (r"tourism|travel|sport|fitness|recreation|leisure|outdoor|golf|gym", "Leisure, Sport & Tourism"),
    (r"agricultur|farm|forest|food production|horticultur|garden", "Agriculture or Forestry"),
    (r"recruit|staffing|human resource|\bhr\b|talent|payroll|people ops", "Recruitment or HR"),
    (r"retail|e-?commerce|grocery|merchand|consumer goods|wholesale|apparel", "Retail"),
    (r"sales|real-?estate agent|brokerage", "Sales"),
    (r"cannabis|consumer packaged|\bcpg\b|beauty|cosmetic", "Retail"),
    (r"fundrais|international development|clergy|labor union|organized labor|trade association|\bunion\b", "Nonprofits"),
    (r"urban planning|public safety", "Government and Public Administration"),
    (r"mortgage|private equity|compliance", "Accounting, Banking & Finance"),
    (r"translat|customer service|procurement|purchasing|distribution", "Business or Consulting"),
    (r"consult|professional services|management services|business service", "Business or Consulting"),
    (r"research|scien|laborator|r&d|think tank|academia", "Research & Science"),
    (r"engineer|manufactur|industrial|aerospace|aviation manuf|automotive|mining|chemical|materials|machin", "Engineering or Manufacturing"),
]

UNCLASSIFIED = "Other / Unclassified"


def normalize_industry(raw) -> tuple[str, str]:
    """Return (industry_std, method) with method in {exact, synonym, keyword, missing, unclassified}."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or not str(raw).strip():
        return UNCLASSIFIED, "missing"
    txt = re.sub(r"\s+", " ", str(raw)).strip().lower()
    if txt in _CANON_LOWER:
        return _CANON_LOWER[txt], "exact"
    if txt in _INDUSTRY_SYNONYMS:
        return _INDUSTRY_SYNONYMS[txt], "synonym"
    for pat, canon in _INDUSTRY_RULES:
        if re.search(pat, txt):
            return canon, "keyword"
    return UNCLASSIFIED, "unclassified"


# ---------------------------------------------------------------------------
# JOB TITLE: free text -> normalised text, seniority, job family
# ---------------------------------------------------------------------------
def normalize_title(raw) -> str:
    txt = str(raw).lower().strip()
    txt = re.sub(r"[^a-z0-9&/+ ]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


_SENIORITY_RULES: list[tuple[str, str]] = [  # highest level first
    (r"\b(ceo|cfo|coo|cto|cio|cmo|chief|president|vp|vice president|svp|evp|founder|owner|partner|managing director|head of)\b", "Executive"),
    (r"\b(director|dir)\b", "Director"),
    (r"\b(manager|mgr|supervisor|superintendent)\b", "Manager"),
    (r"\b(lead|principal|staff|architect)\b", "Lead / Principal"),
    (r"\b(senior|sr|iii|iv)\b", "Senior"),
    (r"\b(junior|jr|intern|trainee|apprentice|entry|assistant|associate|coordinator|i)\b", "Junior / Entry"),
]

_FAMILY_RULES: list[tuple[str, str]] = [  # ordered, first match wins
    (r"\b(ceo|cfo|coo|cto|cio|cmo|chief|president|vice president|vp|svp|founder|owner|managing director|executive director)\b", "Executive / Leadership"),
    (r"data scien|machine learning|\bml\b|\bai\b|data engineer|data analy|analytics|business intelligence|\bbi\b|statistic|quantitative|data architect|data manager", "Data & Analytics"),
    (r"software|developer|programmer|\bswe\b|devops|\bsre\b|full ?stack|front ?end|back ?end|web dev|mobile dev|application dev|qa engineer|\bqa\b|test engineer", "Software Engineering"),
    (r"solutions? architect|enterprise architect|technical director|tech lead|director of technology|\bit\b|systems|network|sysadmin|help ?desk|technical support|infrastructure|security analyst|database admin|\bdba\b|cloud|information technology|desktop support", "IT & Systems"),
    (r"project manag|product manag|program manag|scrum|\bpmo\b|product owner|program director|project coordinator|project lead", "Product / Project / Program Mgmt"),
    (r"attorney|lawyer|paralegal|legal|counsel|\bjudge\b|compliance|public defender|prosecutor", "Legal & Compliance"),
    (r"speech language|pathologist|dietitian|optometr|paramedic|hygienist|nurse|\brn\b|physician|doctor|therapist|clinical|medical|dentist|pharmacist|veterinar|psycholog|counselor|health|clinician|patient", "Healthcare & Clinical"),
    (r"account(ant|ing)|financ|controller|auditor|bookkeep|\btax\b|actuar|treasur|payroll|analyst.*(fp&a)|underwrit|banker|investment|loan|credit", "Finance & Accounting"),
    (r"recruit|talent|\bhr\b|human resources|people (ops|partner|operations)|benefits|compensation", "HR & Recruiting"),
    (r"marketing|communications|\bpr\b|public relations|content|social media|brand|copywrit|\bseo\b|campaign|creative director|advertis|digital media", "Marketing & Communications"),
    (r"sales|business development|account executive|account manager|customer success|\bbd\b|relationship manager|client", "Sales & Business Dev"),
    (r"design|\bux\b|\bui\b|artist|graphic|illustrat|animator|photograph|editor|writer|producer|videograph|reporter|journalist|translator|interpreter", "Design, Media & Creative"),
    (r"graduate student|phd candidate|\bstudent\b|trainer|training|teacher|professor|instructor|lecturer|faculty|tutor|educator|principal|dean|academic|curriculum|school|adjunct", "Education & Academia"),
    (r"librarian|library|archivist|curator|museum", "Library & Archives"),
    (r"geolog|archaeolog|epidemiolog|economist|research|scientist|\blab\b|laborator|biolog|chemist|postdoc|analyst.*research", "Research & Science"),
    (r"engineer|architect|mechanical|electrical|civil|structural|process|manufactur|technician|machinist", "Engineering (non-software)"),
    (r"development|fundrais|grant|donor|advancement|outreach|advocate|case manag|social work|program (officer|coordinator|associate|assistant)|community|volunteer", "Nonprofit / Development / Social"),
    (r"customer (service|support)|support (specialist|rep)|representative|call center|\bcsr\b|receptionist|help", "Customer Support"),
    (r"consultant|advisor|adviser|advisory|strategist|policy", "Consulting & Advisory"),
    (r"operations|administrat|assistant|office|coordinator|\badmin\b|\bea\b|clerk|secretary|logistic|specialist|officer|analyst|registrar|buyer|planner|procurement|purchasing|barista", "Operations & Admin"),
    (r"manager|director|supervisor|deputy|head|lead|leader|partner|associate", "General Management"),
]

DATA_ROLE_PATTERN = re.compile(
    r"data scien|machine learning|\bml\b|\bai\b|data engineer|data analy|analytics|business intelligence|\bbi\b|statistic"
)


def classify_title(title_norm: str) -> tuple[str, str, bool]:
    """Return (seniority, job_family, is_data_role)."""
    seniority = "Mid-level / Unspecified"
    for pat, label in _SENIORITY_RULES:
        if re.search(pat, title_norm):
            seniority = label
            break
    family = "Other"
    for pat, label in _FAMILY_RULES:
        if re.search(pat, title_norm):
            family = label
            break
    return seniority, family, bool(DATA_ROLE_PATTERN.search(title_norm))
