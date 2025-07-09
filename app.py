import os
import re
import pdfplumber
import unicodedata
import io
from flask import Flask, render_template, request, flash, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_misaka import Misaka
from groq import Groq
from parser import analyser_texte_bulletin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB

# --- INITIALISATION ET CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-tres-securisee')
Misaka(app)

# --- CONFIGURATION DE LA BASE DE DONNÉES (CORRIGÉE) ---
db_url = os.getenv('DATABASE_URL')
if db_url:
    # SQLAlchemy préfère 'postgresql://' au lieu de 'postgres://'
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # Fournit une valeur par défaut pour éviter de planter si la variable n'est pas définie
    # Cela peut arriver en local ou lors d'un démarrage à froid.
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///local.db'
    print("ATTENTION: DATABASE_URL non trouvée, utilisation d'une base de données SQLite locale.")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialisation des extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."

# --- MODÈLES ---
class Classe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    annee_scolaire = db.Column(db.String(10), nullable=False)
    nom_classe = db.Column(db.String(50), nullable=False)
    matieres = db.Column(db.Text, nullable=False)
    analyses = db.relationship('Analyse', backref='classe', lazy=True, cascade="all, delete-orphan")

class Analyse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_eleve = db.Column(db.String(200), nullable=False)
    appreciation_principale = db.Column(db.Text)
    justifications = db.Column(db.Text)
    donnees_brutes = db.Column(JSONB)
    classe_id = db.Column(db.Integer, db.ForeignKey('classe.id'), nullable=False)
    
class User(UserMixin):
    def __init__(self, id): self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id is not None: return User(user_id)
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
        else: flash('Échec de la connexion.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('classe_id', None)
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def accueil():
    classes = Classe.query.order_by(Classe.annee_scolaire.desc(), Classe.nom_classe).all()
    derniere_classe_id = session.get('classe_id')
    return render_template('accueil.html', classes=classes, derniere_classe_id=derniere_classe_id)

@app.route('/analyser', methods=['POST'])
@login_required
def analyser():
    fichier = request.files.get('bulletin_pdf')
    nom_eleve = request.form.get('nom_eleve', '').strip()
    classe_id = request.form.get('classe_id')
    
    if not all([fichier, nom_eleve, classe_id]):
        flash("Tous les champs sont requis.", "danger")
        return redirect(url_for('accueil'))
    
    session['classe_id'] = classe_id
    classe = Classe.query.get(classe_id)
    if not classe:
        flash("Classe sélectionnée invalide.", "danger")
        return redirect(url_for('accueil'))
        
    matieres_attendues = [m.strip() for m in classe.matieres.split(',') if m.strip()]

    try:
        pdf_bytes = fichier.read()
        pdf_file_in_memory = io.BytesIO(pdf_bytes)
        texte_extrait = ""
        with pdfplumber.open(pdf_file_in_memory) as pdf:
            texte_extrait = pdf.pages[0].extract_text(x_tolerance=1, y_tolerance=1) or ""
        
        if not texte_extrait: raise ValueError("Le contenu du PDF est vide ou illisible.")

        donnees_structurees = analyser_texte_bulletin(texte_extrait, nom_eleve, matieres_attendues)
        
        if not donnees_structurees.get("nom_eleve"):
            raise ValueError(f"Le nom '{nom_eleve}' n'a pas été trouvé dans le contenu du PDF.")
        if len(donnees_structurees["appreciations_matieres"]) != len(matieres_attendues):
            raise ValueError(f"Le parser n'a pas trouvé le bon nombre de matières.")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        if not client.api_key: raise ValueError("Clé GROQ_API_KEY non définie.")
        
        liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
        prompt_systeme = "Tu es un professeur principal qui rédige l'appréciation générale. Ton style est synthétique, analytique et tu justifies tes conclusions."
        prompt_utilisateur = f"""
        Voici les données de l'élève {nom_eleve}.
        Données brutes :
        {liste_appreciations}
        Ta réponse doit être en DEUX parties distinctes, séparées par la ligne "--- JUSTIFICATIONS ---".
        **Partie 1 : Appréciation Globale**
        Rédige un paragraphe de 2 à 3 phrases pour le bulletin.
        **Partie 2 : Justifications**
        Sous le séparateur, justifie chaque idée clé avec des citations brutes des commentaires.
        Rédige maintenant ta réponse complète.
        """
        
        chat_completion = client.chat.completions.create(messages=[{"role": "system", "content": prompt_systeme}, {"role": "user", "content": prompt_utilisateur}], model="llama3-70b-8192", temperature=0.5)
        reponse_complete_ia = chat_completion.choices[0].message.content
        
        separateur = "--- JUSTIFICATIONS ---"
        if separateur in reponse_complete_ia:
            parties = reponse_complete_ia.split(separateur, 1)
            appreciation_principale = parties[0].replace("**Partie 1 : Appréciation Globale**", "").strip()
            justifications = parties[1].replace("**Partie 2 : Justifications**", "").strip()
        else:
            appreciation_principale = reponse_complete_ia
            justifications = ""
        
        nouvelle_analyse = Analyse(
            nom_eleve=nom_eleve,
            appreciation_principale=appreciation_principale,
            justifications=justifications,
            donnees_brutes=donnees_structurees,
            classe_id=classe_id
        )
        db.session.add(nouvelle_analyse)
        db.session.commit()
        
        return render_template('resultat.html', res=nouvelle_analyse, classe=classe)

    except Exception as e:
        flash(f"Une erreur est survenue : {e}", "danger")
        return redirect(url_for('accueil'))

@app.route('/configuration', methods=['GET', 'POST'])
@login_required
def configuration():
    if request.method == 'POST':
        annee = request.form.get('annee_scolaire')
        nom_classe = request.form.get('nom_classe')
        matieres = request.form.get('matieres')
        
        if all([annee, nom_classe, matieres]):
            nouvelle_classe = Classe(annee_scolaire=annee, nom_classe=nom_classe, matieres=matieres)
            db.session.add(nouvelle_classe)
            db.session.commit()
            flash("Nouvelle classe ajoutée avec succès !", "success")
        else:
            flash("Tous les champs sont requis.", "warning")
        return redirect(url_for('configuration'))
        
    classes = Classe.query.order_by(Classe.annee_scolaire.desc(), Classe.nom_classe).all()
    return render_template('configuration.html', classes=classes)

@app.route('/classe/supprimer/<int:classe_id>', methods=['POST'])
@login_required
def supprimer_classe(classe_id):
    classe_a_supprimer = Classe.query.get_or_404(classe_id)
    db.session.delete(classe_a_supprimer)
    db.session.commit()
    flash("La classe et toutes ses analyses ont été supprimées.", "info")
    return redirect(url_for('configuration'))
    
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)