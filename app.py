import os
import re
import pdfplumber
import time
import unicodedata
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_misaka import Misaka
import redis
from rq import Queue
from tasks import traiter_un_bulletin
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-par-defaut-pour-le-dev')
Misaka(app)

def normaliser_chaine(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9\s]+', '', s.lower())
    s = re.sub(r'\s+', ' ', s).strip()
    return s

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

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

ADMIN_USERNAME = os.getenv('APP_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('APP_PASSWORD', 'password')
password_hash = bcrypt.generate_password_hash(ADMIN_PASSWORD).decode('utf-8')
admin_user = User(id=1, username=ADMIN_USERNAME, password_hash=password_hash)

@login_manager.user_loader
def load_user(user_id):
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

with app.app_context():
    db.create_all()

redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
conn = redis.from_url(redis_url)
q = Queue(connection=conn)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('accueil'))
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        if username == admin_user.username and bcrypt.check_password_hash(admin_user.password_hash, password):
            login_user(admin_user)
            return redirect(url_for('accueil'))
        else:
            flash('Échec de la connexion.', 'danger')
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

@app.route('/historique')
@login_required
def historique():
    analyses_sauvegardees = Analyse.query.order_by(Analyse.cree_le.desc()).all()
    return render_template('historique.html', analyses=analyses_sauvegardees)

@app.route('/lancer-analyse', methods=['POST'])
@login_required
def lancer_analyse():
    fichiers = request.files.getlist('bulletin_pdf')
    liste_matieres_str = request.form.get('liste_matieres', '')
    liste_eleves_str = request.form.get('liste_eleves', '')
    matieres_attendues = [m.strip() for m in liste_matieres_str.split(',') if m.strip()]
    eleves_attendus = [e.strip() for e in liste_eleves_str.split('\n') if e.strip()]

    if not all([fichiers, matieres_attendues, eleves_attendus]):
        return "Erreur : Tous les champs sont requis."

    job_ids = []
    fichiers_traites = set()

    # On rétablit la boucle qui marche : on parcourt les élèves
    for nom_eleve in eleves_attendus:
        # Condition de sortie : si on a déjà traité tous les fichiers uploadés, on arrête
        if len(fichiers_traites) == len(fichiers):
            break

        fichier_trouve = None
        nom_eleve_normalise = normaliser_chaine(nom_eleve)
        mots_nom_eleve = nom_eleve_normalise.split()

        for fichier in fichiers:
            if fichier.filename in fichiers_traites: continue
            nom_fichier_normalise = normaliser_chaine(fichier.filename)
            if all(mot in nom_fichier_normalise for mot in mots_nom_eleve):
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
        flash("Aucune correspondance trouvée entre les élèves de votre liste et les noms des fichiers PDF. Veuillez vérifier l'orthographe et les noms de fichiers.", "danger")
        return redirect(url_for('accueil'))

    return redirect(url_for('page_suivi', job_ids=",".join(job_ids)))

@app.route('/suivi/<job_ids>')
@login_required
def page_suivi(job_ids):
    id_list = job_ids.split(',')
    return render_template('suivi.html', job_ids=id_list)

@app.route('/statut-jobs', methods=['POST'])
@login_required
def statut_jobs():
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
                    resultat_final = { "status": "succes", "nom_eleve": analyse_sauvegardee.nom_eleve, "appreciation_principale": analyse_sauvegardee.appreciation_principale, "justifications": analyse_sauvegardee.justifications }
            elif status == 'failed':
                resultat_final = {"status": "echec", "erreur": "La tâche a échoué."}
            
            resultats.append({"id": job.get_id(), "status": status, "resultat": resultat_final})
        else:
            resultats.append({"id": job_id, "status": "non_trouve"})

    return jsonify(resultats)

if __name__ == '__main__':
    app.run(debug=True)