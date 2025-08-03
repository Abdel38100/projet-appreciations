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

# 1. Initialisation
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-tres-securisee')
Misaka(app)

# 2. Configuration BDD
db_url = os.getenv('DATABASE_URL')
if not db_url:
    # Pour le dev local, sinon Render doit fournir cette variable
    db_url = "sqlite:///local.db" 
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# 3. Modèles
class User(UserMixin):
    def __init__(self, id): self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id is not None: return User(user_id)
    return None

class Classe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    annee_scolaire = db.Column(db.String(10), nullable=False)
    nom_classe = db.Column(db.String(50), nullable=False)
    matieres = db.Column(db.Text, nullable=False)
    eleves = db.Column(db.Text, nullable=False)
    analyses = db.relationship('Analyse', backref='classe', lazy=True, cascade="all, delete-orphan")

class Analyse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_eleve = db.Column(db.String(200), nullable=False)
    appreciation_principale = db.Column(db.Text)
    justifications = db.Column(db.Text)
    donnees_brutes = db.Column(db.JSON)
    classe_id = db.Column(db.Integer, db.ForeignKey('classe.id'), nullable=False)

# 4. Commande pour initialiser la BDD
@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        db.create_all()
    print("Tables de la base de données créées avec succès.")

# 5. Routes
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
    session.clear()
    logout_user()
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def accueil():
    if request.method == 'POST':
        classe_id = request.form.get('classe_id')
        session['classe_id'] = classe_id
        return redirect(url_for('analyser'))
    try:
        classes = Classe.query.order_by(Classe.annee_scolaire.desc(), Classe.nom_classe).all()
        return render_template('accueil.html', classes=classes, derniere_classe_id=session.get('classe_id'))
    except Exception as e:
        flash(f"Erreur de base de données : {e}. Assurez-vous d'avoir lancé l'initialisation.", "warning")
        return render_template('accueil.html', classes=[], derniere_classe_id=None)

@app.route('/analyser', methods=['GET', 'POST'])
@login_required
def analyser():
    classe_id = session.get('classe_id')
    if not classe_id:
        flash("Veuillez d'abord sélectionner une classe.", "warning")
        return redirect(url_for('accueil'))
    classe = Classe.query.get_or_404(classe_id)
    eleves_liste = [e.strip() for e in classe.eleves.split('\n') if e.strip()]
    matieres_attendues = [m.strip() for m in classe.matieres.split(',') if m.strip()]
    if request.method == 'POST':
        fichier = request.files.get('bulletin_pdf')
        nom_eleve = request.form.get('nom_eleve', '').strip()
        if not all([fichier, nom_eleve]):
            flash("Veuillez sélectionner un élève et son bulletin.", "danger")
            return redirect(url_for('analyser'))
        try:
            pdf_bytes = fichier.read()
            pdf_file_in_memory = io.BytesIO(pdf_bytes)
            texte_extrait = ""
            with pdfplumber.open(pdf_file_in_memory) as pdf:
                texte_extrait = pdf.pages[0].extract_text(x_tolerance=1, y_tolerance=1) or ""
            if not texte_extrait: raise ValueError("Le contenu du PDF est vide.")
            donnees_structurees = analyser_texte_bulletin(texte_extrait, nom_eleve, matieres_attendues)
            if not donnees_structurees.get("nom_eleve"): raise ValueError(f"Le nom '{nom_eleve}' n'a pas été trouvé dans le PDF.")
            if len(donnees_structurees["appreciations_matieres"]) != len(matieres_attendues): raise ValueError(f"Le parser n'a pas trouvé le bon nombre de matières.")
            client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
            liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
            prompt_systeme = "Tu es un professeur principal qui rédige l'appréciation générale. Ton style est synthétique, analytique et tu justifies tes conclusions."
            prompt_utilisateur = f"Rédige une appréciation pour {nom_eleve} à partir de : {liste_appreciations}. Ta réponse doit avoir deux parties séparées par '--- JUSTIFICATIONS ---'. Partie 1: Appréciation globale. Partie 2: Justifications avec citations brutes."
            chat_completion = client.chat.completions.create(messages=[{"role": "system", "content": prompt_systeme}, {"role": "user", "content": prompt_utilisateur}], model="llama3-70b-8192")
            reponse_ia = chat_completion.choices[0].message.content
            separateur = "--- JUSTIFICATIONS ---"
            if separateur in reponse_ia:
                parties = reponse_ia.split(separateur, 1)
                appreciation_principale, justifications = parties[0].strip(), parties[1].strip()
            else:
                appreciation_principale, justifications = reponse_ia, ""
            nouvelle_analyse = Analyse(nom_eleve=nom_eleve, appreciation_principale=appreciation_principale, justifications=justifications, donnees_brutes=donnees_structurees, classe_id=classe_id)
            db.session.add(nouvelle_analyse)
            db.session.commit()
            return render_template('resultat.html', res=nouvelle_analyse, classe=classe)
        except Exception as e:
            flash(f"Une erreur est survenue : {e}", "danger")
            return redirect(url_for('analyser'))
    analyses_faites = {analyse.nom_eleve for analyse in classe.analyses}
    return render_template('analyser.html', classe=classe, eleves_liste=eleves_liste, analyses_faites=analyses_faites)

@app.route('/configuration', methods=['GET', 'POST'])
@login_required
def configuration():
    if request.method == 'POST':
        annee, nom_classe, matieres, eleves = request.form.get('annee_scolaire'), request.form.get('nom_classe'), request.form.get('matieres'), request.form.get('eleves')
        if all([annee, nom_classe, matieres, eleves]):
            db.session.add(Classe(annee_scolaire=annee, nom_classe=nom_classe, matieres=matieres, eleves=eleves))
            db.session.commit()
            flash("Nouvelle classe ajoutée !", "success")
        else: flash("Tous les champs sont requis.", "warning")
        return redirect(url_for('configuration'))
    classes = Classe.query.order_by(Classe.annee_scolaire.desc(), Classe.nom_classe).all()
    return render_template('configuration.html', classes=classes)

@app.route('/classe/supprimer/<int:classe_id>', methods=['POST'])
@login_required
def supprimer_classe(classe_id):
    classe_a_supprimer = Classe.query.get_or_404(classe_id)
    db.session.delete(classe_a_supprimer)
    db.session.commit()
    flash("La classe a été supprimée.", "info")
    return redirect(url_for('configuration'))

@app.route('/historique/<int:classe_id>')
@login_required
def historique_classe(classe_id):
    classe = Classe.query.get_or_404(classe_id)
    return render_template('historique.html', classe=classe)