import os
import pdfplumber
from flask import Flask, render_template, request, redirect, url_for

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
                # On prend uniquement la première page pour ce test
                premiere_page = pdf.pages[0]
                texte_extrait = premiere_page.extract_text()
        except Exception as e:
            return f"Erreur lors de l'analyse du PDF : {e}"
        finally:
            # Nettoyer en supprimant le fichier temporaire
            if os.path.exists(chemin_fichier):
                os.remove(chemin_fichier)
        
        # 5. Afficher le texte extrait
        return render_template('resultat.html', texte=texte_extrait)
    else:
        return "Erreur : Veuillez téléverser un fichier au format PDF."

# (Le reste du fichier, comme 'if __name__ == "__main__"', ne change pas)
if __name__ == '__main__':
    app.run(debug=True)