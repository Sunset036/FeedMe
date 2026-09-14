import os
import json
import feedparser
import requests
from datetime import datetime, timedelta
import re
import hashlib

OPENAI_API_KEY = os.environ.get("LLM_API_KEY")
GITHUB_USER = "Sunset036"
GITHUB_REPO = "FeedMe"

SOURCES = [
    {"url": "https://www.theguardian.com/uk/business/rss", "cat": "economie", "name": "Guardian Business"},
    {"url": "https://www.theguardian.com/world/rss", "cat": "politique", "name": "Guardian World"},
    {"url": "https://www.theguardian.com/environment/rss", "cat": "ecologie", "name": "Guardian Environment"},
    {"url": "https://www.theguardian.com/uk/technology/rss", "cat": "tech", "name": "Guardian Tech"},
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "cat": "politique", "name": "BBC World"},
    {"url": "https://feeds.bbci.co.uk/news/business/rss.xml", "cat": "economie", "name": "BBC Business"},
    {"url": "https://apnews.com/hub/ap-top-news?format=rss", "cat": "politique", "name": "AP Top News"},
    {"url": "https://apnews.com/hub/business?format=rss", "cat": "economie", "name": "AP Business"},
    {"url": "https://www.france24.com/en/rss", "cat": "politique", "name": "France24"},
]

CATEGORY_COLORS = {"economie": "#3b82f6", "politique": "#a855f7", "ecologie": "#22c55e", "tech": "#f59e0b"}
CATEGORY_LABELS = {"economie": "Économie", "politique": "Politique", "ecologie": "Écologie", "tech": "Tech"}


def fetch_articles():
    articles = []
    now = datetime.now()
    for source in SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:8]:
                pub_date = datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') else now
                if now - pub_date < timedelta(days=30):
                    articles.append({
                        "title": entry.title,
                        "link": entry.link,
                        "source": source["name"],
                        "category": source["cat"],
                        "summary": re.sub(r'<[^>]+>', '', entry.get('summary', ''))[:400],
                        "published": pub_date.strftime("%Y-%m-%d")
                    })
        except Exception as e:
            print(f"Erreur avec {source['name']}: {e}")
    return articles


def call_openai(prompt):
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}
    r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
    r.raise_for_status()
    content = r.json()['choices'][0]['message']['content']
    content = re.sub(r'```json', '', content)
    content = re.sub(r'```', '', content)
    return json.loads(content.strip())


def curate_and_generate_questions(articles):
    if not articles:
        return {"articles": []}
    prompt = f"""Tu es un rédacteur en chef expert en économie, politique, écologie et tech.
Voici une liste d'articles récents : {json.dumps(articles, ensure_ascii=False)}

Ta mission :
1. Sélectionne les 2 à 5 articles LES PLUS PERTINENTS pour enrichir la culture générale d'un lecteur francophone.
2. Priorise l'économie, mais n'hésite pas à inclure de la politique, de l'écologie ou de la tech.
3. Si tu as moins de 2 articles pertinents sur la semaine, élargis au mois.
4. Pour chaque article, génère 4 questions ouvertes pour pousser à réfléchir (causes, conséquences, enjeux).

Réponds UNIQUEMENT au format JSON :
{{
  "articles": [
    {{
      "title": "Titre exact",
      "link": "Lien exact",
      "source": "Source",
      "category": "economie|politique|ecologie|tech",
      "why_selected": "Pourquoi cet article est important en 1 phrase.",
      "questions": ["Q1", "Q2", "Q3", "Q4"]
    }}
  ]
}}
"""
    return call_openai(prompt)


def generate_monthly_synthesis(past_articles, month_label):
    if not past_articles:
        return None
    titles = [a['title'] for a in past_articles]
    prompt = f"""Tu es un analyste géopolitique et économique.
Voici les articles de veille du mois {month_label} : {json.dumps(titles, ensure_ascii=False)}

Dégage les 3 grandes dynamiques du mois et écris une synthèse de 150 mots maximum en français.

Réponds UNIQUEMENT en JSON :
{{
  "dynamics": ["Dynamique 1 en une phrase", "Dynamique 2", "Dynamique 3"],
  "synthesis": "Texte de synthèse de 150 mots."
}}
"""
    try:
        return call_openai(prompt)
    except Exception as e:
        print(f"Erreur synthèse: {e}")
        return None


