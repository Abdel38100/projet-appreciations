import os
import re
import pdfplumber
import time
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_misaka import Misaka
import redis
from rq import Queue
from tasks import traiter_un_bulletin
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt

app = Flask(__name__)
# Une clé secrète est nécessaire pour la gestion des sessions
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-par-defaut-pour-le-dev')
Misaka(app)

# --- CONFIGURATION (inchangée) ---
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# --- GESTION DE LA CONNEXION (FLASK-LOGIN) ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirige vers la page 'login' si non connecté
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

# --- DÉFINITION DES MODÈLES ---
# On crée un modèle factice pour l'utilisateur, car Flask-Login en a besoin
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

# On crée notre unique utilisateur à partir des variables d'environnement
ADMIN_USERNAME = os.getenv('APP_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('APP_PASSWORD', 'password')
password_hash = bcrypt.generate_password_hash(ADMIN_PASSWORD).decode('utf-8')
admin_user = User(id=1, username=ADMIN_USERNAME, password_hash=password_hash)

@login_manager.user_loader
def load_user(user_id):
    # Comme nous n'avons qu'un seul utilisateur, on le retourne toujours.
    if int(user_id) == admin_user.id:
        return admin_user
    return None

class Analyse(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    nom_eleve = db.Column(db.String(200), nullable=False)
    moyenne_generale = db.Column(db.String(10))
    appreciation_principale = db.Column(db.Text, nullable=False)
    justifications = db.Column(db.Text)
    cree_le = db.Column(db.DateTime, server_default=db.func.now())

# Commande pour créer les tables
with app.app_context():
    db.create_all()

# --- Connexion à Redis ---
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
conn = redis.from_url(redis_url)
q = Queue(connection=conn)

# --- ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('accueil'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == admin_user.username and bcrypt.check_password_hash(admin_user.password_hash, password):
            login_user(admin_user)
            flash('Connexion réussie !', 'success')
            return redirect(url_for('accueil'))
        else:
            flash('Échec de la connexion. Vérifiez le nom d\'utilisateur et le mot de passe.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required # <-- ON PROTÈGE CETTE PAGE
def accueil():
    return render_template('accueil.html')

@app.route('/historique')
@login_required # <-- ON PROTÈGE CETTE PAGE
def historique():
    analyses_sauvegardees = Analyse.query.order_by(Analyse.cree_le.desc()).all()
    return render_template('historique.html', analyses=analyses_sauvegardees)

@app.route('/lancer-analyse', methods=['POST'])
@login_required # <-- ON PROTÈGE CETTE ACTION
def lancer_analyse():
    # Le reste de cette fonction est identique au message précédent
    fichiers = request.files.getlist('bulletin_pdf')
    liste_matieres_str = request.form.get('liste_matieres', '')
    liste_eleves_str = request.form.get('liste_eleves', '')
    matieres_attendues = [m.strip() for m in liste_matieres_str.split(',') if m.strip()]
    eleves_attendus = [e.strip() for e in liste_eleves_str.split('\n') if e.strip()]

    if not all([fichiers, matieres_attendues, eleves_attendus]):
        return "Erreur : Tous les champs sont requis."

    job_ids = []
    fichiers_traites = set()

    for nom_eleve in eleves_attendus:
        fichier_trouve = None
        for fichier in fichiers:
            if nom_eleve.lower() in fichier.filename.lower() and fichier.filename not in fichiers_traites:
                fichier_trouve = fichier
                break
        
        if not fichier_trouve: continue

        fichiers_traites.add(fichier_trouve.filename)
        fichier_trouve.seek(0)
        pdf_bytes = fichier_trouve.read()

        texte_extrait = ""
        try:
            with pdfplumber.open(pdf_bytes) as pdf:
                texte_extrait = pdf.pages[0].extract_text(x_tolerance=1, y_tolerance=1) or ""
        except Exception as e:
            print(f"Erreur de lecture PDF pour {fichier_trouve.filename}: {e}")
            continue

        job = q.enqueue(
            'tasks.traiter_un_bulletin',
            args=(texte_extrait, nom_eleve, matieres_attendues),
            job_timeout='10m'
        )
        job_ids.append(job.get_id())

    if not job_ids:
        flash("Aucun fichier correspondant aux élèves n'a été trouvé pour lancer une analyse.", "warning")
        return redirect(url_for('accueil'))

    return redirect(url_for('page_suivi', job_ids=",".join(job_ids)))

@app.route('/suivi/<job_ids>')
@login_required # <-- ON PROTÈGE CETTE PAGE
def page_suivi(job_ids):
    id_list = job_ids.split(',')
    return render_template('suivi.html', job_ids=id_list)

@app.route('/statut-jobs', methods=['POST'])
@login_required # <-- ON PROTÈGE CETTE ACTION
def statut_jobs():
    # Le reste de cette fonction est identique au message précédent
    job_ids = request.json.get('job_ids', [])
    resultats = []
    
    for job_id in job_ids:
        job = q.fetch_job(job_id)
        resultat_final = None

        if job:
            status = job.get_status()
            if status == 'finished':
                analyse_sauvegardee = Analyse.query.get(job_id)
                if analyse_sauvegardee:
                    resultat_final = {
                        "status": "succes",
                        "nom_eleve": analyse_sauvegardee.nom_eleve,
                        "appreciation_principale": analyse_sauvegardee.appreciation_principale,
                        "justifications": analyse_sauvegardee.justifications
                    }
            elif status == 'failed':
                resultat_final = {"status": "echec", "erreur": "La tâche a échoué."}
            
            resultats.append({"id": job.get_id(), "status": status, "resultat": resultat_final})
        else:
            resultats.append({"id": job_id, "status": "non_trouve"})

    return jsonify(resultats)

if __name__ == '__main__':
    app.run(debug=True)