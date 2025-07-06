import os
import openai
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
    # NOUVELLE PARTIE : APPEL À L'API OPENAI
    # #############################################################
    appreciation_ia = ""
    try:
        # La librairie OpenAI lit automatiquement la variable d'environnement OPENAI_API_KEY
        
        # 1. On construit le "prompt" (l'instruction pour l'IA)
        liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
        
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

        # 2. On appelle l'API
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": prompt_systeme},
                {"role": "user", "content": prompt_utilisateur}
            ],
            temperature=0.7 # Un peu de créativité mais pas trop
        )
        
        # 3. On récupère la réponse
        appreciation_ia = response.choices[0].message.content

    except Exception as e:
        # Si l'appel à l'IA échoue, on met un message d'erreur
        appreciation_ia = f"Erreur lors de la génération par IA : {e}"


    # On passe les données ET la nouvelle appréciation au template
    return render_template('resultat.html', donnees=donnees_structurees, appreciation_ia=appreciation_ia)

    # 6. Afficher les données structurées
    return render_template('resultat.html', donnees=donnees_structurees)

# (Le reste du fichier, comme 'if __name__ == "__main__"', ne change pas)
if __name__ == '__main__':
    app.run(debug=True)