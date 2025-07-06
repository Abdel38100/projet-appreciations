import os
from mistralai.client import MistralClient
import pdfplumber
from flask import Flask, render_template, request, redirect, url_for
from parser import analyser_texte_bulletin

# --- Initialisation et Configuration ---
app = Flask(__name__)

# Crée un dossier 'uploads' s'il n'existe pas, pour stocker temporairement les PDF
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# --- Définition des Pages (Routes) ---

@app.route('/')
def accueil():
    """Page d'accueil avec le formulaire d'upload."""
    return render_template('accueil.html')


@app.route('/analyser', methods=['POST'])
def analyser_bulletin():
    """Reçoit le PDF, extrait le texte et l'affiche."""
    # 1. Vérifier si un fichier a été envoyé
    if 'bulletin_pdf' not in request.files:
        return "Erreur : Aucun fichier n'a été envoyé."
    
    fichier = request.files['bulletin_pdf']

    # 2. Vérifier si le nom du fichier est vide
    if fichier.filename == '':
        return "Erreur : Aucun fichier sélectionné."

    # 3. Si le fichier est valide et est un PDF
    if fichier and fichier.filename.endswith('.pdf'):
        # Sauvegarder le fichier temporairement sur le serveur
        chemin_fichier = os.path.join(app.config['UPLOAD_FOLDER'], fichier.filename)
        fichier.save(chemin_fichier)

    # 4. Extraire le texte avec pdfplumber
    texte_extrait = ""
    try:
        with pdfplumber.open(chemin_fichier) as pdf:
            premiere_page = pdf.pages[0]
            texte_extrait = premiere_page.extract_text() or ""
    except Exception as e:
        return f"Erreur lors de l'analyse du PDF : {e}"
    finally:
        if os.path.exists(chemin_fichier):
            os.remove(chemin_fichier)
    
    # 5. NOUVEAU : Appeler notre parser pour structurer les données
    donnees_structurees = analyser_texte_bulletin(texte_extrait)

    # #############################################################
    # NOUVELLE PARTIE : APPEL À L'API MISTRAL
    # #############################################################
    appreciation_ia = ""
    try:
        # 1. On récupère la clé API depuis les variables d'environnement
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("La clé MISTRAL_API_KEY n'est pas définie.")

        # 2. On initialise le client Mistral
        client = MistralClient(api_key=api_key)
        
        # 3. On construit le "prompt" (on peut garder le même pour l'instant)
        liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
        
        # On peut séparer le rôle système du message utilisateur pour plus de clarté
        prompt_systeme = "Tu es un professeur principal expérimenté, bienveillant mais juste. Tu dois rédiger une appréciation générale pour un bulletin scolaire."
        prompt_utilisateur = f"""
        Rédige une appréciation générale pour l'élève {donnees_structurees['nom_eleve']}.
        Sa moyenne générale est de {donnees_structurees['moyenne_generale']}.
        
        Voici le détail des appréciations de ses professeurs :
        {liste_appreciations}
        
        Rédige une synthèse de 3 à 4 phrases qui :
        1. Donne une vue d'ensemble du trimestre (ex: satisfaisant, correct, contrasté...).
        2. Met en avant les points positifs récurrents (sérieux, participation, efforts...).
        3. Mentionne avec bienveillance les points à améliorer s'il y en a.
        4. Se termine par une phrase d'encouragement.
        Ne fais pas de liste, écris un paragraphe fluide et cohérent.
        """

        # 4. On prépare les messages et on appelle l'API
        messages = [
            {"role": "system", "content": prompt_systeme},
            {"role": "user", "content": prompt_utilisateur}
        ]

        # On utilise un des modèles ouverts et performants de Mistral
        chat_response = client.chat(
            model="mistral-large-latest", # ou "mistral-small-latest" pour une option moins chère et très rapide
            messages=messages,
            temperature=0.7
        )
        
        # 5. On récupère la réponse
        appreciation_ia = chat_response.choices[0].message.content

    except Exception as e:
        appreciation_ia = f"Erreur lors de la génération par IA (Mistral) : {e}"

    # On passe les données ET la nouvelle appréciation au template (cette partie ne change pas)
    return render_template('resultat.html', donnees=donnees_structurees, appreciation_ia=appreciation_ia)

    # 6. Afficher les données structurées
    return render_template('resultat.html', donnees=donnees_structurees)

# (Le reste du fichier, comme 'if __name__ == "__main__"', ne change pas)
if __name__ == '__main__':
    app.run(debug=True)