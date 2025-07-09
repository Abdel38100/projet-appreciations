import os
import re
import pdfplumber
import unicodedata
import io
from flask import Flask, render_template, request, flash, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_misaka import markdown as MisakaMarkdown
from groq import Groq
from parser import analyser_texte_bulletin

# --- INITIALISATION ET CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-tres-securisee')
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."

# --- GESTION DE L'UTILISATEUR ---
class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id is not None:
        return User(user_id)
    return None

# --- ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('accueil'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == os.getenv('APP_USERNAME') and password == os.getenv('APP_PASSWORD'):
            user = User(id=1)
            login_user(user)
            return redirect(url_for('accueil'))
        else:
            flash('Échec de la connexion. Vérifiez vos identifiants.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def accueil():
    return render_template('accueil.html')

@app.route('/analyser', methods=['POST'])
@login_required
def analyser():
    fichier = request.files.get('bulletin_pdf')
    nom_eleve = request.form.get('nom_eleve', '').strip()
    liste_matieres_str = request.form.get('liste_matieres', '')
    matieres_attendues = [m.strip() for m in liste_matieres_str.split(',') if m.strip()]

    if not all([fichier, nom_eleve, matieres_attendues]):
        flash("Tous les champs sont requis.", "danger")
        return redirect(url_for('accueil'))

    try:
        pdf_bytes = fichier.read()
        pdf_file_in_memory = io.BytesIO(pdf_bytes)
        
        texte_extrait = ""
        with pdfplumber.open(pdf_file_in_memory) as pdf:
            texte_extrait = pdf.pages[0].extract_text(x_tolerance=1, y_tolerance=1) or ""
        
        if not texte_extrait:
            raise ValueError("Le contenu du PDF est vide ou illisible.")

        donnees_structurees = analyser_texte_bulletin(texte_extrait, nom_eleve, matieres_attendues)
        
        if not donnees_structurees.get("nom_eleve"):
            raise ValueError(f"Le nom '{nom_eleve}' n'a pas été trouvé dans le contenu du PDF. Vérifiez l'orthographe ou les variations dans le PDF.")
        if len(donnees_structurees["appreciations_matieres"]) != len(matieres_attendues):
            raise ValueError(f"Le parser a trouvé {len(donnees_structurees['appreciations_matieres'])} matières au lieu des {len(matieres_attendues)} attendues.")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        if not client.api_key: raise ValueError("Clé GROQ_API_KEY non définie.")
        
        liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
        prompt_systeme = "Tu es un professeur principal qui rédige l'appréciation générale. Ton style est synthétique et analytique."
        prompt_utilisateur = f"""
        Voici les données de l'élève {nom_eleve}.
        Données brutes :
        {liste_appreciations}
        Ta réponse doit être en DEUX parties, séparées par "--- JUSTIFICATIONS ---".
        Partie 1: Rédige un paragraphe de 2-3 phrases pour l'appréciation globale.
        Partie 2: Justifie chaque idée clé avec des citations brutes des commentaires.
        """
        
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": prompt_systeme}, {"role": "user", "content": prompt_utilisateur}],
            model="llama3-70b-8192", temperature=0.5
        )
        reponse_complete_ia = chat_completion.choices[0].message.content
        
        separateur = "--- JUSTIFICATIONS ---"
        if separateur in reponse_complete_ia:
            parties = reponse_complete_ia.split(separateur, 1)
            appreciation_principale = parties[0].strip()
            justifications = MisakaMarkdown(parties[1].strip())
        else:
            appreciation_principale = reponse_complete_ia
            justifications = "Pas de justifications fournies."
        
        return render_template('resultat.html', res={
            "nom_eleve": nom_eleve,
            "donnees": donnees_structurees,
            "appreciation_principale": appreciation_principale,
            "justifications_html": justifications
        })

    except Exception as e:
        flash(f"Une erreur est survenue : {e}", "danger")
        return redirect(url_for('accueil'))

if __name__ == '__main__':
    app.run(debug=True)