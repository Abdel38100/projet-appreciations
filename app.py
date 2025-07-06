import os
import pdfplumber
from flask import Flask, render_template, request
from flask_misaka import Misaka # <-- NOUVEL IMPORT
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from parser import analyser_texte_bulletin

# --- Initialisation et Configuration de l'Application ---
app = Flask(__name__)
Misaka(app) # <-- NOUVELLE INITIALISATION

# Crée un dossier 'uploads' pour stocker temporairement les PDF.
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
    """Point d'entrée principal qui gère l'analyse du bulletin."""
    # Gestion de l'upload
    if 'bulletin_pdf' not in request.files: return "Erreur : Aucun fichier n'a été envoyé."
    fichier = request.files['bulletin_pdf']
    if fichier.filename == '': return "Erreur : Aucun fichier sélectionné."
    if not (fichier and fichier.filename.endswith('.pdf')): return "Erreur : Veuillez téléverser un fichier au format PDF."

    # Extraction du texte
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
        if os.path.exists(chemin_fichier):
            os.remove(chemin_fichier)

    # Parsing des données
    donnees_structurees = analyser_texte_bulletin(texte_extrait)
    
    # Génération de l'appréciation par IA
    appreciation_principale = ""
    justifications = ""
    try:
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("La clé MISTRAL_API_KEY n'est pas définie.")

        client = MistralClient(api_key=api_key)
        
        liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
        
        prompt_systeme = "Tu es un professeur principal qui rédige l'appréciation générale. Ton style est synthétique, analytique et tu justifies tes conclusions."
        
        prompt_utilisateur = f"""
        Voici les données de l'élève {donnees_structurees['nom_eleve']}.
        Données brutes :
        {liste_appreciations}

        Ta réponse doit être en DEUX parties distinctes, séparées par la ligne "--- JUSTIFICATIONS ---".

        **Partie 1 : Appréciation Globale**
        Rédige un paragraphe de 2 à 3 phrases pour le bulletin. Ce texte doit être synthétique, fluide et ne doit PAS mentionner la moyenne générale. Il doit identifier les tendances de fond (qualités, points d'amélioration) sans citer de matières spécifiques.

        **Partie 2 : Justifications**
        Sous le séparateur, justifie chaque idée clé de ta synthèse. Pour chaque point, cite les preuves exactes des commentaires des professeurs. Utilise le format suivant :
        - **Idée synthétisée:** [Ex: L'élève fait preuve de sérieux.]
        - **Preuves:**
        - **[Nom de la matière]:** "[Citation exacte du commentaire]"
        - **[Autre matière]:** "[Autre citation]"
        
        - **Idée synthétisée:** [Ex: Des efforts sont à poursuivre sur l'implication.]
        - **Preuves:**
        - **[Nom de la matière]:** "[Citation exacte du commentaire]"

        Rédige maintenant ta réponse complète.
        """

        messages = [
            ChatMessage(role="system", content=prompt_systeme),
            ChatMessage(role="user", content=prompt_utilisateur)
        ]

        chat_response = client.chat(
            model="mistral-large-latest",
            messages=messages,
            temperature=0.5
        )
        
        reponse_complete_ia = chat_response.choices[0].message.content

        separateur = "--- JUSTIFICATIONS ---"
        if separateur in reponse_complete_ia:
            parties = reponse_complete_ia.split(separateur, 1)
            appreciation_principale = parties[0].strip()
            justifications = parties[1].strip()
        else:
            appreciation_principale = reponse_complete_ia
            justifications = "L'IA n'a pas fourni de justifications séparées."

    except Exception as e:
        appreciation_principale = f"Erreur lors de la génération par IA (Mistral) : {e}"
        justifications = "Aucune justification disponible en raison de l'erreur."

    return render_template(
        'resultat.html', 
        donnees=donnees_structurees, 
        appreciation_principale=appreciation_principale, 
        justifications=justifications
    )


if __name__ == '__main__':
    app.run(debug=True)