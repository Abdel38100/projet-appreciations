import os
import pdfplumber
from flask import Flask, render_template, request
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from parser import analyser_texte_bulletin

# --- Initialisation et Configuration de l'Application ---
app = Flask(__name__)

# Crée un dossier 'uploads' pour stocker temporairement les PDF.
# Ce dossier est ignoré par Git grâce au fichier .gitignore.
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# --- Définition des Pages (Routes) ---

@app.route('/')
def accueil():
    """Affiche la page d'accueil avec le formulaire pour téléverser un fichier."""
    return render_template('accueil.html')


@app.route('/analyser', methods=['POST'])
def analyser_bulletin():
    """
    Point d'entrée principal qui gère l'analyse du bulletin.
    1. Reçoit le fichier PDF.
    2. L'enregistre temporairement.
    3. Appelle le parser pour extraire les données structurées.
    4. Appelle l'API de Mistral pour générer l'appréciation globale.
    5. Affiche la page de résultats.
    """
    # Étape 1 : Gérer la réception du fichier
    if 'bulletin_pdf' not in request.files:
        return "Erreur : Aucun fichier n'a été envoyé."
    
    fichier = request.files['bulletin_pdf']

    if fichier.filename == '':
        return "Erreur : Aucun fichier sélectionné."

    if not (fichier and fichier.filename.endswith('.pdf')):
        return "Erreur : Veuillez téléverser un fichier au format PDF."

    # Étape 2 : Sauvegarde temporaire et extraction du texte brut
    texte_extrait = ""
    chemin_fichier = os.path.join(app.config['UPLOAD_FOLDER'], fichier.filename)
    try:
        fichier.save(chemin_fichier)
        with pdfplumber.open(chemin_fichier) as pdf:
            premiere_page = pdf.pages[0]
            texte_extrait = premiere_page.extract_text() or ""
    except Exception as e:
        return f"Erreur lors de la lecture du fichier PDF : {e}"
    finally:
        # Nettoyage : on supprime le fichier temporaire après l'avoir lu
        if os.path.exists(chemin_fichier):
            os.remove(chemin_fichier)

    # Étape 3 : Parser le texte brut pour obtenir des données structurées
    donnees_structurees = analyser_texte_bulletin(texte_extrait)
    
    # Étape 4 : Générer l'appréciation globale avec l'IA Mistral
    appreciation_ia = ""
    try:
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("La clé MISTRAL_API_KEY n'est pas définie dans les variables d'environnement de Render.")

        client = MistralClient(api_key=api_key)
        
        # Construction du prompt (l'instruction pour l'IA)
        liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
        
        prompt_systeme = "Tu es un professeur principal qui rédige l'appréciation générale sur un bulletin scolaire. Ton style est synthétique, encourageant et va à l'essentiel."
        
        # PROMPT UTILISATEUR AMÉLIORÉ POUR PLUS DE SYNTHÈSE
        prompt_utilisateur = f"""
        Voici les données de l'élève {donnees_structurees['nom_eleve']} (moyenne générale: {donnees_structurees['moyenne_generale']}):
        {liste_appreciations}

        Instructions pour la rédaction :
        1.  **Synthétise** les tendances générales sans citer les noms des matières. Au lieu de dire "en histoire, il est sérieux", préfère "montre un grand sérieux dans les matières littéraires" ou "son sérieux est relevé par plusieurs professeurs".
        2.  **Identifie les qualités principales** de l'élève (ex: sérieux, travailleur, volontaire, bonne participation...).
        3.  **Identifie les axes de progrès principaux** (ex: l'implication en classe, la régularité du travail...).
        4.  Rédige un paragraphe de **deux à trois phrases maximum**.
        5.  Termine par une phrase d'encouragement concise.
        
        Rédige maintenant l'appréciation globale.
        """

        # Préparation des messages pour l'API (syntaxe pour la version 0.4.2 de la librairie)
        messages = [
            ChatMessage(role="system", content=prompt_systeme),
            ChatMessage(role="user", content=prompt_utilisateur)
        ]

        # Appel à l'API Mistral
        chat_response = client.chat(
            model="mistral-large-latest", # Modèle puissant, bon pour le français
            messages=messages,
            temperature=0.6 # Température baissée pour une réponse plus factuelle
        )
        
        appreciation_ia = chat_response.choices[0].message.content

    except Exception as e:
        appreciation_ia = f"Erreur lors de la génération par IA (Mistral) : {e}"

    # Étape 5 : Afficher la page de résultats avec toutes les données
    return render_template('resultat.html', donnees=donnees_structurees, appreciation_ia=appreciation_ia)


# Point d'entrée pour lancer l'application en local (pour le développement)
if __name__ == '__main__':
    app.run(debug=True)