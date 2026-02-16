from __future__ import annotations


def get_app_css() -> str:
    return """
    <style>
    :root {
        --sf-navy: #0B1C2C;
        --sf-navy-2: #0F253A;
        --sf-light-bg: #EEF2F5;
        --sf-panel-bg: #F7F9FB;
        --sf-card-bg: #FFFFFF;
        --sf-text: #101820;
        --sf-muted: #627182;
        --sf-accent: #2EA3FF;
        --sf-border: #D8E0E7;
        --sf-shadow: 0 8px 20px rgba(10, 23, 37, 0.06);
    }

    .stApp {
        background: linear-gradient(180deg, #F2F5F8 0%, #EEF2F5 240px, #EEF2F5 100%);
        color: var(--sf-text);
    }

    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    [data-testid="stAppViewContainer"] > .main > div:first-child,
    #MainMenu,
    footer {
        visibility: hidden;
        height: 0;
    }

    .block-container {
        max-width: 1180px;
        padding-top: 1.1rem;
        padding-bottom: 1.4rem;
    }

    section[data-testid="stSidebar"] > div {
        background: linear-gradient(180deg, #0D2133 0%, #122B42 100%);
        border-right: 1px solid rgba(255,255,255,0.08);
    }

    section[data-testid="stSidebar"] * {
        color: #DFE8F0;
    }

    section[data-testid="stSidebar"] .stMarkdown p {
        color: #AAB9C8;
    }

    section[data-testid="stSidebar"] [data-baseweb="select"] > div {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.12);
        min-height: 36px;
    }

    section[data-testid="stSidebar"] label {
        color: #DCE7F2 !important;
        font-weight: 600;
        letter-spacing: 0.01em;
    }

    section[data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.12);
        margin: 0.55rem 0;
    }

    .sf-shell {
        display: block;
        width: 100%;
    }

    .sf-header {
        background: linear-gradient(90deg, var(--sf-navy), var(--sf-navy-2));
        color: white;
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 10px;
        border: 1px solid #1A3247;
        box-shadow: var(--sf-shadow);
    }

    .sf-header-top {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 12px;
    }

    .sf-badge-row {
        display: flex;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
        justify-content: flex-end;
    }

    .sf-brand {
        line-height: 1.1;
    }

    .sf-wordmark {
        font-size: 1.16rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        margin-bottom: 1px;
    }

    .sf-subtitle {
        color: #96A7B7;
        font-size: 0.76rem;
        margin-top: 2px;
    }

    .sf-tagline {
        color: #F4FAFF;
        font-size: 1.18rem;
        font-weight: 800;
        margin-top: 5px;
        letter-spacing: 0.01em;
    }

    .sf-tagline-secondary {
        color: #BFD1E1;
        font-size: 0.78rem;
        font-weight: 600;
        margin-top: 4px;
    }

    .sf-badge {
        background: rgba(46, 163, 255, 0.12);
        color: #B8E1FF;
        border: 1px solid rgba(46, 163, 255, 0.35);
        border-radius: 999px;
        padding: 3px 9px;
        font-size: 0.74rem;
        font-weight: 600;
        white-space: nowrap;
    }

    .sf-demo-mode-pill {
        margin-top: 2px;
        margin-bottom: 8px;
        padding: 6px 10px;
        border-radius: 10px;
        border: 1px solid rgba(184, 225, 255, 0.35);
        background: rgba(46, 163, 255, 0.14);
        color: #CBE9FF;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.01em;
        text-align: center;
    }

    .sf-trust-row {
        margin-top: 8px;
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        color: #AFC0CF;
        font-size: 0.74rem;
    }

    .sf-context {
        margin-top: 8px;
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
    }

    .sf-chip {
        background: rgba(255, 255, 255, 0.10);
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 999px;
        padding: 2px 9px;
        font-size: 0.76rem;
        line-height: 1.45;
    }

    .sf-card {
        background: var(--sf-card-bg);
        border: 1px solid var(--sf-border);
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 12px;
        box-shadow: var(--sf-shadow);
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
    }

    .sf-card:hover {
        transform: translateY(-1px);
        border-color: #C5D3E0;
        box-shadow: 0 10px 24px rgba(10, 23, 37, 0.10);
    }

    .sf-section {
        margin-top: 4px;
        margin-bottom: 10px;
    }

    .sf-card-title {
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 4px;
        color: #162838;
    }

    .sf-card-subtitle {
        font-size: 0.81rem;
        color: var(--sf-muted);
        margin-bottom: 10px;
    }

    h1, h2, h3 {
        letter-spacing: 0.01em;
    }

    .stCaption, [data-testid="stCaptionContainer"] {
        color: #6B7A89;
        font-size: 0.78rem;
    }

    .sf-kpi-card {
        background: var(--sf-card-bg);
        border: 1px solid var(--sf-border);
        border-radius: 12px;
        padding: 12px 13px;
        min-height: 108px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: var(--sf-shadow);
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
    }

    .sf-kpi-card:hover {
        transform: translateY(-2px);
        border-color: #BFD0DE;
        box-shadow: 0 12px 28px rgba(10, 23, 37, 0.10);
    }

    .sf-kpi-title {
        color: var(--sf-muted);
        font-size: 0.75rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }

    .sf-kpi-value {
        color: var(--sf-text);
        font-size: 1.58rem;
        font-weight: 700;
        line-height: 1.1;
    }

    .sf-kpi-delta {
        color: #7C8A98;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .sf-kpi-helper {
        color: #7A8795;
        font-size: 0.72rem;
        line-height: 1.35;
        margin-top: 4px;
    }

    .sf-desktop-only {
        color: var(--sf-muted);
        font-size: 0.84rem;
        margin-top: 2px;
    }

    .sf-standout {
        background: linear-gradient(180deg, #FFFFFF 0%, #F9FCFF 100%);
        border: 1px solid #D0DCE8;
    }

    .sf-summary-pill {
        border: 1px solid #D4E0EC;
        border-radius: 10px;
        padding: 8px 9px;
        background: #FFFFFF;
        min-height: 62px;
    }

    .sf-summary-label {
        color: #5A6C7E;
        font-size: 0.70rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 3px;
    }

    .sf-summary-value {
        color: #12263A;
        font-size: 0.90rem;
        font-weight: 700;
    }

    .sf-plan-card {
        border-left: 4px solid #2EA3FF;
    }

    .sf-disclaimer {
        color: #7C8A98;
        font-size: 0.74rem;
        margin-top: 8px;
        margin-bottom: 4px;
    }

    .sf-footer {
        margin-top: 2px;
        padding: 10px 12px;
        border: 1px solid #D4DEE8;
        border-radius: 10px;
        background: #F8FBFE;
        color: #5E6D7D;
        font-size: 0.82rem;
        text-align: center;
    }

    [data-testid="stTabs"] {
        margin-top: 2px;
    }

    [data-testid="stTabs"] button[role="tab"] {
        border-radius: 9px 9px 0 0;
        padding: 0.4rem 0.8rem;
        font-weight: 600;
        font-size: 0.88rem;
        transition: background 0.18s ease, color 0.18s ease;
    }

    [data-testid="stTabs"] button[role="tab"]:hover {
        color: #0F253A;
        background: #EAF1F7;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid var(--sf-border);
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 3px 12px rgba(17, 31, 46, 0.04);
    }

    [data-testid="stDataFrame"] [role="row"]:hover {
        background: #F8FBFE !important;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.25rem;
    }

    [data-testid="stMetricLabel"] p {
        font-weight: 700;
        color: #405466;
    }

    .stButton > button {
        border-radius: 8px;
        border: 1px solid #C7D2DD;
        font-weight: 600;
        transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
    }

    .stButton > button:hover {
        background: #F4F8FC;
        border-color: #AFC2D3;
        transform: translateY(-1px);
    }

    @media (max-width: 1200px) {
        .block-container {
            max-width: 980px;
        }

        .sf-header {
            padding: 11px 12px;
        }

        .sf-wordmark {
            font-size: 1.10rem;
        }

        .sf-tagline {
            font-size: 1.08rem;
        }

        .sf-chip {
            font-size: 0.72rem;
        }
    }

    @media (max-width: 900px) {
        .block-container {
            padding-top: 0.7rem;
            padding-bottom: 1rem;
        }

        .sf-header-top {
            align-items: flex-start;
            flex-direction: column;
        }

        .sf-badge-row {
            justify-content: flex-start;
        }

        .sf-badge {
            margin-top: 4px;
        }

        [data-testid="stMetricValue"] {
            font-size: 1.1rem;
        }

        .sf-summary-pill {
            min-height: 56px;
        }
    }

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.9rem;
            padding-right: 0.9rem;
        }

        .sf-card {
            padding: 10px 11px;
        }
    }
    </style>
    """