def article_id(link):
    return hashlib.md5(link.encode()).hexdigest()[:12]


def week_label(dt):
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def month_label(dt):
    return dt.strftime("%Y-%m")


def estimate_reading_time(summary):
    words = len(summary.split())
    minutes = max(1, round(words / 200))
    return f"{minutes} min"


def save_week_data(articles, week_key):
    os.makedirs("data/weeks", exist_ok=True)
    for a in articles:
        a["id"] = article_id(a["link"])
        a["reading_time"] = estimate_reading_time(a.get("summary", ""))
    data = {"week": week_key, "generated_at": datetime.now().isoformat(), "articles": articles}
    with open(f"data/weeks/{week_key}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def load_past_weeks(current_week):
    weeks = []
    if os.path.exists("data/weeks"):
        for f in sorted(os.listdir("data/weeks"), reverse=True):
            if f.endswith(".json") and not f.startswith(current_week):
                with open(f"data/weeks/{f}", "r", encoding="utf-8") as fh:
                    weeks.append(json.load(fh))
    return weeks


def load_past_articles_for_synthesis(current_month):
    all_articles = []
    if os.path.exists("data/weeks"):
        for f in sorted(os.listdir("data/weeks")):
            if f.endswith(".json"):
                with open(f"data/weeks/{f}", "r", encoding="utf-8") as fh:
                    w = json.load(fh)
                    for a in w.get("articles", []):
                        if a.get("published", "").startswith(current_month):
                            all_articles.append(a)
    return all_articles


def save_synthesis(synthesis, month_key):
    os.makedirs("data/synthesis", exist_ok=True)
    path = f"data/synthesis/{month_key}.json"
    data = {"month": month_key, "generated_at": datetime.now().isoformat(), **synthesis}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_all_syntheses():
    syntheses = []
    if os.path.exists("data/synthesis"):
        for f in sorted(os.listdir("data/synthesis"), reverse=True):
            if f.endswith(".json"):
                with open(f"data/synthesis/{f}", "r", encoding="utf-8") as fh:
                    syntheses.append(json.load(fh))
    return syntheses


def render_article(article, prefix=""):
    aid = prefix + article["id"]
    cat = article.get("category", "politique")
    color = CATEGORY_COLORS.get(cat, "#8b949e")
    label = CATEGORY_LABELS.get(cat, cat)
    questions_html = ""
    for i, q in enumerate(article["questions"]):
        qkey = f"{aid}_q{i}"
        questions_html += f"""
        <div class="question">
            <label>{q}</label>
            <textarea data-key="{qkey}" placeholder="Écris ta réponse ici..."></textarea>
        </div>"""
    return f"""
    <article class="article" data-id="{aid}" data-title="{article['title'].lower()}" data-source="{article['source'].lower()}">
        <div class="article-header">
            <span class="category" style="background-color:{color}20; color:{color}; border:1px solid {color}40;">{label}</span>
            <span class="reading-time">⏱ {article.get('reading_time', '1 min')}</span>
            <button class="read-btn" onclick="toggleRead('{aid}')">Marquer comme lu</button>
        </div>
        <h2><a href="{article['link']}" target="_blank" rel="noopener">{article['title']}</a></h2>
        <div class="source">{article['source']} · {article.get('published', '')}</div>
        <div class="why">💡 {article['why_selected']}</div>
        <div class="questions"><h3>🧠 Questions pour réfléchir :</h3>{questions_html}</div>
    </article>
    """


def build_html(current_data, past_weeks, syntheses):
    articles_html = "".join(render_article(a) for a in current_data.get("articles", []))
    if not articles_html:
        articles_html = "<p class='empty'>Aucun article pertinent cette semaine.</p>"

    archive_html = ""
    for w in past_weeks:
        archive_html += f"<h2 class='archive-week'>Semaine {w['week']}</h2>"
        for a in w.get("articles", []):
            archive_html += render_article(a, prefix="arch_")

    synthesis_html = ""
    for s in syntheses:
        dynamics = "".join(f"<li>{d}</li>" for d in s.get("dynamics", []))
        synthesis_html += f"""
        <div class="synthesis">
            <h2>Synthèse de {s['month']}</h2>
            <ul class="dynamics">{dynamics}</ul>
            <p>{s.get('synthesis', '')}</p>
        </div>"""

    css = """
    :root { --bg:#0a0e14; --bg-card:#131820; --border:#1f2937; --text:#e6edf3;
            --text-muted:#8b949e; --accent:#58a6ff; --success:#22c55e; }
    body.light { --bg:#ffffff; --bg-card:#f6f8fa; --border:#d0d7de; --text:#1f2328;
                 --text-muted:#656d76; --accent:#0969da; }
    * { box-sizing:border-box; }
    body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
           background:var(--bg); color:var(--text); line-height:1.7; margin:0; padding:0;
           transition: background 0.2s, color 0.2s; }
    .container { max-width:780px; margin:0 auto; padding:24px 20px 80px; }
    header { border-bottom:1px solid var(--border); padding-bottom:20px; margin-bottom:24px;
             display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px; }
    h1 { font-size:1.6em; margin:0 0 6px; font-weight:700; letter-spacing:-0.02em; }
    .subtitle { color:var(--text-muted); font-size:0.92em; }
    .theme-toggle { background:transparent; border:1px solid var(--border); color:var(--text);
                    padding:6px 12px; border-radius:6px; cursor:pointer; font-size:0.9em; }
    .sync-bar { display:flex; align-items:center; justify-content:space-between;
                background:var(--bg-card); border:1px solid var(--border); border-radius:8px;
                padding:10px 16px; margin-bottom:20px; font-size:0.88em; flex-wrap:wrap; gap:8px; }
    .sync-status { color:var(--text-muted); }
    .sync-status.ok { color:var(--success); }
    .sync-status.error { color:#ef4444; }
    .sync-bar button { background:transparent; border:1px solid var(--border); color:var(--text);
                       padding:6px 12px; border-radius:6px; cursor:pointer; font-size:0.85em; margin-left:4px; }
    .sync-bar button:hover { border-color:var(--accent); color:var(--accent); }
    .tabs { display:flex; gap:4px; margin-bottom:20px; border-bottom:1px solid var(--border); flex-wrap:wrap; }
    .tab { padding:10px 16px; background:transparent; border:none; color:var(--text-muted);
           cursor:pointer; font-size:0.95em; border-bottom:2px solid transparent; }
    .tab.active { color:var(--accent); border-bottom-color:var(--accent); }
    .tab-content { display:none; }
    .tab-content.active { display:block; }
    .search-box { width:100%; padding:10px 14px; background:var(--bg-card); border:1px solid var(--border);
                  color:var(--text); border-radius:8px; margin-bottom:16px; font-size:0.95em; font-family:inherit; }
    .search-box:focus { outline:none; border-color:var(--accent); }
    .article { background:var(--bg-card); border:1px solid var(--border); border-radius:12px;
               padding:22px; margin-bottom:18px; transition:opacity 0.2s, border-color 0.2s; }
    .article:hover { border-color:var(--accent); }
    .article.read { opacity:0.5; }
    .article-header { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:10px; }
    .category { padding:3px 10px; border-radius:20px; font-size:0.78em; font-weight:600; }
    .reading-time { color:var(--text-muted); font-size:0.82em; }
    .read-btn { margin-left:auto; background:transparent; border:1px solid var(--border);
                color:var(--text-muted); padding:4px 10px; border-radius:6px;
                cursor:pointer; font-size:0.78em; }
    .read-btn:hover { color:var(--accent); border-color:var(--accent); }
    .article h2 { font-size:1.2em; margin:6px 0; line-height:1.4; }
    .article h2 a { color:var(--text); text-decoration:none; }
    .article h2 a:hover { color:var(--accent); }
    .source { color:var(--text-muted); font-size:0.83em; margin-bottom:12px; }
    .why { color:var(--text-muted); font-style:italic; margin:12px 0 18px; padding:10px 14px;
           background:rgba(88,166,255,0.05); border-left:3px solid var(--accent);
           border-radius:4px; font-size:0.94em; }
    .questions h3 { font-size:0.98em; margin:0 0 14px; }
    .question { margin-bottom:16px; }
    .question label { display:block; font-weight:500; margin-bottom:8px; font-size:0.93em; }
    .question textarea { width:100%; min-height:70px; background:var(--bg); border:1px solid var(--border);
                         color:var(--text); border-radius:8px; padding:12px; font-family:inherit;
                         font-size:0.93em; resize:vertical; line-height:1.5; }
    .question textarea:focus { outline:none; border-color:var(--accent); }
    .empty { color:var(--text-muted); text-align:center; padding:40px 20px; }
    .archive-week { color:var(--accent); margin-top:32px; font-size:1.15em;
                    border-bottom:1px solid var(--border); padding-bottom:8px; }
    .synthesis { background:linear-gradient(135deg, rgba(88,166,255,0.08), rgba(168,85,247,0.08));
                 border:1px solid var(--border); border-radius:12px; padding:22px; margin-bottom:20px; }
    .synthesis h2 { margin-top:0; color:var(--accent); font-size:1.15em; }
    .dynamics { padding-left:20px; margin:12px 0; }
    .dynamics li { margin-bottom:6px; }
    .modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:100;
             align-items:center; justify-content:center; padding:20px; }
    .modal.open { display:flex; }
    .modal-content { background:var(--bg-card); border:1px solid var(--border); border-radius:12px;
                     padding:24px; max-width:500px; width:100%; }
    .modal-content h2 { margin-top:0; font-size:1.15em; }
    .modal-content p { color:var(--text-muted); font-size:0.88em; line-height:1.5; }
    .modal-content input { width:100%; padding:10px; background:var(--bg); border:1px solid var(--border);
                           color:var(--text); border-radius:6px; font-family:inherit; margin:12px 0; }
    .modal-content button { padding:10px 18px; border-radius:6px; border:none; cursor:pointer;
                            font-size:0.92em; margin-right:8px; }
    .btn-primary { background:var(--accent); color:white; }
    .btn-secondary { background:transparent; color:var(--text); border:1px solid var(--border) !important; }
    footer { text-align:center; color:var(--text-muted); font-size:0.78em; margin-top:50px; }
    """

    js = f"""
    const GITHUB_USER = "{GITHUB_USER}";
    const GITHUB_REPO = "{GITHUB_REPO}";
    const NOTES_PATH = "data/notes.json";
    let notes = {{}};
    let readArticles = JSON.parse(localStorage.getItem('read_articles') || '[]');
    let saveTimeout = null;

    function showTab(name) {{
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        document.querySelector(`.tab[data-tab="${{name}}"]`).classList.add('active');
        document.getElementById(name).classList.add('active');
        localStorage.setItem('active_tab', name);
    }}

    function loadNotesFromLocal() {{
        const stored = localStorage.getItem('notes');
        if (stored) notes = JSON.parse(stored);
        document.querySelectorAll('textarea[data-key]').forEach(ta => {{ ta.value = notes[ta.dataset.key] || ''; }});
    }}

    async function syncFromGitHub() {{
        const token = localStorage.getItem('gh_token');
        if (!token) return;
        setSyncStatus('Chargement...', '');
        try {{
            const res = await fetch(`https://api.github.com/repos/${{GITHUB_USER}}/${{GITHUB_REPO}}/contents/${{NOTES_PATH}}`, {{
                headers: {{ 'Authorization': `token ${{token}}` }}
            }});
            if (res.status === 404) {{ notes = {{}}; setSyncStatus('Aucune note distante', ''); return; }}
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            const content = decodeURIComponent(escape(atob(data.content.replace(/\\n/g, ''))));
            const remote = JSON.parse(content);
            notes = {{ ...remote, ...notes }};
            localStorage.setItem('notes', JSON.stringify(notes));
            document.querySelectorAll('textarea[data-key]').forEach(ta => {{ ta.value = notes[ta.dataset.key] || ''; }});
            setSyncStatus('✓ Synchronisé', 'ok');
        }} catch (e) {{ setSyncStatus('Erreur sync : ' + e.message, 'error'); }}
    }}

    async function saveNotesToGitHub() {{
        const token = localStorage.getItem('gh_token');
        if (!token) {{ setSyncStatus('Token GitHub non configuré', 'error'); return; }}
        setSyncStatus('Sauvegarde...', '');
        try {{
            const getRes = await fetch(`https://api.github.com/repos/${{GITHUB_USER}}/${{GITHUB_REPO}}/contents/${{NOTES_PATH}}`, {{
                headers: {{ 'Authorization': `token ${{token}}` }}
            }});
            let sha = null;
            if (getRes.ok) {{ const d = await getRes.json(); sha = d.sha; }}
            const content = btoa(unescape(encodeURIComponent(JSON.stringify(notes, null, 2))));
            const body = {{ message: 'Update notes [skip ci]', content }};
            if (sha) body.sha = sha;
            const putRes = await fetch(`https://api.github.com/repos/${{GITHUB_USER}}/${{GITHUB_REPO}}/contents/${{NOTES_PATH}}`, {{
                method: 'PUT',
                headers: {{ 'Authorization': `token ${{token}}`, 'Content-Type': 'application/json' }},
                body: JSON.stringify(body)
            }});
            if (!putRes.ok) throw new Error('HTTP ' + putRes.status);
            setSyncStatus('✓ Sauvegardé', 'ok');
        }} catch (e) {{ setSyncStatus('Erreur sauvegarde : ' + e.message, 'error'); }}
    }}

    function setSyncStatus(msg, cls) {{
        const el = document.getElementById('sync-status');
        el.textContent = msg; el.className = 'sync-status ' + (cls || '');
    }}

    function toggleRead(id) {{
        const idx = readArticles.indexOf(id);
        if (idx >= 0) readArticles.splice(idx, 1); else readArticles.push(id);
        localStorage.setItem('read_articles', JSON.stringify(readArticles));
        applyReadState();
    }}
    function applyReadState() {{
        document.querySelectorAll('.article').forEach(art => {{
            const isRead = readArticles.includes(art.dataset.id);
            art.classList.toggle('read', isRead);
            const btn = art.querySelector('.read-btn');
            if (btn) btn.textContent = isRead ? '✓ Lu' : 'Marquer comme lu';
        }});
    }}

    function exportNotes() {{
        let md = '# Mes notes de veille\\n\\n';
        document.querySelectorAll('.article').forEach(art => {{
            const title = art.querySelector('h2 a').textContent;
            md += `## ${{title}}\\n\\n`;
            art.querySelectorAll('.question').forEach(q => {{
                const label = q.querySelector('label').textContent;
                const answer = q.querySelector('textarea').value || '_(vide)_';
                md += `**${{label}}**\\n\\n${{answer}}\\n\\n`;
            }});
        }});
        const blob = new Blob([md], {{ type: 'text/markdown' }});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = 'veille-notes.md'; a.click();
    }}

    function openTokenModal() {{
        document.getElementById('token-input').value = localStorage.getItem('gh_token') || '';
        document.getElementById('token-modal').classList.add('open');
    }}
    function closeTokenModal() {{ document.getElementById('token-modal').classList.remove('open'); }}
    function saveToken() {{
        const val = document.getElementById('token-input').value.trim();
        if (val) {{ localStorage.setItem('gh_token', val); closeTokenModal(); syncFromGitHub(); }}
    }}

    function toggleTheme() {{
        document.body.classList.toggle('light');
        localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
    }}

    function searchArchive() {{
        const q = document.getElementById('search-input').value.toLowerCase();
        document.querySelectorAll('#archive .article').forEach(art => {{
            const match = art.dataset.title.includes(q) || art.dataset.source.includes(q);
            art.style.display = match ? 'block' : 'none';
        }});
    }}

    document.addEventListener('DOMContentLoaded', () => {{
        if (localStorage.getItem('theme') === 'light') document.body.classList.add('light');
        const activeTab = localStorage.getItem('active_tab') || 'current';
        showTab(activeTab);
        loadNotesFromLocal();
        applyReadState();
        document.querySelectorAll('textarea[data-key]').forEach(ta => {{
            ta.addEventListener('input', () => {{
                notes[ta.dataset.key] = ta.value;
                localStorage.setItem('notes', JSON.stringify(notes));
                setSyncStatus('Non sauvegardé...', '');
                clearTimeout(saveTimeout);
                saveTimeout = setTimeout(saveNotesToGitHub, 2000);
            }});
        }});
        if (localStorage.getItem('gh_token')) syncFromGitHub();
        else setSyncStatus('Configure ton token GitHub pour synchroniser', '');
        // PWA
        if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(()=>{{}});
    }});
    """

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#0a0e14">
    <link rel="manifest" href="./manifest.json">
    <link rel="apple-touch-icon" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgcng9IjIwIiBmaWxsPSIjMGEwZTE0Ii8+PHRleHQgeD0iNTAiIHk9IjY1IiBmb250LXNpemU9IjUwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjNThhNmZmIj7wn5OwPC90ZXh0Pjwvc3ZnPg==">
    <title>Ma Veille</title>
    <style>{css}</style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>📰 Ma Veille</h1>
                <div class="subtitle">Semaine {current_data.get('week', '')} · {len(current_data.get('articles', []))} articles sélectionnés</div>
            </div>
            <button class="theme-toggle" onclick="toggleTheme()">🌓 Thème</button>
        </header>

        <div class="sync-bar">
            <span id="sync-status" class="sync-status">Initialisation...</span>
            <div>
                <button onclick="openTokenModal()">⚙️ Token</button>
                <button onclick="exportNotes()">📥 Exporter</button>
            </div>
        </div>

        <div class="tabs">
            <button class="tab active" data-tab="current" onclick="showTab('current')">Cette semaine</button>
            <button class="tab" data-tab="synthesis" onclick="showTab('synthesis')">Synthèses</button>
            <button class="tab" data-tab="archive" onclick="showTab('archive')">Archive</button>
        </div>

        <div id="current" class="tab-content active">{articles_html}</div>

        <div id="synthesis" class="tab-content">
            {synthesis_html if synthesis_html else "<p class='empty'>Les synthèses mensuelles apparaîtront ici à partir du 2e mois.</p>"}
        </div>

        <div id="archive" class="tab-content">
            <input type="text" id="search-input" class="search-box" placeholder="🔎 Rechercher dans l'archive..." oninput="searchArchive()">
            {archive_html if archive_html else "<p class='empty'>L'archive se remplira au fil des semaines.</p>"}
        </div>

        <footer>Généré automatiquement · Tes notes se synchronisent via GitHub</footer>
    </div>

    <div id="token-modal" class="modal">
        <div class="modal-content">
            <h2>Token GitHub</h2>
            <p>Pour synchroniser tes notes entre appareils, colle ton Personal Access Token GitHub (permission <code>repo</code>). Il reste uniquement dans ton navigateur.</p>
            <input type="password" id="token-input" placeholder="ghp_..." />
            <div style="text-align:right;">
                <button class="btn-secondary" onclick="closeTokenModal()">Annuler</button>
                <button class="btn-primary" onclick="saveToken()">Enregistrer</button>
            </div>
        </div>
    </div>

    <script>{js}</script>
</body>
</html>"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    # PWA files
    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump({
            "name": "Ma Veille", "short_name": "Veille",
            "start_url": "./", "display": "standalone",
            "background_color": "#0a0e14", "theme_color": "#0a0e14",
            "icons": [{"src": "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgcng9IjIwIiBmaWxsPSIjMGEwZTE0Ii8+PHRleHQgeD0iNTAiIHk9IjY1IiBmb250LXNpemU9IjUwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjNThhNmZmIj7wn5OwPC90ZXh0Pjwvc3ZnPg==", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]
        }, f, ensure_ascii=False, indent=2)
    with open("sw.js", "w", encoding="utf-8") as f:
        f.write("self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>self.clients.claim());self.addEventListener('fetch',e=>{});")


if __name__ == "__main__":
    now = datetime.now()
    current_week = week_label(now)
    print("Récupération des articles...")
    articles = fetch_articles()
    print(f"{len(articles)} articles trouvés.")
    print("Sélection IA...")
    data = curate_and_generate_questions(articles)
    print(f"{len(data.get('articles', []))} retenus.")
    week_data = save_week_data(data.get("articles", []), current_week)

    # Synthèse mensuelle : on la génère le premier lundi de chaque mois
    if now.day <= 7:
        prev_month_dt = (now.replace(day=1) - timedelta(days=1))
        prev_month = month_label(prev_month_dt)
        synth_path = f"data/synthesis/{prev_month}.json"
        if not os.path.exists(synth_path):
            print(f"Génération synthèse pour {prev_month}...")
            past_arts = load_past_articles_for_synthesis(prev_month)
            if past_arts:
                synth = generate_monthly_synthesis(past_arts, prev_month)
                if synth:
                    save_synthesis(synth, prev_month)

    print("Chargement archives...")
    past = load_past_weeks(current_week)
    syntheses = load_all_syntheses()
    print("Génération HTML...")
    build_html(week_data, past, syntheses)
    print("Terminé !")
