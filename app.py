import os
import re
import pdfplumber
import unicodedata
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_misaka import markdown as MisakaMarkdown # On importe la fonction 'markdown' directement
import redis
from rq import Queue
from tasks import traiter_un_bulletin
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-par-defaut-pour-le-dev')
# La ligne Misaka(app) n'est plus nécessaire car on appelle la fonction directement

def normaliser_chaine(s):
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9]+', '', s.lower())
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

    nombre_a_traiter = len(fichiers)
    if len(eleves_attendus) < nombre_a_traiter:
        flash(f"Erreur : Vous avez téléversé {nombre_a_traiter} fichiers mais seulement fourni {len(eleves_attendus)} noms d'élèves.", "danger")
        return redirect(url_for('accueil'))

    job_ids = []

    for i in range(nombre_a_traiter):
        fichier = fichiers[i]
        nom_eleve = eleves_attendus[i]

        if not fichier.filename: continue

        chemin_fichier = os.path.join(app.config['UPLOAD_FOLDER'], fichier.filename)
        try:
            fichier.save(chemin_fichier)
            with open(chemin_fichier, "rb") as f:
                pdf_bytes = f.read()

            job = q.enqueue(
                'tasks.traiter_un_bulletin',
                args=(pdf_bytes, nom_eleve, matieres_attendues),
                job_timeout='10m'
            )
            job_ids.append(job.get_id())

        except Exception as e:
            print(f"Erreur lors de la sauvegarde/lecture du fichier {fichier.filename}: {e}")
            continue
        finally:
            if os.path.exists(chemin_fichier):
                os.remove(chemin_fichier)

    if not job_ids:
        flash("Aucune tâche d'analyse n'a pu être lancée. Vérifiez les logs du serveur pour des erreurs de lecture de PDF.", "danger")
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
                    resultat_final = { 
                        "status": "succes", 
                        "nom_eleve": analyse_sauvegardee.nom_eleve, 
                        "appreciation_principale": analyse_sauvegardee.appreciation_principale, 
                        # On convertit le texte Markdown des justifications en HTML ici
                        "justifications_html": MisakaMarkdown(analyse_sauvegardee.justifications or "")
                    }
            elif status == 'failed':
                erreur_msg = job.exc_info.strip().split('\n')[-1] if job.exc_info else "La tâche a échoué."
                resultat_final = {"status": "echec", "erreur": erreur_msg}
            
            if not resultat_final: resultat_final = {}
            if job.args: resultat_final['nom_eleve'] = job.args[1]

            resultats.append({"id": job.get_id(), "status": status, "resultat": resultat_final})
        else:
            resultats.append({"id": job_id, "status": "non_trouve"})

    return jsonify(resultats)

if __name__ == '__main__':
    app.run(debug=True)