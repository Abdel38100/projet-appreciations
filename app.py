import os
import re
import pdfplumber
import time
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_misaka import Misaka
import redis
from rq import Queue
from tasks import traiter_un_bulletin # On importe notre fonction de tâche

app = Flask(__name__)
Misaka(app)
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Connexion à Redis et initialisation de la file d'attente ---
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
conn = redis.from_url(redis_url)
q = Queue(connection=conn)

@app.route('/')
def accueil():
    """Affiche la page d'accueil simple."""
    return render_template('accueil.html')

@app.route('/lancer-analyse', methods=['POST'])
def lancer_analyse():
    """
    Réceptionne les fichiers et crée une tâche pour chaque élève dans la file d'attente.
    Ne fait AUCUN traitement lourd.
    """
    fichiers = request.files.getlist('bulletin_pdf')
    liste_matieres_str = request.form.get('liste_matieres', '')
    liste_eleves_str = request.form.get('liste_eleves', '')

    matieres_attendues = [m.strip() for m in liste_matieres_str.split(',') if m.strip()]
    eleves_attendus = [e.strip() for e in liste_eleves_str.split('\n') if e.strip()]

    if not fichiers or not matieres_attendues or not eleves_attendus:
        return "Erreur : Vous devez fournir des fichiers, la liste des matières et la liste des élèves."

    job_ids = []
    fichiers_traites = set()

    for nom_eleve in eleves_attendus:
        fichier_trouve = None
        for fichier in fichiers:
            if nom_eleve.lower() in fichier.filename.lower() and fichier.filename not in fichiers_traites:
                fichier_trouve = fichier
                break
        
        if not fichier_trouve:
            # Pour l'instant, on ignore les élèves sans fichier. On pourrait améliorer ça plus tard.
            continue

        fichiers_traites.add(fichier_trouve.filename)
        
        # On lit le contenu du fichier et on le passe en mémoire.
        # seek(0) est crucial si on réutilise le même handle de fichier.
        fichier_trouve.seek(0)
        pdf_bytes = fichier_trouve.read()

        texte_extrait = ""
        try:
            with pdfplumber.open(pdf_bytes) as pdf:
                texte_extrait = pdf.pages[0].extract_text(x_tolerance=1, y_tolerance=1) or ""
        except Exception as e:
            print(f"Erreur de lecture PDF pour {fichier_trouve.filename}: {e}")
            continue

        # --- C'EST ICI QUE LA MAGIE OPÈRE ---
        # On ajoute la tâche à la file d'attente Redis.
        # q.enqueue() prend la fonction à exécuter et ses arguments.
        # Le worker exécutera : traiter_un_bulletin(texte_extrait, nom_eleve, matieres_attendues)
        job = q.enqueue(
            traiter_un_bulletin,
            texte_extrait,
            nom_eleve,
            matieres_attendues,
            job_timeout='10m' # On autorise la tâche à durer jusqu'à 10 minutes
        )
        job_ids.append(job.get_id())

    # On redirige l'utilisateur vers une page de suivi, en lui passant les ID des tâches lancées.
    # On joint les ID avec des virgules pour les passer dans l'URL.
    return redirect(url_for('page_suivi', job_ids=",".join(job_ids)))


@app.route('/suivi/<job_ids>')
def page_suivi(job_ids):
    """Affiche la page qui va suivre l'état des tâches."""
    # On transforme la chaîne d'ID en une vraie liste
    id_list = job_ids.split(',')
    return render_template('suivi.html', job_ids=id_list)


@app.route('/statut-jobs', methods=['POST'])
def statut_jobs():
    """
    Point d'API appelé par le JavaScript de la page de suivi.
    Renvoie l'état actuel de toutes les tâches demandées.
    """
    job_ids = request.json.get('job_ids', [])
    resultats = []
    
    for job_id in job_ids:
        job = q.fetch_job(job_id)
        if job:
            status = job.get_status()
            resultat_tache = None
            if status == 'finished':
                resultat_tache = job.result
            elif status == 'failed':
                resultat_tache = {
                    "status": "echec",
                    "nom_eleve": job.meta.get('nom_eleve', 'Inconnu'),
                    "erreur": "La tâche a échoué. Voir les logs du worker."
                }

            resultats.append({
                "id": job.get_id(),
                "status": status,
                "resultat": resultat_tache
            })
        else:
            resultats.append({"id": job_id, "status": "non_trouve"})

    return jsonify(resultats)

if __name__ == '__main__':
    app.run(debug=True)