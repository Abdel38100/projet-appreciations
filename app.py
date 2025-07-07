import os
import re
import pdfplumber
import time
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_misaka import Misaka
import redis
from rq import Queue
from tasks import traiter_un_bulletin # On importe notre fonction de tâche
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
Misaka(app)

# --- CONFIGURATION ---
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configuration de la base de données PostgreSQL
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Connexion à Redis
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
conn = redis.from_url(redis_url)
q = Queue(connection=conn)

# --- DÉFINITION DES MODÈLES DE LA BASE DE DONNÉES ---
class Analyse(db.Model):
    id = db.Column(db.String(36), primary_key=True) # ID de la tâche RQ
    nom_eleve = db.Column(db.String(200), nullable=False)
    moyenne_generale = db.Column(db.String(10))
    appreciation_principale = db.Column(db.Text, nullable=False)
    justifications = db.Column(db.Text)
    cree_le = db.Column(db.DateTime, server_default=db.func.now())

# --- ROUTES ---
@app.route('/')
def accueil():
    return render_template('accueil.html')

@app.route('/historique')
def historique():
    """Affiche la liste de toutes les analyses sauvegardées."""
    analyses_sauvegardees = Analyse.query.order_by(Analyse.cree_le.desc()).all()
    return render_template('historique.html', analyses=analyses_sauvegardees)

@app.route('/lancer-analyse', methods=['POST'])
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
            'tasks.traiter_un_bulletin', # On passe le chemin de la fonction
            args=(texte_extrait, nom_eleve, matieres_attendues),
            job_timeout='10m'
        )
        job_ids.append(job.get_id())

    return redirect(url_for('page_suivi', job_ids=",".join(job_ids)))

@app.route('/suivi/<job_ids>')
def page_suivi(job_ids):
    id_list = job_ids.split(',')
    return render_template('suivi.html', job_ids=id_list)

@app.route('/statut-jobs', methods=['POST'])
def statut_jobs():
    job_ids = request.json.get('job_ids', [])
    resultats = []
    
    for job_id in job_ids:
        job = q.fetch_job(job_id)
        resultat_final = None

        if job:
            status = job.get_status()
            if status == 'finished':
                # Si la tâche est finie, on va chercher le résultat dans la BDD
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