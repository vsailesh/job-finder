"""
Streamlit Dashboard — Interactive job search viewer with auto-apply and profiles.
Run with: streamlit run dashboard/app.py
"""
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import json
from datetime import datetime, timedelta

import config
from models.profile import Profile

# ─── Page Config ────────────────────────────────────────────
st.set_page_config(
    page_title="Job Finder Agent — Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize DB (creates applications table if not exists)
db = config.get_database()
db.init_sync()

# ─── Custom CSS ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }
    
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem 2.5rem; border-radius: 16px; color: white;
        margin-bottom: 2rem; box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
    }
    .main-header h1 { font-size: 2rem; font-weight: 700; margin: 0; letter-spacing: -0.02em; }
    .main-header p { opacity: 0.9; margin: 0.3rem 0 0 0; font-size: 1rem; }
    
    .metric-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 1.5rem; border-radius: 12px; text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08); transition: transform 0.2s ease;
        cursor: pointer;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.12); }
    .metric-value { font-size: 2.5rem; font-weight: 700; color: #2d3748; line-height: 1; }
    .metric-label { font-size: 0.85rem; color: #718096; font-weight: 500; margin-top: 0.3rem; text-transform: uppercase; letter-spacing: 0.05em; }
    
    .type-federal { background: #dbeafe; color: #1e40af; }
    .type-state { background: #fef3c7; color: #92400e; }
    .type-corporate { background: #e0e7ff; color: #3730a3; }
    .type-remote { background: #d1fae5; color: #065f46; }
    
    .status-queued { background: #e0e7ff; color: #3730a3; }
    .status-applied { background: #d1fae5; color: #065f46; }
    .status-manual { background: #fef3c7; color: #92400e; }
    .status-failed { background: #fde2e2; color: #922b21; }
    .status-interview { background: #dbeafe; color: #1e40af; }
    .status-offered { background: #d1fae5; color: #065f46; }

    div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0 0; padding: 8px 20px; }
    
    .profile-card {
        background: white; border: 2px solid #e2e8f0; border-radius: 12px;
        padding: 1.2rem; margin-bottom: 0.8rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .profile-card:hover { border-color: #667eea; }
    
    .funnel-step {
        text-align: center; padding: 1rem; border-radius: 8px;
        margin-bottom: 0.5rem; font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


def load_data(hours: int = 0) -> pd.DataFrame:
    """Load jobs from database."""
    if not config.DB_PATH.exists():
        return pd.DataFrame()
    jobs = db.get_jobs_sync(hours=hours, limit=50000)
    if not jobs:
        return pd.DataFrame()
    df = pd.DataFrame(jobs)
    if "posted_date" in df.columns:
        df["posted_date"] = pd.to_datetime(df["posted_date"], errors="coerce")
    if "fetched_at" in df.columns:
        df["fetched_at"] = pd.to_datetime(df["fetched_at"], errors="coerce")
    return df


def render_metric(value, label, color="#667eea"):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value" style="color: {color};">{value}</div>
        <div class="metric-label">{label}</div>
    </div>
    """, unsafe_allow_html=True)


def classify_seniority(title: str) -> str:
    t = str(title).lower()
    if any(w in t for w in ['intern', 'trainee', 'entry', 'graduate']):
        return 'Entry'
    elif any(w in t for w in ['junior', 'jr ', 'associate']):
        return 'Junior'
    elif any(w in t for w in ['senior', 'sr ', ' iii', 'staff']):
        return 'Senior'
    elif any(w in t for w in ['lead', 'principal', 'architect']):
        return 'Lead / Principal'
    elif any(w in t for w in ['director', 'vp', 'vice president', 'head of']):
        return 'Director / VP'
    elif any(w in t for w in ['cto', 'ceo', 'cfo', 'chief']):
        return 'C-Level'
    return 'Mid-Level'

def classify_sector(title: str, category: str, description: str = "") -> str:
    """
    Classify jobs into broader sectors based on NAICS (North American Industry Classification System)
    and SOC (Standard Occupational Classification) standards from US Bureau of Labor Statistics.

    NAICS Sectors Reference: https://www.census.gov/naics/
    SOC Occupational Groups: https://www.bls.gov/soc/
    """
    t = str(title).lower()
    c = str(category).lower()
    d = str(description).lower()
    combined_text = f"{t} {c} {d}"

    # ═══════════════════════════════════════════════════════════════
    # TECHNOLOGY SECTORS (NAICS 51 - Information)
    # ═══════════════════════════════════════════════════════════════

    # AI & Machine Learning (SOC 15-2000+ - Computer and Information Research Scientists)
    if any(w in combined_text for w in ['artificial intelligence', 'machine learning', 'deep learning', 'nlp',
                                          'computer vision', 'llm', 'generative ai', 'mlops', 'ai engineer',
                                          'data scientist', 'ml engineer', 'neural network', 'computer vision engineer']):
        return 'AI & Machine Learning'

    # Blockchain & Crypto (Emerging technology sector)
    if any(w in combined_text for w in ['blockchain', 'cryptocurrency', 'web3', 'smart contract', 'defi',
                                          'nft', 'bitcoin', 'ethereum', 'solidity', 'crypto engineer',
                                          'web3 developer', 'decentralized']):
        return 'Blockchain & Crypto'

    # IT & Software (NAICS 5112, 5415 - Software Publishers, Computer Systems Design)
    # (SOC 15-1000+ - Computer and Mathematical Occupations)
    if any(w in combined_text for w in ['software', 'developer', 'programmer', 'web', 'mobile', 'full stack',
                                          'backend', 'frontend', 'devops', 'cloud', 'cybersecurity', 'network',
                                          'database', 'it ', 'information technology', 'full-stack', 'back-end',
                                          'front-end', 'software engineer', 'applications developer', 'systems analyst']):
        return 'IT & Software'

    # ═══════════════════════════════════════════════════════════════
    # ENERGY SECTOR (NAICS 22 - Utilities, 21 - Mining, Oil & Gas)
    # Reference: US Department of Energy - Energy Employment Report
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['oil and gas', 'oil & gas', 'petroleum', 'upstream', 'downstream',
                                          'midstream', 'drilling', 'refining', 'offshore', 'pipeline',
                                          'lng', 'liquefied natural gas', 'fossil fuel', 'petroleum engineer',
                                          'drilling engineer', 'reservoir engineer']):
        return 'Energy - Oil & Gas'

    if any(w in combined_text for w in ['renewable energy', 'solar', 'wind', 'geothermal', 'hydropower',
                                          'biomass', 'clean energy', 'green energy', 'solar engineer',
                                          'wind turbine', 'photovoltaic', 'renewables', 'energy storage']):
        return 'Energy - Renewables'

    if any(w in combined_text for w in ['nuclear energy', 'nuclear power', 'reactor', 'radiation',
                                          'isotope', 'health physics', 'criticality', 'nuclear engineering',
                                          'nuclear operator', 'nuclear safety']):
        return 'Energy - Nuclear'

    if any(w in combined_text for w in ['utility', 'utilities', 'power generation', 'electric grid',
                                          'transmission', 'distribution', 'substation', 'power plant',
                                          'grid operator', 'electrical utility', 'energy management',
                                          'smart grid', 'metering', 'power systems']):
        return 'Energy - Utilities & Grid'

    if any(w in combined_text for w in ['energy', 'energy efficiency', 'sustainability', 'esg',
                                          'carbon', 'climate tech', 'battery technology', 'hydrogen',
                                          'energy analyst', 'energy auditor', 'cleantech']):
        return 'Energy - General & Cleantech'

    # ═══════════════════════════════════════════════════════════════
    # TRANSPORTATION & SHIPPING (NAICS 48-49 - Transportation and Warehousing)
    # Reference: Bureau of Transportation Statistics
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['maritime', 'shipping', 'port', 'sea transport', 'ocean freight',
                                          'vessel', 'ship', 'cargo ship', 'container shipping', 'marine',
                                          'maritime engineer', 'port operations', 'harbor', 'stevedore',
                                          'marine logistics', 'ocean carrier', 'bulk shipping']):
        return 'Shipping & Maritime'

    if any(w in combined_text for w in ['logistics', 'supply chain', 'freight', 'warehouse', 'distribution',
                                          'inventory', 'fulfillment', 'shipping coordinator', 'logistics manager',
                                          'supply chain analyst', 'freight forwarder', 'last mile', '3pl', '4pl']):
        return 'Logistics & Supply Chain'

    if any(w in combined_text for w in ['truck', 'trucking', 'freight transportation', 'delivery', 'courier',
                                          'fleet', 'transportation', 'route', 'driver', 'dispatch', 'carrier',
                                          'truck driver', 'delivery driver', 'fleet manager']):
        return 'Transportation - Ground'

    if any(w in combined_text for w in ['aviation', 'airline', 'airport', 'air cargo', 'air freight',
                                          'flight operations', 'air traffic', 'aviation maintenance',
                                          'airline pilot', 'aircraft dispatcher']):
        return 'Transportation - Aviation'

    if any(w in combined_text for w in ['rail', 'railroad', 'train', 'railway', 'locomotive',
                                          'rail freight', 'transit', 'metro', 'rail operations']):
        return 'Transportation - Rail'

    # ═══════════════════════════════════════════════════════════════
    # HEALTHCARE (NAICS 62 - Health Care and Social Assistance)
    # SOC 29-0000+ - Healthcare Practitioners and Technical Occupations
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['nurse', 'nursing', 'rn', 'lpn', 'cna', 'nurse practitioner',
                                          'physician', 'doctor', 'medical doctor', 'surgeon', 'healthcare',
                                          'clinical', 'pharmacist', 'radiologist', 'therapist', 'medical',
                                          'health care', 'patient care', 'registered nurse', 'clinical nurse']):
        return 'Healthcare & Nursing'

    # ═══════════════════════════════════════════════════════════════
    # DEFENSE (NAICS 33 - Defense Manufacturing)
    # Reference: US Department of Defense - Occupational Classification
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['defense', 'military', 'army', 'navy', 'air force', 'weapons',
                                          'combat', 'security clearance', 'dod', 'intelligence analyst',
                                          'defense contractor', 'military analyst', 'defense systems',
                                          'signals intelligence', 'counterintelligence', 'combat systems',
                                          'defense program manager']):
        return 'Defense & Military'

    # ═══════════════════════════════════════════════════════════════
    # MANUFACTURING (NAICS 31-33 - Manufacturing)
    # SOC 47-0000+ - Production Occupations
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['manufacturing', 'production', 'plant', 'factory', 'industrial',
                                          'quality control', 'cnc', 'machinist', 'assembly', 'fabrication',
                                          'production supervisor', 'plant manager', 'lean manufacturing',
                                          'six sigma', 'production engineer', 'manufacturing engineer']):
        return 'Manufacturing'

    # ═══════════════════════════════════════════════════════════════
    # FINANCE (NAICS 52 - Finance and Insurance)
    # SOC 13-0000+ - Business and Financial Operations Occupations
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['finance', 'financial', 'investment', 'trading', 'banking',
                                          'fintech', 'quantitative', 'portfolio', 'risk analyst',
                                          'financial analyst', 'investment banker', 'trader', 'asset management',
                                          'corporate finance', 'financial planning']):
        return 'Finance & FinTech'

    # ═══════════════════════════════════════════════════════════════
    # ADVANCED MANUFACTURING & TECHNOLOGY
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['robotics', 'automation', 'mechatronics', 'robot',
                                          'autonomous systems', 'control systems', 'plc', 'embedded systems',
                                          'industrial automation', 'robotics engineer', 'automation engineer']):
        return 'Robotics & Automation'

    if any(w in combined_text for w in ['aerospace', 'aviation', 'aircraft', 'satellite', 'uav',
                                          'drone', 'propulsion', 'flight', 'orbital', 'aeronautics',
                                          'astronautics', 'avionics', 'flight systems', 'unmanned aerial systems']):
        return 'Aerospace'

    # ═══════════════════════════════════════════════════════════════
    # LIFE SCIENCES (NAICS 3254 - Pharmaceutical and Medicine Manufacturing)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['pharmaceutical', 'biotech', 'biotechnology', 'drug development',
                                          'clinical trials', 'bioinformatics', 'genomics', 'regulatory affairs',
                                          'clinical research', 'pharmaceutical scientist', 'biomedical']):
        return 'Pharma & Biotech'

    # ═══════════════════════════════════════════════════════════════
    # EDUCATION (NAICS 61 - Educational Services)
    # SOC 25-0000+ - Educational Instruction and Library Occupations
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['teacher', 'education', 'professor', 'instructor', 'trainer',
                                          'curriculum', 'academic', 'educator', 'faculty', 'teaching',
                                          'principal', 'school administrator']):
        return 'Education'

    # ═══════════════════════════════════════════════════════════════
    # GENERAL ENGINEERING (SOC 17-0000+ - Architecture and Engineering Occupations)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['engineer', 'engineering', 'civil engineer', 'structural engineer',
                                          'electrical engineer', 'mechanical engineer', 'chemical engineer',
                                          'industrial engineer']) and 'manufacturing' not in combined_text:
        return 'General Engineering'

    # ═══════════════════════════════════════════════════════════════
    # BUSINESS & PROFESSIONAL (NAICS 54 - Professional, Scientific, and Technical Services)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['admin', 'administrative', 'assistant', 'clerk', 'receptionist',
                                          'office', 'secretary', 'coordinator', 'office manager']):
        return 'Administrative'

    if any(w in combined_text for w in ['manager', 'management', 'director', 'head of', 'vp', 'chief',
                                          'executive', 'leader', 'business manager', 'operations manager']):
        return 'Management'

    if any(w in combined_text for w in ['sales', 'marketing', 'business development', 'account manager',
                                          'revenue', 'growth', 'sales representative', 'marketing manager']):
        return 'Sales & Marketing'

    if any(w in combined_text for w in ['research', 'r&d', 'scientist', 'analyst', 'data analyst',
                                          'research scientist', 'research associate']):
        return 'Research & Development'

    # ═══════════════════════════════════════════════════════════════
    # CONSTRUCTION & TRADES (NAICS 23 - Construction)
    # SOC 47-0000+ - Construction and Extraction Occupations
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['electrician', 'plumber', 'carpenter', 'welder', 'mechanic',
                                          'technician', 'maintenance', 'construction', 'skilled trade',
                                          'hvac', 'pipefitter', 'ironworker', 'heavy equipment']):
        return 'Skilled Trades'

    return 'Other'

def classify_job_type(title: str, category: str, description: str = "") -> str:
    """
    Classify jobs into collar types and work categories based on SOC (Standard Occupational Classification)
    Major Groups and US EEOC (Equal Employment Opportunity Commission) job categories.

    SOC Major Groups Reference: https://www.bls.gov/soc/2018/soc_2018_major_groups.htm
    EEOC Categories: https://www.eeoc.gov/statistics/employment/jobpatterns
    """
    t = str(title).lower()
    c = str(category).lower()
    d = str(description).lower()
    combined_text = f"{t} {c} {d}"

    # ═══════════════════════════════════════════════════════════════
    # SOC 15-0000: Computer and Mathematical Occupations (IT / Technical)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['software', 'developer', 'engineer', 'programmer', 'data scientist',
                                          'machine learning', 'ai', 'artificial intelligence', 'cloud', 'devops',
                                          'cybersecurity', 'cyber security', 'network', 'system admin', 'database',
                                          'web', 'mobile', 'full stack', 'backend', 'frontend', 'qa', 'test engineer',
                                          'data engineer', 'mlops', 'site reliability', 'sre', 'information security',
                                          'penetration tester', 'cloud architect', 'solutions architect']):
        return 'IT / Technical'

    # ═══════════════════════════════════════════════════════════════
    # SOC 43-0000: Office and Administrative Support (Administrative)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['admin', 'administrative', 'assistant', 'clerk', 'receptionist',
                                          'office', 'secretary', 'data entry', 'office manager', 'executive assistant',
                                          'office assistant', 'administrative assistant', 'file clerk', 'word processor',
                                          'desktop publishing']):
        return 'Administrative'

    # ═══════════════════════════════════════════════════════════════
    # SOC 11-0000: Management Occupations (Managerial)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['manager', 'management', 'director', 'vp', 'vice president', 'chief',
                                          'ceo', 'cto', 'cfo', 'cio', 'coo', 'head of', 'lead', 'supervisor',
                                          'team lead', 'principal', 'executive', 'administrator', 'operations manager',
                                          'general manager', 'program manager', 'product manager']):
        return 'Managerial'

    # ═══════════════════════════════════════════════════════════════
    # SOC 47-0000: Construction and Extraction (Blue Collar)
    # SOC 51-0000: Production Occupations (Blue Collar)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['manufacturing', 'production', 'factory', 'warehouse', 'logistics',
                                          'driver', 'mechanic', 'technician', 'maintenance', 'construction',
                                          'electrician', 'plumber', 'welder', 'carpenter', 'machinist', 'operator',
                                          'labor', 'laborer', 'assembly', 'fabrication', 'quality control', 'inspector',
                                          'heavy equipment', 'crane', 'forklift', 'machine operator', 'production worker',
                                          'packer', 'packaging', 'material handling', 'shipping', 'receiving']):
        return 'Blue Collar'

    # ═══════════════════════════════════════════════════════════════
    # SOC 13-0000: Business and Financial Operations (White Collar)
    # SOC 17-0000: Architecture and Engineering (White Collar)
    # SOC 19-0000: Life, Physical, and Social Science Occupations (White Collar)
    # SOC 25-0000: Educational Instruction and Library (White Collar)
    # SOC 29-0000: Healthcare Practitioners (White Collar)
    # SOC 41-0000: Sales and Related (White Collar)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['analyst', 'consultant', 'accountant', 'auditor', 'financial analyst',
                                          'business analyst', 'data analyst', 'legal', 'attorney', 'lawyer', 'paralegal',
                                          'architect', 'scientist', 'research scientist', 'pharmacist', 'doctor',
                                          'physician', 'nurse', 'teacher', 'professor', 'engineer', 'investment banker',
                                          'actuary', 'economist', 'statistician', 'researcher', 'advisor', 'specialist']):
        return 'White Collar'

    # ═══════════════════════════════════════════════════════════════
    # SOC 41-0000: Sales and Related (Service Industry)
    # SOC 35-0000: Food Preparation and Serving (Service Industry)
    # SOC 37-0000: Building and Grounds Cleaning and Maintenance (Service Industry)
    # SOC 39-0000: Personal Care and Service (Service Industry)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['customer service', 'sales', 'retail', 'hospitality', 'food service',
                                          'server', 'cashier', 'representative', 'support', 'call center',
                                          'waiter', 'waitress', 'bartender', 'host', 'hostess', 'cook', 'chef',
                                          'cleaner', 'janitor', 'security guard', 'personal care', 'home health aide',
                                          'cashier', 'retail sales', 'sales associate', 'account representative']):
        return 'Service Industry'

    # ═══════════════════════════════════════════════════════════════
    # SOC 27-0000: Arts, Design, Entertainment, Sports, and Media (Creative)
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['designer', 'writer', 'editor', 'journalist', 'artist', 'content creator',
                                          'marketing', 'creative', 'ux', 'ui', 'graphic designer', 'content writer',
                                          'copywriter', 'photographer', 'videographer', 'producer', 'director',
                                          'social media', 'content manager', 'brand manager', 'art director',
                                          'creative director', 'illustrator', 'animator', 'game designer']):
        return 'Creative'

    # ═══════════════════════════════════════════════════════════════
    # Transportation (Blue Collar subset - but distinct for analysis)
    # SOC 53-0000: Transportation and Material Moving Occupations
    # ═══════════════════════════════════════════════════════════════
    if any(w in combined_text for w in ['truck driver', 'delivery driver', 'bus driver', 'taxi', 'uber',
                                          'lyft', 'courier', 'delivery', 'pilot', 'captain', 'mate',
                                          'flight attendant', 'air traffic controller', 'conductor', 'locomotive']):
        return 'Transportation'

    return 'Other'

def main():
    # ─── Header ─────────────────────────────────────────────
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Job Finding Agent</h1>
        <p>Federal · State · Corporate · Remote — With Auto-Apply</p>
    </div>
    """, unsafe_allow_html=True)

    # ─── Sidebar ────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Filters")

        time_filter = st.selectbox(
            "Time Range",
            options=[0, 24, 48, 72, 168],
            format_func=lambda x: {0: "All Time", 24: "Last 24h", 48: "Last 48h", 72: "Last 3 Days", 168: "Last Week"}.get(x, f"Last {x}h"),
            index=1,
        )

        df = load_data(hours=time_filter)

        if df.empty:
            st.warning("No jobs found. Run the agent first:\n```\npython main.py\n```")
            st.stop()

        df["seniority_level"] = df["title"].apply(classify_seniority)
        df["sector"] = df.apply(lambda r: classify_sector(r.get("title", ""), r.get("category", ""), r.get("description", "")), axis=1)
        df["job_category"] = df.apply(lambda r: classify_job_type(r.get("title", ""), r.get("category", ""), r.get("description", "")), axis=1)

        seniorities = ['Entry', 'Junior', 'Mid-Level', 'Senior', 'Lead / Principal', 'Director / VP', 'C-Level']
        available_seniorities = [s for s in seniorities if s in df["seniority_level"].unique()]
        selected_seniorities = st.multiselect("Seniority", available_seniorities, default=available_seniorities)

        sources = sorted(df["source"].unique().tolist())
        selected_sources = st.multiselect("Sources", sources, default=sources)

        # REMOVED: Old category filter - now using unified sectors

        job_types = sorted(df["job_type"].unique().tolist())
        default_types = job_types
        if "filter_type" in st.session_state and st.session_state.filter_type:
            ft = st.session_state.filter_type
            if ft in job_types:
                default_types = [ft]
        selected_types = st.multiselect("Job Types", job_types, default=default_types)

        # New: Sector Filter
        sectors = sorted(df["sector"].unique().tolist())
        selected_sectors = st.multiselect("Sectors", sectors, default=sectors)

        # New: Job Category Filter (IT, Admin, etc.)
        job_categories = sorted(df["job_category"].unique().tolist())
        selected_job_categories = st.multiselect("Job Categories (IT, Admin, etc.)", job_categories, default=job_categories)

        search_term = st.text_input("🔎 Search", placeholder="Title, company...")

        st.markdown("#### 💰 Salary Range")
        has_salary = df["salary_min"].notna()
        salary_range = None
        if has_salary.any():
            min_sal = int(df.loc[has_salary, "salary_min"].min())
            max_sal = int(df.loc[has_salary, "salary_max"].fillna(df["salary_min"]).max())
            if min_sal < max_sal:
                salary_range = st.slider("Salary ($)", min_sal, max_sal, (min_sal, max_sal), step=5000, format="$%d")
        else:
            st.caption("No salary data available")

        # Reset filter buttons
        if st.button("🔄 Reset All Filters"):
            for key in ["filter_sector", "filter_type", "filter_source", "filter_company"]:
                st.session_state.pop(key, None)
            st.rerun()

    # ─── Apply Filters ──────────────────────────────────────
    mask = (df["source"].isin(selected_sources) &
            df["job_type"].isin(selected_types) &
            df["seniority_level"].isin(selected_seniorities) &
            df["sector"].isin(selected_sectors) &
            df["job_category"].isin(selected_job_categories))

    if search_term:
        sl = search_term.lower()
        mask &= (
            df["title"].str.lower().str.contains(sl, na=False)
            | df["company"].str.lower().str.contains(sl, na=False)
            | df["description"].str.lower().str.contains(sl, na=False)
        )

    if "filter_company" in st.session_state and st.session_state.filter_company:
        mask &= df["company"] == st.session_state.filter_company

    if salary_range:
        mask &= (df["salary_min"].isna() | (df["salary_min"] >= salary_range[0])) & \
                (df["salary_max"].isna() | (df["salary_max"] <= salary_range[1]))

    filtered = df[mask].copy()

    # ─── Metrics Row ────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: render_metric(f"{len(filtered):,}", "Total Jobs", "#667eea")
    with col2: render_metric(f"{len(filtered[filtered['job_type']=='federal']):,}", "Federal", "#1a5276")
    with col3: render_metric(f"{len(filtered[filtered['job_type']=='corporate']):,}", "Corporate", "#3730a3")
    with col4: render_metric(f"{len(filtered[filtered['job_type']=='remote']):,}", "Remote", "#065f46")
    with col5: render_metric(f"{filtered['salary_min'].notna().sum():,}", "With Salary", "#92400e")

    # ─── Second Metrics Row: Job Category Breakdown ───────────────
    col6, col7, col8, col9, col10 = st.columns(5)
    with col6: render_metric(f"{len(filtered[filtered['job_category']=='IT / Technical']):,}", "IT/Tech Jobs", "#667eea")
    with col7: render_metric(f"{len(filtered[filtered['job_category']=='Administrative']):,}", "Admin Jobs", "#fbbf24")
    with col8: render_metric(f"{len(filtered[filtered['job_category']=='Blue Collar']):,}", "Blue Collar", "#10b981")
    with col9: render_metric(f"{len(filtered[filtered['job_category']=='White Collar']):,}", "White Collar", "#3b82f6")
    with col10: render_metric(f"{len(filtered[filtered['job_category']=='Managerial']):,}", "Management", "#f59e0b")

    st.markdown("<br>", unsafe_allow_html=True)

    # ─── Main Tabs ──────────────────────────────────────────
    tab1, tab2, tab6, tab3, tab4, tab5, tab7 = st.tabs([
        "📊 Overview", "📋 Job Listings", "💰 Analytics",
        "🎯 Auto Apply", "👤 Profiles", "📈 Applications",
        "🏢 Company Tracker"
    ])

    # ═══════════════ TAB 1: Overview ═══════════════
    with tab1:
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            sector_counts = filtered["sector"].value_counts().reset_index()
            sector_counts.columns = ["Sector", "Count"]
            fig = px.bar(
                sector_counts, x="Count", y="Sector", orientation="h",
                color="Count", color_continuous_scale=["#c3cfe2", "#667eea", "#764ba2"],
                title="Jobs by Sector (click to filter)",
            )
            fig.update_layout(
                showlegend=False, coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter"), height=400,
            )
            event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="sector_chart_click")
            if event and event.selection and event.selection.points:
                clicked_sector = event.selection.points[0].get("y")
                if clicked_sector:
                    st.session_state.filter_sector = clicked_sector
                    st.rerun()

        with chart_col2:
            source_counts = filtered["source"].value_counts().reset_index()
            source_counts.columns = ["Source", "Count"]
            fig = px.pie(
                source_counts, values="Count", names="Source", title="Jobs by Source (click to filter)",
                hole=0.4,
            )
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter"), height=400,
            )
            event2 = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="source_chart")
            if event2 and event2.selection and event2.selection.points:
                clicked_src = event2.selection.points[0].get("label")
                if clicked_src:
                    st.session_state.filter_source = clicked_src
                    st.rerun()

        chart_col3, chart_col4 = st.columns(2)

        with chart_col3:
            type_counts = filtered["job_type"].value_counts().reset_index()
            type_counts.columns = ["Type", "Count"]
            type_colors = {"federal": "#2980b9", "state": "#f39c12", "corporate": "#8e44ad", "remote": "#27ae60"}
            fig = px.bar(type_counts, x="Type", y="Count", color="Type",
                         color_discrete_map=type_colors, title="Jobs by Type (click to filter)")
            fig.update_layout(showlegend=False, plot_bgcolor="rgba(0,0,0,0)",
                              paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter"), height=350)
            event3 = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="type_chart")
            if event3 and event3.selection and event3.selection.points:
                clicked_type = event3.selection.points[0].get("x")
                if clicked_type:
                    st.session_state.filter_type = clicked_type
                    st.rerun()

        with chart_col4:
            top_companies = filtered["company"].value_counts().head(10).reset_index()
            top_companies.columns = ["Company", "Openings"]
            fig = px.bar(top_companies, x="Openings", y="Company", orientation="h",
                         color="Openings", color_continuous_scale=["#e8f4fd", "#1a5276"],
                         title="Top 10 Employers (click to filter)")
            fig.update_layout(showlegend=False, coloraxis_showscale=False,
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(family="Inter"), height=350, yaxis=dict(autorange="reversed"))
            event4 = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="company_chart")
            if event4 and event4.selection and event4.selection.points:
                clicked_company = event4.selection.points[0].get("y")
                if clicked_company:
                    st.session_state.filter_company = clicked_company
                    st.rerun()

        # Active filters display
        active_filters = []
        if "filter_sector" in st.session_state and st.session_state.filter_sector:
            active_filters.append(f"Sector: **{st.session_state.filter_sector}**")
        if "filter_type" in st.session_state and st.session_state.filter_type:
            active_filters.append(f"Type: **{st.session_state.filter_type}**")
        if "filter_company" in st.session_state and st.session_state.filter_company:
            active_filters.append(f"Company: **{st.session_state.filter_company}**")
        if active_filters:
            st.info("🔍 Active click filters: " + " · ".join(active_filters) + "  — Use 🔄 Reset in sidebar to clear")

        st.markdown("---")

        # ═══════════════ NEW VISUALIZATIONS: Sector & Job Type Analysis ═══════════════
        st.markdown("### 🎯 Sector & Job Type Analysis")

        # Row 3: Sector Distribution & Job Type Distribution
        chart_col5, chart_col6 = st.columns(2)

        with chart_col5:
            sector_counts = filtered["sector"].value_counts().reset_index()
            sector_counts.columns = ["Sector", "Count"]
            fig_sector = px.bar(
                sector_counts, x="Count", y="Sector", orientation="h",
                color="Count", color_continuous_scale=["#d1fae5", "#059669", "#065f46"],
                title="Jobs by Sector (Industry-wise)",
            )
            fig_sector.update_layout(
                showlegend=False, coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter"), height=450,
            )
            st.plotly_chart(fig_sector, use_container_width=True, key="sector_chart")

        with chart_col6:
            job_type_counts = filtered["job_category"].value_counts().reset_index()
            job_type_counts.columns = ["Job Type", "Count"]

            # Custom color scheme for job types
            job_type_colors = {
                'IT / Technical': '#667eea',
                'Administrative': '#fbbf24',
                'Managerial': '#f59e0b',
                'Blue Collar': '#10b981',
                'White Collar': '#3b82f6',
                'Service Industry': '#ec4899',
                'Creative': '#8b5cf6',
                'Other': '#9ca3af'
            }

            fig_job_type = px.pie(
                job_type_counts, values="Count", names="Job Type",
                title="Jobs by Category (IT, Admin, Blue/White Collar, etc.)",
                hole=0.4,
                color_discrete_map=job_type_colors
            )
            fig_job_type.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter"), height=450,
            )
            st.plotly_chart(fig_job_type, use_container_width=True, key="job_type_chart")

        # Row 4: Detailed Sector Breakdown
        st.markdown("#### 📊 Detailed Sector Breakdown")

        # Create tabs for different sector analyses
        sector_tab1, sector_tab2, sector_tab3, sector_tab4 = st.tabs(["🏭 Top Sectors", "⚡ Energy Deep Dive", "🚢 Transportation & Shipping", "🔍 Cross Analysis"])

        with sector_tab1:
            col_a1, col_a2, col_a3 = st.columns(3)

            with col_a1:
                # Top sectors by count
                top_sectors = filtered["sector"].value_counts().head(10)
                st.markdown("**Top 10 Sectors by Job Count**")
                for idx, (sector, count) in enumerate(top_sectors.items(), 1):
                    percentage = (count / len(filtered)) * 100
                    st.markdown(f"{idx}. **{sector}**: {count:,} jobs ({percentage:.1f}%)")

            with col_a2:
                # Sectors by salary (if available)
                if filtered["salary_min"].notna().any():
                    sector_salary = filtered[filtered["salary_min"].notna()].groupby("sector").agg(
                        median_salary=("salary_min", "median"),
                        avg_salary=("salary_min", "mean"),
                        count=("salary_min", "count")
                    ).sort_values("median_salary", ascending=False).head(10)

                    st.markdown("**Top 10 Sectors by Median Salary**")
                    for idx, (sector, row) in enumerate(sector_salary.iterrows(), 1):
                        st.markdown(f"{idx}. **{sector}**: ${row['median_salary']:,.0f} (n={row['count']:.0f})")
                else:
                    st.info("No salary data available")

            with col_a3:
                # Remote work by sector
                if "remote" in filtered.columns:
                    remote_by_sector = filtered.groupby("sector").agg(
                        total=("remote", "count"),
                        remote_jobs=("remote", "sum")
                    )
                    remote_by_sector["remote_pct"] = (remote_by_sector["remote_jobs"] / remote_by_sector["total"] * 100).round(1)
                    remote_by_sector = remote_by_sector[remote_by_sector["total"] >= 5].sort_values("remote_pct", ascending=False).head(10)

                    st.markdown("**Top 10 Sectors by Remote Work %**")
                    for idx, (sector, row) in enumerate(remote_by_sector.iterrows(), 1):
                        st.markdown(f"{idx}. **{sector}**: {row['remote_pct']}% remote ({row['remote_jobs']:.0f}/{row['total']:.0f})")

        with sector_tab4:
            st.markdown("### 🔍 Cross-Analysis & Heatmaps")
            col_c1, col_c2 = st.columns(2)

            with col_c1:
                # Sector × Job Type Heatmap
                st.markdown("**Sector × Job Type Distribution**")
                cross_tab = pd.crosstab(filtered["sector"], filtered["job_category"])
                cross_tab = cross_tab.loc[cross_tab.sum(axis=1).sort_values(ascending=False).index]
                cross_tab = cross_tab.loc[:, cross_tab.sum(axis=0).sort_values(ascending=False).index]

                fig_heat = px.imshow(
                    cross_tab.values,
                    labels=dict(x="Job Type", y="Sector", color="Job Count"),
                    x=cross_tab.columns,
                    y=cross_tab.index,
                    color_continuous_scale="YlOrRd",
                    title="Sector vs Job Type Heatmap"
                )
                fig_heat.update_layout(
                    height=500,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter")
                )
                st.plotly_chart(fig_heat, use_container_width=True)

            with col_c2:
                # IT Jobs Deep Dive
                st.markdown("**IT/Tech Jobs Deep Dive**")
                it_jobs = filtered[filtered["job_category"] == "IT / Technical"]

                if len(it_jobs) > 0:
                    st.metric("Total IT Jobs", f"{len(it_jobs):,}")

                    # Top IT skills/sources
                    if "source" in it_jobs.columns:
                        it_sources = it_jobs["source"].value_counts().head(5)
                        st.markdown("**Top Sources for IT Jobs**")
                        for source, count in it_sources.items():
                            st.markdown(f"- {source}: {count:,}")

                    # IT by seniority
                    it_seniority = it_jobs["seniority_level"].value_counts()
                    st.markdown("**IT Jobs by Seniority**")
                    for seniority, count in it_seniority.items():
                        st.markdown(f"- {seniority}: {count:,}")
                else:
                    st.info("No IT jobs found in current filter")

        with sector_tab2:
            st.markdown("### ⚡ Energy Sector Deep Dive")
            col_e1, col_e2, col_e3 = st.columns(3)

            # Filter for all energy-related sectors
            energy_sectors = [s for s in filtered["sector"].unique() if 'Energy' in s]
            energy_jobs = filtered[filtered["sector"].isin(energy_sectors)]

            if len(energy_jobs) > 0:
                with col_e1:
                    st.markdown("**Energy Sector Breakdown**")
                    energy_breakdown = energy_jobs["sector"].value_counts()
                    for sector, count in energy_breakdown.items():
                        percentage = (count / len(energy_jobs)) * 100
                        st.markdown(f"- **{sector}**: {count:,} jobs ({percentage:.1f}%)")

                with col_e2:
                    st.markdown("**Energy by Job Type**")
                    energy_by_type = energy_jobs["job_category"].value_counts()
                    for job_type, count in energy_by_type.items():
                        percentage = (count / len(energy_jobs)) * 100
                        st.markdown(f"- **{job_type}**: {count:,} jobs ({percentage:.1f}%)")

                with col_e3:
                    st.markdown("**Energy by Seniority**")
                    energy_seniority = energy_jobs["seniority_level"].value_counts()
                    for seniority, count in energy_seniority.items():
                        percentage = (count / len(energy_jobs)) * 100
                        st.markdown(f"- **{seniority}**: {count:,} jobs ({percentage:.1f}%)")

                st.markdown("---")

                # Energy salary analysis
                if energy_jobs["salary_min"].notna().any():
                    col_e4, col_e5 = st.columns(2)

                    with col_e4:
                        st.markdown("**Energy Sectors by Salary**")
                        energy_salary = energy_jobs[energy_jobs["salary_min"].notna()].groupby("sector").agg(
                            median_salary=("salary_min", "median"),
                            avg_salary=("salary_min", "mean"),
                            count=("salary_min", "count")
                        ).sort_values("median_salary", ascending=False)

                        for sector, row in energy_salary.iterrows():
                            st.markdown(f"- **{sector}**: ${row['median_salary']:,.0f} median (n={row['count']:.0f})")

                    with col_e5:
                        st.markdown("**Energy Remote Work %**")
                        if "remote" in energy_jobs.columns:
                            energy_remote = energy_jobs.groupby("sector").agg(
                                total=("remote", "count"),
                                remote_jobs=("remote", "sum")
                            )
                            energy_remote["remote_pct"] = (energy_remote["remote_jobs"] / energy_remote["total"] * 100).round(1)

                            for sector, row in energy_remote.iterrows():
                                st.markdown(f"- **{sector}**: {row['remote_pct']}% remote ({row['remote_jobs']:.0f}/{row['total']:.0f})")
                else:
                    st.info("No salary data available for energy jobs")

                # Energy sources
                st.markdown("**Top Sources for Energy Jobs**")
                if "source" in energy_jobs.columns:
                    energy_sources = energy_jobs["source"].value_counts()
                    col_es1, col_es2, col_es3 = st.columns(3)
                    for idx, (source, count) in enumerate(energy_sources.items()):
                        col = [col_es1, col_es2, col_es3][idx % 3]
                        with col:
                            st.metric(source, f"{count:,} jobs")
            else:
                st.info("No energy jobs found in current filter. Try adjusting filters or searching for energy-related terms.")

        with sector_tab3:
            st.markdown("### 🚢 Transportation & Shipping Deep Dive")
            col_t1, col_t2, col_t3 = st.columns(3)

            # Filter for transportation-related sectors
            transport_sectors = [s for s in filtered["sector"].unique() if any(x in s for x in ['Shipping', 'Logistics', 'Transportation'])]
            transport_jobs = filtered[filtered["sector"].isin(transport_sectors)]

            if len(transport_jobs) > 0:
                with col_t1:
                    st.markdown("**Transportation Breakdown**")
                    transport_breakdown = transport_jobs["sector"].value_counts()
                    for sector, count in transport_breakdown.items():
                        percentage = (count / len(transport_jobs)) * 100
                        st.markdown(f"- **{sector}**: {count:,} jobs ({percentage:.1f}%)")

                with col_t2:
                    st.markdown("**By Job Type**")
                    transport_by_type = transport_jobs["job_category"].value_counts()
                    for job_type, count in transport_by_type.items():
                        percentage = (count / len(transport_jobs)) * 100
                        st.markdown(f"- **{job_type}**: {count:,} jobs ({percentage:.1f}%)")

                with col_t3:
                    st.markdown("**By Seniority**")
                    transport_seniority = transport_jobs["seniority_level"].value_counts()
                    for seniority, count in transport_seniority.items():
                        percentage = (count / len(transport_jobs)) * 100
                        st.markdown(f"- **{seniority}**: {count:,} jobs ({percentage:.1f}%)")

                st.markdown("---")

                # Transportation salary analysis
                if transport_jobs["salary_min"].notna().any():
                    col_t4, col_t5 = st.columns(2)

                    with col_t4:
                        st.markdown("**Transportation Sectors by Salary**")
                        transport_salary = transport_jobs[transport_jobs["salary_min"].notna()].groupby("sector").agg(
                            median_salary=("salary_min", "median"),
                            avg_salary=("salary_min", "mean"),
                            count=("salary_min", "count")
                        ).sort_values("median_salary", ascending=False)

                        for sector, row in transport_salary.iterrows():
                            st.markdown(f"- **{sector}**: ${row['median_salary']:,.0f} median (n={row['count']:.0f})")

                    with col_t5:
                        st.markdown("**Top Locations**")
                        if "location" in transport_jobs.columns:
                            transport_locations = transport_jobs["location"].value_counts().head(10)
                            for location, count in transport_locations.items():
                                st.markdown(f"- **{location}**: {count:,} jobs")
                else:
                    st.info("No salary data available for transportation jobs")

                # Transportation sources
                st.markdown("**Top Sources for Transportation Jobs**")
                if "source" in transport_jobs.columns:
                    transport_sources = transport_jobs["source"].value_counts()
                    col_ts1, col_ts2, col_ts3 = st.columns(3)
                    for idx, (source, count) in enumerate(transport_sources.items()):
                        col = [col_ts1, col_ts2, col_ts3][idx % 3]
                        with col:
                            st.metric(source, f"{count:,} jobs")

                # Maritime specific
                maritime_jobs = transport_jobs[transport_jobs["sector"] == "Shipping & Maritime"]
                if len(maritime_jobs) > 0:
                    st.markdown("---")
                    st.markdown("### ⚓ Maritime & Shipping Specifics")
                    col_m1, col_m2 = st.columns(2)

                    with col_m1:
                        st.metric("Maritime Jobs", f"{len(maritime_jobs):,}")
                        if "job_category" in maritime_jobs.columns:
                            st.markdown("**Maritime by Job Type**")
                            for job_type, count in maritime_jobs["job_category"].value_counts().items():
                                st.markdown(f"- {job_type}: {count:,}")

                    with col_m2:
                        st.markdown("**Top Maritime Job Titles**")
                        for title, count in maritime_jobs["title"].value_counts().head(10).items():
                            st.markdown(f"- {title}: {count:,}")
            else:
                st.info("No transportation/shipping jobs found in current filter. Try adjusting filters or searching for shipping, logistics, or transportation-related terms.")

        with sector_tab4:
            st.markdown("#### 🌳 Job Hierarchy View")
        col_d1, col_d2 = st.columns(2)

        with col_d1:
            # Sunburst: Job Type → Sector → Seniority (hierarchical view)
            sunburst_data = filtered.groupby(["job_category", "sector", "seniority_level"]).size().reset_index(name="count")
            sunburst_data = sunburst_data[sunburst_data["count"] > 0]

            if not sunburst_data.empty:
                fig_sunburst = px.sunburst(
                    sunburst_data,
                    path=["job_category", "sector", "seniority_level"],
                    values="count",
                    title="Job Distribution Hierarchy (Job Type → Sector → Seniority)",
                    color="count",
                    color_continuous_scale="RdYlGn",
                )
                fig_sunburst.update_layout(
                    height=500,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter")
                )
                st.plotly_chart(fig_sunburst, use_container_width=True)
            else:
                st.info("Not enough data for hierarchy view")

        with col_d2:
            # Treemap: Sector → Seniority
            treemap_data = filtered.groupby(["sector", "seniority_level"]).size().reset_index(name="count")
            treemap_data = treemap_data[treemap_data["count"] > 0]

            if not treemap_data.empty:
                fig_treemap = px.treemap(
                    treemap_data,
                    path=["sector", "seniority_level"],
                    values="count",
                    title="Jobs by Sector & Seniority (Treemap)",
                    color="count",
                    color_continuous_scale="Blues",
                )
                fig_treemap.update_layout(
                    height=500,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter")
                )
                st.plotly_chart(fig_treemap, use_container_width=True)
            else:
                st.info("Not enough data for treemap view")

        st.markdown("---")

        # ═════════════════ Government Standards Reference ═══════════════
        with st.expander("ℹ️ Government Classification Standards Used"):
            st.markdown("""
            ### 🏛️ Industry Classification Standards Reference

            This dashboard uses official US government classification systems for categorizing jobs and sectors:

            #### **NAICS - North American Industry Classification System**
            - **Agency**: US Census Bureau
            - **Purpose**: Classify business establishments by industry
            - **Website**: https://www.census.gov/naics/
            - **Key Sectors Used**:
              - NAICS 11: Agriculture, Forestry, Fishing and Hunting
              - NAICS 21: Mining, Quarrying, and Oil and Gas Extraction
              - NAICS 22: Utilities (Electric, Gas, Water)
              - NAICS 23: Construction
              - NAICS 31-33: Manufacturing
              - NAICS 48-49: Transportation and Warehousing
              - NAICS 51: Information (Technology)
              - NAICS 52: Finance and Insurance
              - NAICS 54: Professional, Scientific, and Technical Services
              - NAICS 61: Educational Services
              - NAICS 62: Health Care and Social Assistance

            #### **SOC - Standard Occupational Classification**
            - **Agency**: US Bureau of Labor Statistics (BLS)
            - **Purpose**: Classify workers into occupational categories
            - **Website**: https://www.bls.gov/soc/
            - **Major Groups Used**:
              - SOC 11-0000: Management Occupations
              - SOC 13-0000: Business and Financial Operations Occupations
              - SOC 15-0000: Computer and Mathematical Occupations
              - SOC 17-0000: Architecture and Engineering Occupations
              - SOC 19-0000: Life, Physical, and Social Science Occupations
              - SOC 25-0000: Educational Instruction and Library Occupations
              - SOC 27-0000: Arts, Design, Entertainment, Sports, and Media Occupations
              - SOC 29-0000: Healthcare Practitioners and Technical Occupations
              - SOC 35-0000: Food Preparation and Serving Related Occupations
              - SOC 37-0000: Building and Grounds Cleaning and Maintenance
              - SOC 39-0000: Personal Care and Service Occupations
              - SOC 41-0000: Sales and Related Occupations
              - SOC 43-0000: Office and Administrative Support Occupations
              - SOC 47-0000: Construction and Extraction Occupations
              - SOC 49-0000: Installation, Maintenance, and Repair Occupations
              - SOC 51-0000: Production Occupations
              - SOC 53-0000: Transportation and Material Moving Occupations

            #### **EEOC Job Categories**
            - **Agency**: Equal Employment Opportunity Commission
            - **Purpose**: Track employment patterns by job category
            - **Website**: https://www.eeoc.gov/statistics/employment/jobpatterns
            - **Categories Used**:
              - Officials and Managers
              - Professionals
              - Technicians
              - Sales Workers
              - Administrative Support Workers
              - Craft Workers
              - Operatives
              - Laborers
              - Service Workers

            #### **Energy Sector References**
            - **US Department of Energy**: Annual Energy Employment Reports
            - **Bureau of Labor Statistics**: Green Goods and Services Occupations
            - **International Renewable Energy Agency (IRENA)**: Renewable Energy Jobs

            #### **Transportation & Shipping References**
            - **Bureau of Transportation Statistics (BTS)**: Transportation Statistics
            - **Maritime Administration (MARAD)**: Maritime Industry Data
            - **Federal Motor Carrier Safety Administration (FMCSA)**: Trucking Industry

            #### **How Sectors are Mapped**:
            - **Energy**: Split into Oil & Gas, Renewables, Nuclear, Utilities, and Cleantech
              - Aligns with NAICS 211 (Oil & Gas), 2211 (Electric Power), 2212 (Gas)
              - Matches DOE's energy employment categories
            - **Shipping & Maritime**: Based on NAICS 483 (Water Transportation)
              - Includes ports, vessels, cargo shipping, maritime operations
            - **Transportation**: Ground (NAICS 484), Aviation (NAICS 481), Rail (NAICS 482)
            - **Manufacturing**: NAICS 31-33, split by sub-sector
            - **IT & Software**: NAICS 5112 (Software), 5415 (Computer Systems Design)
            - **Healthcare**: NAICS 62, split by clinical roles
            - **Defense**: NAICS 332, 336 (Defense Manufacturing)
            """)

    # ═══════════════ TAB 2: Job Listings ═══════════════
    with tab2:
        st.markdown(f"### 📋 {len(filtered):,} Job Listings")

        display_cols = ["title", "company", "location", "source", "sector",
                        "job_type", "salary_min", "salary_max", "employment_type",
                        "posted_date", "url"]
        available_cols = [c for c in display_cols if c in filtered.columns]
        display_df = filtered[available_cols].copy()

        if "salary_min" in display_df.columns:
            display_df["salary"] = display_df.apply(
                lambda r: f"${r['salary_min']:,.0f} - ${r['salary_max']:,.0f}"
                if pd.notna(r.get("salary_min")) and pd.notna(r.get("salary_max"))
                else (f"${r['salary_min']:,.0f}+" if pd.notna(r.get("salary_min")) else "—"),
                axis=1,
            )
            display_df = display_df.drop(columns=["salary_min", "salary_max"], errors="ignore")

        if "posted_date" in display_df.columns:
            display_df["posted_date"] = pd.to_datetime(display_df["posted_date"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")

        col_renames = {
            "title": "Title", "company": "Company", "location": "Location",
            "source": "Source", "sector": "Sector", "job_type": "Type",
            "employment_type": "Employment", "posted_date": "Posted",
            "salary": "Salary", "url": "Apply Link",
        }
        display_df = display_df.rename(columns=col_renames)

        sort_col = st.selectbox("Sort by", ["Posted", "Title", "Company", "Salary", "Sector"], index=0)
        sort_asc = st.checkbox("Ascending", value=False)
        if sort_col in display_df.columns:
            display_df = display_df.sort_values(sort_col, ascending=sort_asc, na_position="last")

        if "Apply Link" in display_df.columns:
            display_df["Apply Link"] = display_df["Apply Link"].apply(lambda x: x if pd.notna(x) and x else "—")

        st.dataframe(
            display_df, use_container_width=True, height=600,
            column_config={
                "Apply Link": st.column_config.LinkColumn("Apply Link"),
                "Salary": st.column_config.TextColumn("Salary"),
            },
        )

        csv = filtered.to_csv(index=False)
        st.download_button("📥 Download CSV", csv,
                           file_name=f"jobs_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv")

    # ═══════════════ TAB 3: Auto Apply ═══════════════
    with tab3:
        st.markdown("### 🎯 Auto Apply to Jobs")

        profiles = Profile.list_all()
        if not profiles:
            st.warning("⚠️ No profiles found. Create a profile in the **👤 Profiles** tab first.")
        else:
            profile_names = [p.name for p in profiles]
            selected_profile_name = st.selectbox("Select Profile", profile_names)
            selected_profile = next((p for p in profiles if p.name == selected_profile_name), None)

            if selected_profile:
                st.markdown(f"**{selected_profile.full_name}** · {selected_profile.email} · "
                            f"Skills: {', '.join(selected_profile.skills[:5])}")

                st.markdown("---")
                st.markdown("#### Select Jobs to Apply")

                # Show matching jobs with checkboxes
                needed_cols = ["id", "title", "company", "location", "source",
                               "sector", "job_type", "url", "unique_hash", "description",
                               "salary_min", "salary_max"]
                avail_needed = [c for c in needed_cols if c in filtered.columns]
                apply_df = filtered[avail_needed].copy()

                # Scoring — compute on apply_df directly
                if selected_profile and "id" in apply_df.columns:
                    apply_df["Match"] = apply_df.apply(
                        lambda r: f"{selected_profile.matches_job(r.to_dict()):.0%}", axis=1
                    )
                    apply_df = apply_df.sort_values("Match", ascending=False)


                # Check already applied
                existing_apps = db.get_applications_sync(profile_name=selected_profile_name)
                applied_hashes = {a.get("job_hash", "") for a in existing_apps}

                if "unique_hash" in apply_df.columns:
                    apply_df["Status"] = apply_df["unique_hash"].apply(
                        lambda h: "✅ Applied" if h in applied_hashes else "⬜ New"
                    )

                display_apply = apply_df.head(100)

                if not display_apply.empty:
                    sel_cols = ["title", "company", "location", "sector", "job_type"]
                    if "Match" in display_apply.columns:
                        sel_cols.append("Match")
                    if "Status" in display_apply.columns:
                        sel_cols.append("Status")
                    avail = [c for c in sel_cols if c in display_apply.columns]

                    selection = st.dataframe(
                        display_apply[avail].rename(columns={
                            "title": "Title", "company": "Company",
                            "location": "Location", "sector": "Sector",
                            "job_type": "Type"
                        }),
                        use_container_width=True, height=400,
                        on_select="rerun", selection_mode="multi-row",
                        key="apply_table",
                    )

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("🚀 Queue Selected for Auto-Apply", type="primary"):
                            if selection and selection.selection and selection.selection.rows:
                                queued = 0
                                for idx in selection.selection.rows:
                                    row = display_apply.iloc[idx]
                                    if "id" in row and "unique_hash" in row:
                                        cl = selected_profile.render_cover_letter(
                                            row.get("title", ""), row.get("company", "")
                                        )
                                        db.queue_application(
                                            int(row["id"]), row["unique_hash"],
                                            selected_profile_name, cl
                                        )
                                        queued += 1
                                st.success(f"✅ Queued {queued} jobs for auto-apply!")
                                st.rerun()
                            else:
                                st.warning("Select jobs from the table above first")

                    with col_b:
                        if st.button("📋 Queue Top 20 Matches"):
                            queued = 0
                            for _, row in display_apply.head(20).iterrows():
                                if "id" in row and "unique_hash" in row:
                                    h = row["unique_hash"]
                                    if h not in applied_hashes:
                                        cl = selected_profile.render_cover_letter(
                                            row.get("title", ""), row.get("company", "")
                                        )
                                        db.queue_application(
                                            int(row["id"]), h, selected_profile_name, cl
                                        )
                                        queued += 1
                            st.success(f"✅ Queued {queued} jobs!")
                            st.rerun()

                    st.markdown("---")
                    st.markdown("#### ▶️ Run Auto-Apply")
                    st.info("Auto-apply uses Playwright headless Chrome. It will attempt to fill forms, "
                            "upload your resume, and submit. Complex ATS forms are marked for manual apply.")

                    num_to_apply = st.slider("Number of jobs to process", 1, 50, 10)

                    if st.button("▶️ Start Auto-Apply", type="primary"):
                        import subprocess, threading

                        status_placeholder = st.empty()
                        progress_placeholder = st.empty()
                        status_placeholder.info("⚡ Auto-apply is starting...")

                        apply_script = f"""
import asyncio, sys, os
sys.path.insert(0, '{PROJECT_ROOT}')
os.chdir('{PROJECT_ROOT}')
from agents.apply_agent import ApplyAgent
from models.profile import Profile
from models.database import JobDatabase
import config

async def run():
    p = Profile.load('{selected_profile_name}')
    db = JobDatabase(config.DB_PATH)
    agent = ApplyAgent(p, db)
    stats = await agent.apply_to_queued(limit={num_to_apply})
    print(f"RESULT: applied={{stats['applied']}}, manual={{stats['manual']}}, failed={{stats['failed']}}, skipped={{stats['skipped']}}")

asyncio.run(run())
"""
                        try:
                            result = subprocess.run(
                                [os.path.join(PROJECT_ROOT, "venv", "bin", "python"), "-c", apply_script],
                                capture_output=True, text=True, timeout=600,
                                cwd=PROJECT_ROOT,
                            )
                            output = result.stdout + result.stderr

                            # Parse results
                            result_line = [l for l in output.split('\n') if l.startswith('RESULT:')]
                            if result_line:
                                status_placeholder.success(f"✅ Auto-apply complete! {result_line[0].replace('RESULT: ', '')}")
                            elif result.returncode != 0:
                                status_placeholder.error(f"❌ Auto-apply failed:\n```\n{output[-1000:]}\n```")
                            else:
                                status_placeholder.success("✅ Auto-apply finished!")

                            # Show details
                            if output.strip():
                                with progress_placeholder.expander("📋 Full Output", expanded=False):
                                    st.code(output[-3000:], language="text")

                        except subprocess.TimeoutExpired:
                            status_placeholder.error("⏰ Auto-apply timed out after 10 minutes")
                        except Exception as e:
                            status_placeholder.error(f"❌ Error: {e}")

                        st.rerun()

    # ═══════════════ TAB 4: Profiles ═══════════════
    with tab4:
        st.markdown("### 👤 Application Profiles")

        profiles = Profile.list_all()

        col_list, col_form = st.columns([1, 2])

        with col_list:
            st.markdown("#### Saved Profiles")
            if profiles:
                for p in profiles:
                    skills_preview = ", ".join(p.skills[:3])
                    st.markdown(f"""
                    <div class="profile-card">
                        <strong>{p.name}</strong><br>
                        <small>{p.full_name} · {p.email}</small><br>
                        <small>Skills: {skills_preview}{'...' if len(p.skills) > 3 else ''}</small><br>
                        <small>Experience: {p.years_experience} years</small>
                    </div>
                    """, unsafe_allow_html=True)
                
                del_profile = st.selectbox("Delete profile:", [""] + [p.name for p in profiles])
                if del_profile and st.button("🗑️ Delete", type="secondary"):
                    Profile.delete(del_profile)
                    st.success(f"Deleted '{del_profile}'")
                    st.rerun()
            else:
                st.info("No profiles yet. Create one →")

        with col_form:
            st.markdown("#### Create / Edit Profile")

            # Pre-fill if editing
            edit_names = ["New Profile"] + [p.name for p in profiles]
            editing = st.selectbox("Edit existing or create new:", edit_names)
            edit_profile = None
            if editing != "New Profile":
                edit_profile = Profile.load(editing)

            with st.form("profile_form"):
                name = st.text_input("Profile Name *", value=edit_profile.name if edit_profile else "",
                                     placeholder="e.g. Senior Engineer")
                full_name = st.text_input("Full Name *", value=edit_profile.full_name if edit_profile else "")
                email = st.text_input("Email *", value=edit_profile.email if edit_profile else "")
                phone = st.text_input("Phone", value=edit_profile.phone if edit_profile else "")

                c1, c2 = st.columns(2)
                with c1:
                    years_exp = st.number_input("Years Experience", 0, 50,
                                                value=edit_profile.years_experience if edit_profile else 0)
                    education = st.text_input("Education",
                                              value=edit_profile.education if edit_profile else "",
                                              placeholder="e.g. MS Computer Science")
                with c2:
                    clearance = st.selectbox("Security Clearance",
                                             ["none", "secret", "top_secret", "sci"],
                                             index=["none", "secret", "top_secret", "sci"].index(
                                                 edit_profile.security_clearance if edit_profile and edit_profile.security_clearance in ["none", "secret", "top_secret", "sci"] else "none"
                                             ))
                    location_pref = st.text_input("Location Preference",
                                                   value=edit_profile.location_preference if edit_profile else "",
                                                   placeholder="e.g. Remote, Washington DC")

                skills_str = st.text_area("Skills (comma-separated)",
                                           value=", ".join(edit_profile.skills) if edit_profile else "",
                                           placeholder="Python, AWS, Machine Learning, SQL...")

                all_categories = list(config.SEARCH_CATEGORIES.keys())
                pref_cats = st.multiselect("Preferred Categories", all_categories,
                                            default=edit_profile.preferred_categories if edit_profile else [])
                pref_types = st.multiselect("Preferred Job Types",
                                             ["federal", "state", "corporate", "remote"],
                                             default=edit_profile.preferred_job_types if edit_profile else [])

                c3, c4 = st.columns(2)
                with c3:
                    sal_min = st.number_input("Target Salary Min ($)", 0, 500000,
                                              value=int(edit_profile.target_salary_min) if edit_profile and edit_profile.target_salary_min else 0,
                                              step=5000)
                with c4:
                    sal_max = st.number_input("Target Salary Max ($)", 0, 500000,
                                              value=int(edit_profile.target_salary_max) if edit_profile and edit_profile.target_salary_max else 0,
                                              step=5000)

                resume_col1, resume_col2 = st.columns([1, 1])
                with resume_col1:
                    resume_path_input = st.text_input("Resume Path",
                                                 value=edit_profile.resume_path if edit_profile else "",
                                                 placeholder="/path/to/resume.pdf")
                    if edit_profile and edit_profile.resume_path and os.path.exists(edit_profile.resume_path):
                        st.caption("✅ Valid resume found at path.")
                with resume_col2:
                    uploaded_resume = st.file_uploader("Upload PDF Resume (Overrides Path)", type=["pdf"])

                cover_template = st.text_area(
                    "Cover Letter Template",
                    value=edit_profile.cover_letter_template if edit_profile else "",
                    placeholder="Dear Hiring Manager,\n\nI am excited about the {job_title} role at {company}...\n\nUse {job_title}, {company}, {skills}, {years_experience}, {full_name}",
                    height=150,
                )

                linkedin = st.text_input("LinkedIn URL",
                                          value=edit_profile.linkedin_url if edit_profile else "")
                portfolio = st.text_input("Portfolio URL",
                                           value=edit_profile.portfolio_url if edit_profile else "")

                submitted = st.form_submit_button("💾 Save Profile", type="primary")

                if submitted and name and full_name and email:
                    final_resume_path = resume_path_input
                    
                    if uploaded_resume is not None:
                        resumes_dir = os.path.join(PROJECT_ROOT, "data", "resumes")
                        os.makedirs(resumes_dir, exist_ok=True)
                        file_ext = os.path.splitext(uploaded_resume.name)[1]
                        safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
                        file_name = f"{safe_name.replace(' ', '_').lower()}_resume{file_ext}"
                        final_resume_path = os.path.join(resumes_dir, file_name)
                        with open(final_resume_path, "wb") as f:
                            f.write(uploaded_resume.getbuffer())
                            
                    skills_list = [s.strip() for s in skills_str.split(",") if s.strip()]
                    profile = Profile(
                        name=name, full_name=full_name, email=email, phone=phone,
                        resume_path=final_resume_path, cover_letter_template=cover_template,
                        skills=skills_list, preferred_categories=pref_cats,
                        preferred_job_types=pref_types,
                        target_salary_min=float(sal_min) if sal_min else None,
                        target_salary_max=float(sal_max) if sal_max else None,
                        years_experience=years_exp, security_clearance=clearance,
                        education=education, linkedin_url=linkedin,
                        portfolio_url=portfolio, location_preference=location_pref,
                    )
                    profile.save()
                    st.success(f"✅ Profile '{name}' saved!")
                    st.rerun()
                elif submitted:
                    st.error("Please fill in Name, Full Name, and Email.")

    # ═══════════════ TAB 5: Applications ═══════════════
    with tab5:
        st.markdown("### 📈 Application Tracking")

        app_stats = db.get_application_stats_sync()

        if app_stats["total"] == 0:
            st.info("No applications yet. Queue jobs in the **🎯 Auto Apply** tab to get started.")
        else:
            # Funnel metrics
            by_status = app_stats.get("by_status", {})
            funnel_cols = st.columns(6)
            statuses = [
                ("queued", "⏳ Queued", "#e0e7ff"),
                ("applied", "✅ Applied", "#d1fae5"),
                ("manual", "✋ Manual", "#fef3c7"),
                ("failed", "❌ Failed", "#fde2e2"),
                ("interview", "🎤 Interview", "#dbeafe"),
                ("offered", "🎉 Offered", "#d1fae5"),
            ]

            for col, (status, label, color) in zip(funnel_cols, statuses):
                count = by_status.get(status, 0)
                with col:
                    st.markdown(f"""
                    <div class="funnel-step" style="background: {color};">
                        <div style="font-size: 2rem;">{count}</div>
                        <div>{label}</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("---")

            # Filter applications
            ac1, ac2 = st.columns(2)
            with ac1:
                app_profiles = Profile.list_all()
                app_profile_filter = st.selectbox(
                    "Filter by Profile", ["All"] + [p.name for p in app_profiles],
                    key="app_profile_filter"
                )
            with ac2:
                app_status_filter = st.selectbox(
                    "Filter by Status", ["All", "queued", "applied", "manual", "failed", "interview", "offered"],
                    key="app_status_filter"
                )

            pf = app_profile_filter if app_profile_filter != "All" else ""
            sf = app_status_filter if app_status_filter != "All" else ""
            applications = db.get_applications_sync(profile_name=pf, status=sf)

            if applications:
                app_df = pd.DataFrame(applications)
                display_cols_app = ["profile_name", "title", "company", "location",
                                    "status", "applied_at", "notes", "url"]
                avail_app = [c for c in display_cols_app if c in app_df.columns]
                disp_app = app_df[avail_app].rename(columns={
                    "profile_name": "Profile", "title": "Job Title", "company": "Company",
                    "location": "Location", "status": "Status", "applied_at": "Applied At",
                    "notes": "Notes", "url": "Link",
                })

                st.dataframe(
                    disp_app, use_container_width=True, height=400,
                    column_config={"Link": st.column_config.LinkColumn("Link")},
                )

                # Manual status update
                st.markdown("#### Update Application Status")
                uc1, uc2, uc3 = st.columns(3)
                with uc1:
                    app_id_update = st.number_input("Application ID", min_value=1, step=1)
                with uc2:
                    new_status = st.selectbox("New Status",
                                              ["applied", "interview", "offered", "rejected", "failed"])
                with uc3:
                    update_notes = st.text_input("Notes", placeholder="Interview scheduled...")

                if st.button("📝 Update Status"):
                    db.update_application_status(int(app_id_update), new_status, notes=update_notes)
                    st.success(f"Updated application #{app_id_update} to '{new_status}'")
                    st.rerun()
            else:
                st.info("No applications match the current filters.")

    # ═══════════════ TAB 6: Analytics ═══════════════
    with tab6:
        st.markdown("### 💰 Salary & Market Analytics")

        sal_df = filtered[filtered["salary_min"] > 0].copy()
        sal_df["salary_mid"] = (sal_df["salary_min"] + sal_df["salary_max"]) / 2
        # seniority_level is already populated globally

        # ── Key Salary Metrics ──
        if len(sal_df) > 0:
            sm1, sm2, sm3, sm4, sm5 = st.columns(5)
            med_sal = sal_df["salary_mid"].median()
            p25 = sal_df["salary_mid"].quantile(0.25)
            p75 = sal_df["salary_mid"].quantile(0.75)
            avg_sal = sal_df["salary_mid"].mean()
            max_sal = sal_df["salary_max"].max()
            with sm1: render_metric(f"${med_sal:,.0f}", "Median Salary", "#059669")
            with sm2: render_metric(f"${p25:,.0f}", "25th Percentile", "#2563eb")
            with sm3: render_metric(f"${p75:,.0f}", "75th Percentile", "#7c3aed")
            with sm4: render_metric(f"${avg_sal:,.0f}", "Average", "#d97706")
            with sm5: render_metric(f"${max_sal:,.0f}", "Highest", "#dc2626")

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Row 1: Salary Distribution + Salary by Category ──
            a_c1, a_c2 = st.columns(2)

            with a_c1:
                fig_hist = px.histogram(
                    sal_df, x="salary_mid", nbins=50,
                    title="Salary Distribution",
                    labels={"salary_mid": "Mid-Point Salary ($)"},
                    color_discrete_sequence=["#667eea"],
                )
                fig_hist.add_vline(x=med_sal, line_dash="dash", line_color="#e53e3e",
                                   annotation_text=f"Median ${med_sal:,.0f}")
                fig_hist.update_layout(
                    showlegend=False, height=400,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                    yaxis_title="Number of Jobs",
                )
                st.plotly_chart(fig_hist, use_container_width=True, key="sal_hist")

            with a_c2:
                sector_salary = sal_df.groupby("sector").agg(
                    median_sal=("salary_mid", "median"),
                    p25=("salary_mid", lambda x: x.quantile(0.25)),
                    p75=("salary_mid", lambda x: x.quantile(0.75)),
                    count=("salary_mid", "count"),
                ).reset_index().sort_values("median_sal", ascending=True)

                fig_sector = go.Figure()
                fig_sector.add_trace(go.Bar(
                    y=sector_salary["sector"], x=sector_salary["median_sal"],
                    orientation="h", name="Median",
                    marker_color="#667eea",
                    text=[f"${v:,.0f}" for v in sector_salary["median_sal"]],
                    textposition="outside",
                ))
                fig_sector.add_trace(go.Bar(
                    y=sector_salary["sector"], x=sector_salary["p75"] - sector_salary["median_sal"],
                    orientation="h", name="75th %",
                    marker_color="rgba(124,58,237,0.4)", base=sector_salary["median_sal"],
                ))
                fig_sector.update_layout(
                    title="Salary by Sector (Median + 75th)",
                    barmode="stack", height=400, showlegend=True,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                    xaxis_title="Salary ($)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig_sector, use_container_width=True, key="sal_by_sector")

            # ── Row 2: Seniority Distribution + Salary by Seniority ──
            a_c3, a_c4 = st.columns(2)

            seniority_order = ['Entry', 'Junior', 'Mid-Level', 'Senior', 'Lead / Principal', 'Director / VP', 'C-Level']
            all_seniority = filtered.copy()
            all_seniority["seniority_level"] = all_seniority["title"].apply(classify_seniority)

            with a_c3:
                sen_counts = all_seniority["seniority_level"].value_counts().reindex(seniority_order, fill_value=0)
                fig_sen = px.bar(
                    x=sen_counts.index, y=sen_counts.values,
                    title="Jobs by Seniority Level",
                    labels={"x": "Seniority", "y": "Jobs"},
                    color=sen_counts.values,
                    color_continuous_scale="Viridis",
                )
                fig_sen.update_layout(
                    showlegend=False, coloraxis_showscale=False, height=400,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                )
                st.plotly_chart(fig_sen, use_container_width=True, key="sen_dist")

            with a_c4:
                sen_salary = sal_df.groupby("seniority_level").agg(
                    median_sal=("salary_mid", "median"),
                    count=("salary_mid", "count"),
                ).reindex(seniority_order).dropna().reset_index()

                fig_sen_sal = px.bar(
                    sen_salary, x="seniority_level", y="median_sal",
                    title="Median Salary by Seniority",
                    labels={"seniority_level": "Seniority", "median_sal": "Median Salary ($)"},
                    color="median_sal",
                    color_continuous_scale="RdYlGn",
                    text=[f"${v:,.0f}" for v in sen_salary["median_sal"]],
                )
                fig_sen_sal.update_layout(
                    showlegend=False, coloraxis_showscale=False, height=400,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                )
                fig_sen_sal.update_traces(textposition="outside")
                st.plotly_chart(fig_sen_sal, use_container_width=True, key="sal_by_sen")

            # ── Row 3: Salary by Job Type + Employment Type ──
            a_c5, a_c6 = st.columns(2)

            with a_c5:
                type_salary = sal_df.groupby("job_type").agg(
                    min_sal=("salary_min", "median"),
                    mid_sal=("salary_mid", "median"),
                    max_sal=("salary_max", "median"),
                    count=("salary_mid", "count"),
                ).reset_index()
                type_salary = type_salary[type_salary["count"] >= 5]  # min sample

                fig_type = go.Figure()
                for _, row in type_salary.iterrows():
                    fig_type.add_trace(go.Bar(
                        x=[row["job_type"]], y=[row["max_sal"] - row["min_sal"]],
                        base=[row["min_sal"]], name=row["job_type"],
                        text=[f"${row['mid_sal']:,.0f}"], textposition="inside",
                        marker_color={'corporate': '#667eea', 'federal': '#1a5276',
                                      'state': '#065f46', 'remote': '#7c3aed'}.get(row['job_type'], '#94a3b8'),
                    ))
                fig_type.update_layout(
                    title="Salary Range by Job Type (Median Min → Max)",
                    yaxis_title="Salary ($)", height=400, showlegend=False,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                )
                st.plotly_chart(fig_type, use_container_width=True, key="sal_by_type")

            with a_c6:
                emp_type = filtered["employment_type"].replace('', 'Not Specified')
                emp_counts = emp_type.value_counts().head(8).reset_index()
                emp_counts.columns = ["Type", "Count"]
                fig_emp = px.pie(
                    emp_counts, values="Count", names="Type",
                    title="Employment Type Breakdown", hole=0.45,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig_emp.update_layout(
                    height=400,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                )
                st.plotly_chart(fig_emp, use_container_width=True, key="emp_type")

            # ── Row 4: Posting Trends + Top Employers by Salary ──
            a_c7, a_c8 = st.columns(2)

            with a_c7:
                if "posted_date" in filtered.columns:
                    trend_df = filtered.copy()
                    trend_df["post_date"] = pd.to_datetime(trend_df["posted_date"], errors="coerce").dt.date
                    daily = trend_df.groupby("post_date").size().reset_index(name="Jobs Posted")
                    daily = daily.sort_values("post_date")
                    daily = daily[daily["Jobs Posted"] > 0]

                    if len(daily) > 1:
                        fig_trend = px.area(
                            daily, x="post_date", y="Jobs Posted",
                            title="Job Posting Trends Over Time",
                            labels={"post_date": "Date"},
                            color_discrete_sequence=["#667eea"],
                        )
                        fig_trend.update_layout(
                            height=400,
                            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="Inter"),
                        )
                        st.plotly_chart(fig_trend, use_container_width=True, key="posting_trend")
                    else:
                        fig_trend = px.bar(
                            daily, x="post_date", y="Jobs Posted",
                            title="Job Posting Trends",
                            labels={"post_date": "Date"},
                            color_discrete_sequence=["#667eea"],
                        )
                        fig_trend.update_layout(
                            height=400,
                            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                            font=dict(family="Inter"),
                        )
                        st.plotly_chart(fig_trend, use_container_width=True, key="posting_trend")

            with a_c8:
                top_emp = sal_df.groupby("company").agg(
                    median_sal=("salary_mid", "median"),
                    count=("salary_mid", "count"),
                ).reset_index()
                top_emp = top_emp[top_emp["count"] >= 3].sort_values("median_sal", ascending=False).head(15)

                if len(top_emp) > 0:
                    fig_top = px.bar(
                        top_emp.sort_values("median_sal", ascending=True),
                        y="company", x="median_sal",
                        orientation="h",
                        title="Top 15 Employers by Median Salary (3+ postings)",
                        labels={"company": "Company", "median_sal": "Median Salary ($)"},
                        color="median_sal",
                        color_continuous_scale="YlOrRd",
                        text=[f"${v:,.0f}" for v in top_emp.sort_values('median_sal', ascending=True)["median_sal"]],
                    )
                    fig_top.update_layout(
                        showlegend=False, coloraxis_showscale=False, height=400,
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="Inter"),
                    )
                    fig_top.update_traces(textposition="outside")
                    st.plotly_chart(fig_top, use_container_width=True, key="top_employers")
                else:
                    st.info("Not enough employer salary data for this view.")

            # ── Row 5: Salary Heatmap — Sector × Seniority ──
            st.markdown("---")
            st.markdown("#### 🔥 Salary Heatmap: Sector × Seniority")

            heat_data = sal_df.groupby(["sector", "seniority_level"])["salary_mid"].median().reset_index()
            heat_pivot = heat_data.pivot(index="sector", columns="seniority_level", values="salary_mid")
            heat_pivot = heat_pivot.reindex(columns=seniority_order)
            heat_pivot = heat_pivot.dropna(how="all")

            if not heat_pivot.empty:
                fig_heat = go.Figure(data=go.Heatmap(
                    z=heat_pivot.values,
                    x=heat_pivot.columns.tolist(),
                    y=heat_pivot.index.tolist(),
                    colorscale="RdYlGn",
                    text=[[f"${v:,.0f}" if not np.isnan(v) else "" for v in row] for row in heat_pivot.values],
                    texttemplate="%{text}",
                    hovertemplate="Sector: %{y}<br>Seniority: %{x}<br>Median Salary: %{text}<extra></extra>",
                ))
                fig_heat.update_layout(
                    height=450,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter"),
                    xaxis_title="Seniority Level",
                    yaxis_title="Sector",
                )
                st.plotly_chart(fig_heat, use_container_width=True, key="sal_heatmap")
            else:
                st.info("Not enough cross-tabulated data for the heatmap.")

        else:
            st.warning("⚠️ No salary data available in the current filter. Adjust filters to see salary analytics.")

    # ═══════════════ TAB 7: Company Tracker ═══════════════
    with tab7:
        st.markdown("### 🏢 Company Tracker")
        st.markdown("Track jobs directly from company career pages via **Greenhouse**, **Lever**, and **Ashby** ATS APIs — free, no auth needed.")

        # Load tracked companies
        tracked_path = config.TRACKED_COMPANIES_PATH
        if tracked_path.exists():
            with open(tracked_path) as f:
                tracked = json.load(f)
        else:
            tracked = []

        # ── Tech Stack Extraction ──
        import sqlite3 as _sqlite3
        import re as _re
        from collections import Counter as _Counter, defaultdict as _defaultdict

        TECH_CATALOG = {
            "Languages": [
                "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust",
                r"C\+\+", "C#", "Ruby", "Scala", "Kotlin", "Swift", "PHP",
            ],
            "Frontend": ["React", "Angular", "Vue", "Next.js", "HTML", "CSS"],
            "Backend": [
                "Node.js", "Django", "Flask", "Spring", "FastAPI", "Rails",
                "GraphQL", "REST", "gRPC", "Microservices",
            ],
            "Cloud & Infra": [
                "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform",
                "Linux", "CI/CD", "Jenkins", "GitHub Actions",
            ],
            "Databases": [
                "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
                "Kafka", "SQL", "NoSQL", "Snowflake", "BigQuery", "DynamoDB",
            ],
            "ML & Data": [
                "Machine Learning", "Deep Learning", "NLP",
                "Computer Vision", "TensorFlow", "PyTorch",
                "Spark", "Hadoop", "Airflow", "Databricks", "LLM",
            ],
        }

        _all_techs = []
        _tech_to_category = {}
        for _cat, _techs in TECH_CATALOG.items():
            for _t in _techs:
                _all_techs.append(_t)
                _norm = _t.replace(r"\+", "+")
                _tech_to_category[_norm] = _cat

        def _extract_tech_stacks():
            """Extract tech stacks from career job descriptions."""
            company_techs = {}
            try:
                conn = _sqlite3.connect(str(config.DB_PATH))
                rows = conn.execute(
                    "SELECT company, description FROM jobs WHERE source='careers' AND description != ''"
                ).fetchall()
                conn.close()
            except Exception:
                return {}
            for company, desc in rows:
                if not desc:
                    continue
                if company not in company_techs:
                    company_techs[company] = {}
                for tech in _all_techs:
                    pattern = r'\b' + tech + r'\b'
                    if _re.search(pattern, desc, _re.IGNORECASE):
                        norm = tech.replace(r"\+", "+")
                        company_techs[company][norm] = company_techs[company].get(norm, 0) + 1
            return company_techs

        company_tech_data = _extract_tech_stacks()

        # ── Current tracked companies table ──
        if tracked:
            # --- Tech filter ---
            all_found_techs = set()
            for techs in company_tech_data.values():
                all_found_techs.update(techs.keys())
            sorted_techs = sorted(all_found_techs)

            tech_filter = st.multiselect(
                "🔧 Filter by Tech Stack",
                options=sorted_techs,
                default=[],
                key="tech_stack_filter",
                help="Filter companies that use specific technologies",
            )

            if tech_filter:
                filtered_companies = []
                for c in tracked:
                    techs = company_tech_data.get(c["name"], {})
                    if all(t in techs for t in tech_filter):
                        filtered_companies.append(c)
                display_tracked = filtered_companies
                if not display_tracked:
                    st.warning("No companies match all selected technologies.")
            else:
                display_tracked = tracked

            st.markdown(f"**Showing {len(display_tracked)} of {len(tracked)} companies:**")

            # Query DB directly for ALL careers jobs
            careers_counts = {}
            try:
                conn = _sqlite3.connect(str(config.DB_PATH))
                rows = conn.execute(
                    "SELECT company, COUNT(*) FROM jobs WHERE source='careers' GROUP BY company"
                ).fetchall()
                conn.close()
                careers_counts = {row[0]: row[1] for row in rows}
            except Exception:
                pass

            board_urls = {
                "greenhouse": "https://boards.greenhouse.io/{}",
                "lever": "https://jobs.lever.co/{}",
                "ashby": "https://jobs.ashbyhq.com/{}",
            }

            tbl_data = []
            for c in display_tracked:
                platform_emoji = {"greenhouse": "🌱", "lever": "🔧", "ashby": "🟣"}.get(c["platform"], "⚙️")
                count = careers_counts.get(c["name"], 0)
                url_template = board_urls.get(c["platform"], "")
                board_url = url_template.format(c["slug"]) if url_template else ""
                techs = company_tech_data.get(c["name"], {})
                top_techs = sorted(techs.items(), key=lambda x: x[1], reverse=True)[:5]
                tech_str = ", ".join(t[0] for t in top_techs) if top_techs else "—"
                tbl_data.append({
                    "Platform": f"{platform_emoji} {c['platform'].title()}",
                    "Company": c["name"],
                    "Board URL": board_url,
                    "Jobs": count,
                    "Top Tech Stack": tech_str,
                })

            tbl_df = pd.DataFrame(tbl_data)
            st.dataframe(
                tbl_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Board URL": st.column_config.LinkColumn("Board URL", display_text="Open →"),
                    "Jobs": st.column_config.NumberColumn("Jobs", format="%d"),
                },
            )

            # ── Tech Radar Chart ──
            st.markdown("---")
            st.markdown("#### 🕸️ Tech Stack Radar")

            companies_with_data = [c["name"] for c in display_tracked if c["name"] in company_tech_data]
            if companies_with_data:
                # Build category scores for each company (sum mentions per category)
                radar_categories = list(TECH_CATALOG.keys())

                def _company_category_scores(company_name):
                    techs = company_tech_data.get(company_name, {})
                    scores = []
                    for cat_name, cat_techs in TECH_CATALOG.items():
                        total = 0
                        for tech in cat_techs:
                            norm = tech.replace(r"\+", "+")
                            total += techs.get(norm, 0)
                        scores.append(total)
                    return scores

                # Let user pick companies for the radar (default: top 5 by job count)
                sorted_by_data = sorted(
                    companies_with_data,
                    key=lambda c: sum(company_tech_data.get(c, {}).values()),
                    reverse=True,
                )
                default_radar = sorted_by_data[:5]
                radar_selection = st.multiselect(
                    "Select companies to compare",
                    options=sorted_by_data,
                    default=default_radar,
                    key="radar_company_select",
                )

                if radar_selection:
                    # Vibrant color palette for radar traces
                    radar_colors = [
                        "rgba(99, 102, 241, 0.8)",   # indigo
                        "rgba(236, 72, 153, 0.8)",   # pink
                        "rgba(16, 185, 129, 0.8)",   # emerald
                        "rgba(245, 158, 11, 0.8)",   # amber
                        "rgba(139, 92, 246, 0.8)",   # violet
                        "rgba(6, 182, 212, 0.8)",    # cyan
                        "rgba(244, 63, 94, 0.8)",    # rose
                        "rgba(34, 197, 94, 0.8)",    # green
                        "rgba(251, 146, 60, 0.8)",   # orange
                        "rgba(59, 130, 246, 0.8)",   # blue
                    ]
                    fill_colors = [
                        "rgba(99, 102, 241, 0.15)",
                        "rgba(236, 72, 153, 0.15)",
                        "rgba(16, 185, 129, 0.15)",
                        "rgba(245, 158, 11, 0.15)",
                        "rgba(139, 92, 246, 0.15)",
                        "rgba(6, 182, 212, 0.15)",
                        "rgba(244, 63, 94, 0.15)",
                        "rgba(34, 197, 94, 0.15)",
                        "rgba(251, 146, 60, 0.15)",
                        "rgba(59, 130, 246, 0.15)",
                    ]

                    fig_radar = go.Figure()
                    for i, comp in enumerate(radar_selection):
                        scores = _company_category_scores(comp)
                        color_idx = i % len(radar_colors)
                        fig_radar.add_trace(go.Scatterpolar(
                            r=scores + [scores[0]],  # close the polygon
                            theta=radar_categories + [radar_categories[0]],
                            fill='toself',
                            fillcolor=fill_colors[color_idx],
                            line=dict(color=radar_colors[color_idx], width=2.5),
                            name=comp,
                            hovertemplate="<b>%{theta}</b>: %{r} mentions<extra>" + comp + "</extra>",
                        ))

                    fig_radar.update_layout(
                        polar=dict(
                            radialaxis=dict(
                                visible=True,
                                showticklabels=True,
                                gridcolor="rgba(128,128,128,0.2)",
                            ),
                            angularaxis=dict(
                                gridcolor="rgba(128,128,128,0.2)",
                            ),
                            bgcolor="rgba(0,0,0,0)",
                        ),
                        showlegend=True,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=-0.2,
                            xanchor="center",
                            x=0.5,
                        ),
                        height=550,
                        margin=dict(l=60, r=60, t=40, b=60),
                        paper_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

                # ── Tech by Category breakdown (synced with radar selection) ──
                category_companies = radar_selection if radar_selection else companies_with_data
                st.markdown(f"#### 📊 Technology Categories — {len(category_companies)} companies selected")
                cat_cols = st.columns(len(TECH_CATALOG))
                for idx, (cat_name, cat_techs) in enumerate(TECH_CATALOG.items()):
                    with cat_cols[idx]:
                        st.markdown(f"**{cat_name}**")
                        cat_counts = []
                        for tech in cat_techs:
                            norm = tech.replace(r"\+", "+")
                            total = sum(company_tech_data.get(c, {}).get(norm, 0) for c in category_companies)
                            if total > 0:
                                cat_counts.append((norm, total))
                        cat_counts.sort(key=lambda x: x[1], reverse=True)
                        for tech_name, count in cat_counts[:6]:
                            st.markdown(f"- `{tech_name}` ({count})")
                        if not cat_counts:
                            st.caption("No data")
            else:
                st.info("Run the careers agent to populate tech stack data.")
        else:
            st.info("No companies tracked yet. Add companies below to start fetching career-page jobs.")

        st.markdown("---")

        # ── Add new company ──
        st.markdown("#### ➕ Add Company")
        add_cols = st.columns([3, 3, 3, 2])
        with add_cols[0]:
            new_name = st.text_input("Company Name", key="tracker_name", placeholder="e.g. Tesla")
        with add_cols[1]:
            new_slug = st.text_input("Board Slug", key="tracker_slug", placeholder="e.g. tesla")
        with add_cols[2]:
            new_platform = st.selectbox("ATS Platform", ["greenhouse", "lever", "ashby", "workday"], key="tracker_platform")
        with add_cols[3]:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✅ Add Company", use_container_width=True, key="btn_add_company"):
                if new_name and new_slug:
                    existing_slugs = {c["slug"] for c in tracked}
                    if new_slug in existing_slugs:
                        st.warning(f"Company '{new_slug}' is already tracked.")
                    else:
                        tracked.append({"name": new_name, "slug": new_slug, "platform": new_platform})
                        with open(tracked_path, "w") as f:
                            json.dump(tracked, f, indent=2)
                        st.success(f"✅ Added **{new_name}** ({new_platform})")
                        st.rerun()
                else:
                    st.warning("Please fill in both Company Name and Board Slug.")

        # ── Quick-add presets ──
        quick_add_companies = [
            {"name": "Google", "slug": "google", "platform": "greenhouse"},
            {"name": "Meta", "slug": "meta", "platform": "greenhouse"},
            {"name": "Apple", "slug": "apple", "platform": "greenhouse"},
            {"name": "Microsoft", "slug": "microsoft", "platform": "workday"},
            {"name": "Amazon", "slug": "amazon", "platform": "greenhouse"},
            {"name": "Tesla", "slug": "tesla", "platform": "greenhouse"},
            {"name": "Mastercard", "slug": "mastercard/CorporateCareers", "platform": "workday"},
            {"name": "Capital One", "slug": "capitalone/Capital_One", "platform": "workday"},
            {"name": "Uber", "slug": "uber", "platform": "greenhouse"},
            {"name": "Lyft", "slug": "lyft", "platform": "greenhouse"},
            {"name": "Block", "slug": "block", "platform": "greenhouse"},
            {"name": "Snap", "slug": "snap", "platform": "greenhouse"},
            {"name": "Pinterest", "slug": "pinterest", "platform": "greenhouse"},
            {"name": "Twilio", "slug": "twilio", "platform": "greenhouse"},
            {"name": "Databricks", "slug": "databricks", "platform": "greenhouse"},
            {"name": "Scale AI", "slug": "scaleai", "platform": "ashby"},
        ]

        existing_slugs = {c["slug"] for c in tracked}
        available_presets = [c for c in quick_add_companies if c["slug"] not in existing_slugs]

        if available_presets:
            st.markdown("#### ⚡ Quick Add")
            preset_cols = st.columns(5)
            for i, preset in enumerate(available_presets[:10]):
                with preset_cols[i % 5]:
                    if st.button(f"+ {preset['name']}", key=f"quick_add_{preset['slug']}", use_container_width=True):
                        tracked.append(preset)
                        with open(tracked_path, "w") as f:
                            json.dump(tracked, f, indent=2)
                        st.success(f"✅ Added {preset['name']}")
                        st.rerun()

        st.markdown("---")

        # ── Remove companies ──
        if tracked:
            st.markdown("#### 🗑️ Remove Companies")
            remove_names = st.multiselect(
                "Select companies to remove:",
                options=[c["name"] for c in tracked],
                key="tracker_remove"
            )
            if st.button("❌ Remove Selected", key="btn_remove_companies", type="secondary"):
                if remove_names:
                    tracked = [c for c in tracked if c["name"] not in remove_names]
                    with open(tracked_path, "w") as f:
                        json.dump(tracked, f, indent=2)
                    st.success(f"Removed {len(remove_names)} companies")
                    st.rerun()

        st.markdown("---")

        # ── How it works ──
        with st.expander("ℹ️ How does this work?"):
            st.markdown("""
**Career page scraping** fetches jobs directly from company ATS (Applicant Tracking System) APIs:

| Platform | Example Companies | API |
|---|---|---|
| 🌱 Greenhouse | Stripe, Airbnb, Cloudflare | `boards-api.greenhouse.io` |
| 🔧 Lever | Spotify, Twitch, Coinbase | `api.lever.co` |
| 🟣 Ashby | Ramp, OpenAI, Anthropic | `api.ashbyhq.com` |
| 💼 Workday | Mastercard, Capital One | `cxs/tenant/site/jobs` |

**How to find a company's slug:**
1. Go to the company's careers page
2. Look at the URL — e.g. `boards.greenhouse.io/stripe` → slug is `stripe`
3. Or check `jobs.lever.co/spotify` → slug is `spotify`
4. Or `jobs.ashbyhq.com/ramp` → slug is `ramp`
5. For Workday, e.g. `mastercard.wd1.../CorporateCareers` → slug is `mastercard/CorporateCareers`

**Tech Stack** data is extracted from job descriptions automatically. Filter by technology to find companies using specific tools.
""")

    # ─── Footer ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #718096; font-size: 0.85rem;'>"
        "🔍 Job Finding Agent — Federal · State · Corporate · Remote across 9 sectors with Auto-Apply"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
