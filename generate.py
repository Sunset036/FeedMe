import os
import json
import feedparser
import requests
from datetime import datetime, timedelta
import re

# --- CONFIGURATION ---
OPENAI_API_KEY = os.environ.get("LLM_API_KEY")
SOURCES = [
    "https://www.theguardian.com/uk/business/rss",
    "https://www.theguardian.com/world/rss",
    "https://www.theguardian.com/environment/rss",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://apnews.com/hub/ap-top-news?format=rss",
    "https://apnews.com/hub/business?format=rss",
    "https://www.france24.com/en/rss"
]

# --- RÉCUPÉRATION DES ARTICLES ---
def fetch_articles():
    articles = []
    for url in SOURCES:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:  # On prend les 5 plus récents de chaque source
            pub_date = datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') else datetime.now()
            # On garde les articles du dernier mois
            if datetime.now() - pub_date < timedelta(days=30):
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "source": feed.feed.title,
                    "summary": entry.get('summary', '')[:500], # Résumé brut du RSS
                    "published": pub_date.strftime("%Y-%m-%d")
                })
    return articles

# --- APPEL À L'IA ---
def curate_and_generate_questions(articles):
    if not articles:
        return {"articles": []}
        
    prompt = f"""
    Tu es un rédacteur en chef expert en économie, politique, écologie et tech.
    Voici une liste d'articles récents : {json.dumps(articles)}
    
    Ta mission :
    1. Sélectionne les 2 à 5 articles LES PLUS PERTINENTS pour enrichir la culture générale d'un lecteur francophone.
    2. Priorise l'économie, mais n'hésite pas à inclure de la politique, de l'écologie ou de la tech.
    3. Si tu as moins de 2 articles pertinents sur la semaine écoulée, élargis ta recherche aux articles du mois.
    4. Pour chaque article sélectionné, génère 4 questions ouvertes et pertinentes pour pousser le lecteur à réfléchir sur les causes, les conséquences et les enjeux.
    
    Réponds UNIQUEMENT au format JSON suivant (pas de texte avant ou après) :
    {{
      "articles": [
        {{
          "title": "Titre de l'article",
          "link": "Lien",
          "source": "Source",
          "why_selected": "Pourquoi cet article est important en 1 phrase.",
          "questions": ["Question 1", "Question 2", "Question 3", "Question 4"]
        }}
      ]
    }}
    """
    
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
    response.raise_for_status()
    
    content = response.json()['choices'][0]['message']['content']
    # Nettoyage du JSON au cas où l'IA ajoute des balises markdown
    content = re.sub(r'```json', '', content)
    content = re.sub(r'```', '', content)
    return json.loads(content)

# --- GÉNÉRATION DU SITE HTML ---
def generate_html(data):
    html = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ma Veille Hebdomadaire</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #0d1117; color: #c9d1d9; line-height: 1.6; padding: 20px; max-width: 800px; margin: 0 auto; }
            h1 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }
            .article { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 20px; }
            .article h2 { margin-top: 0; color: #58a6ff; }
            .article a { color: #58a6ff; text-decoration: none; }
            .article a:hover { text-decoration: underline; }
            .source { font-size: 0.9em; color: #8b949e; margin-bottom: 10px; }
            .why { font-style: italic; color: #8b949e; margin-bottom: 15px; }
            .questions { background-color: #0d1117; padding: 15px; border-radius: 6px; margin-top: 15px; }
            .questions h3 { margin-top: 0; color: #c9d1d9; font-size: 1.1em; }
            .question { margin-bottom: 15px; }
            .question label { display: block; font-weight: bold; margin-bottom: 5px; }
            .question textarea { width: 100%; min-height: 60px; background-color: #161b22; border: 1px solid #30363d; color: #c9d1d9; border-radius: 4px; padding: 10px; font-family: inherit; resize: vertical; }
            .footer { text-align: center; margin-top: 40px; font-size: 0.8em; color: #8b949e; }
        </style>
    </head>
    <body>
        <h1>📰 Ma Veille Hebdomadaire</h1>
    """
    
    if not data.get("articles"):
        html += "<p>Aucun article pertinent trouvé cette semaine. Reviens la semaine prochaine !</p>"
    else:
        for article in data["articles"]:
            html += f"""
            <div class="article">
                <h2><a href="{article['link']}" target="_blank">{article['title']}</a></h2>
                <div class="source">Source : {article['source']}</div>
                <div class="why">💡 {article['why_selected']}</div>
                <div class="questions">
                    <h3>🧠 Questions pour réfléchir :</h3>
            """
            for i, q in enumerate(article['questions']):
                html += f"""
                    <div class="question">
                        <label>{q}</label>
                        <textarea placeholder="Écris ta réponse ici... (sauvegardé automatiquement)"></textarea>
                    </div>
                """
            html += "</div></div>"
            
    html += """
        <div class="footer">Généré automatiquement par ton robot de veille.</div>
        <script>
            // Sauvegarde automatique des réponses dans le navigateur
            document.querySelectorAll('textarea').forEach((textarea, index) => {
                const key = 'veille_answer_' + index;
                textarea.value = localStorage.getItem(key) || '';
                textarea.addEventListener('input', () => {
                    localStorage.setItem(key, textarea.value);
                });
            });
        </script>
    </body>
    </html>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    print("Récupération des articles...")
    articles = fetch_articles()
    print(f"{len(articles)} articles trouvés.")
    print("Sélection et génération des questions par l'IA...")
    data = curate_and_generate_questions(articles)
    print("Génération du site...")
    generate_html(data)
    print("Terminé !")
