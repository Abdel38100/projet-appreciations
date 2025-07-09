import os
import pdfplumber
import redis
from rq import Queue
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, current_app
from flask_login import login_required, current_user, login_user, logout_user
from flask_misaka import markdown as MisakaMarkdown
from app import db, bcrypt, User, Analyse # On importe depuis notre app.py
from tasks import traiter_un_bulletin

main = Blueprint('main', __name__)

# On récupère la file d'attente Redis depuis le contexte de l'application
# Note : Cette partie est un peu avancée, elle assure que 'q' est bien initialisé.
def get_queue():
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    conn = redis.from_url(redis_url)
    return Queue(connection=conn)

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.accueil'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        ADMIN_USERNAME = os.getenv('APP_USERNAME')
        ADMIN_PASSWORD = os.getenv('APP_PASSWORD')
        
        # Le mot de passe stocké n'est pas hashé, on le compare directement.
        # Pour une meilleure sécurité, il faudrait le hasher.
        # Ici on compare directement pour simplifier le débogage.
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            user = User(id=1)
            login_user(user)
            return redirect(url_for('main.accueil'))
        else:
            flash('Échec de la connexion. Vérifiez vos identifiants.', 'danger')
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@main.route('/')
@login_required
def accueil():
    return render_template('accueil.html')

@main.route('/history')
@login_required
def history():
    analyses_sauvegardees = Analyse.query.order_by(Analyse.cree_le.desc()).all()
    return render_template('historique.html', analyses=analyses_sauvegardees)

@main.route('/lancer-analyse', methods=['POST'])
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
        flash(f"Erreur : Vous avez téléversé {nombre_a_traiter} fichiers pour {len(eleves_attendus)} élèves.", "danger")
        return redirect(url_for('main.accueil'))

    job_ids = []
    q = get_queue()
    UPLOAD_FOLDER = current_app.config['UPLOAD_FOLDER']

    for i in range(nombre_a_traiter):
        fichier, nom_eleve = fichiers[i], eleves_attendus[i]
        if not fichier.filename: continue
        chemin_fichier = os.path.join(UPLOAD_FOLDER, fichier.filename)
        try:
            fichier.save(chemin_fichier)
            with open(chemin_fichier, "rb") as f:
                pdf_bytes = f.read()
            job = q.enqueue('tasks.traiter_un_bulletin', args=(pdf_bytes, nom_eleve, matieres_attendues), job_timeout='10m')
            job_ids.append(job.get_id())
        except Exception as e:
            print(f"Erreur lors de la sauvegarde/lecture du fichier {fichier.filename}: {e}")
            continue
        finally:
            if os.path.exists(chemin_fichier): os.remove(chemin_fichier)
    
    if not job_ids:
        flash("Aucune tâche n'a pu être lancée.", "danger")
        return redirect(url_for('main.accueil'))
    return redirect(url_for('main.page_suivi', job_ids=",".join(job_ids)))

@main.route('/suivi/<job_ids>')
@login_required
def page_suivi(job_ids):
    return render_template('suivi.html', job_ids=job_ids.split(','))

@main.route('/statut-jobs', methods=['POST'])
@login_required
def statut_jobs():
    job_ids = request.json.get('job_ids', [])
    resultats = []
    q = get_queue()
    
    for job_id in job_ids:
        job = q.fetch_job(job_id)
        resultat_final = None
        if job:
            status = job.get_status()
            if status == 'finished':
                analyse = Analyse.query.get(job_id)
                if analyse:
                    resultat_final = {"status": "succes", "nom_eleve": analyse.nom_eleve, "appreciation_principale": analyse.appreciation_principale, "justifications_html": MisakaMarkdown(analyse.justifications or ""), "donnees": analyse.donnees_brutes}
            elif status == 'failed':
                resultat_final = {"status": "echec", "erreur": job.exc_info.strip().split('\n')[-1] if job.exc_info else "Tâche échouée."}
            
            if not resultat_final: resultat_final = {}
            if job.args: resultat_final['nom_eleve'] = job.args[1]
            resultats.append({"id": job.get_id(), "status": status, "resultat": resultat_final})
        else:
            resultats.append({"id": job_id, "status": "non_trouve"})
    return jsonify(resultats)