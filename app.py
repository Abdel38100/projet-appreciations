import os
import re
import unicodedata
from flask import Flask, render_template, request, flash, redirect, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_bcrypt import Bcrypt

# --- CONFIGURATION DE BASE (SANS BDD, SANS REDIS POUR LE TEST) ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-pour-le-dev')
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

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

def normaliser_chaine(s):
    # Étape 1: Unicode Normalization (NFC) pour standardiser les caractères composés
    s = unicodedata.normalize('NFC', s)
    # Étape 2: Décomposer les caractères accentués (ex: 'é' -> 'e' + ´)
    s_decomposed = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    # Étape 3: Mettre en minuscule et ne garder que les lettres et chiffres
    s_alphanum = re.sub(r'[^a-z0-9]+', '', s_decomposed.lower())
    return s_alphanum

# --- ROUTES DE DÉBOGAGE ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('accueil'))
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        if username == admin_user.username and bcrypt.check_password_hash(admin_user.password_hash, password):
            login_user(admin_user)
            return redirect(url_for('accueil'))
        else: flash('Échec de la connexion.', 'danger')
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

@app.route('/lancer-analyse', methods=['POST'])
@login_required
def lancer_analyse():
    fichiers = request.files.getlist('bulletin_pdf')
    liste_eleves_str = request.form.get('liste_eleves', '')
    eleves_attendus = [e.strip() for e in liste_eleves_str.split('\n') if e.strip()]
    noms_fichiers = [f.filename for f in fichiers]

    debug_html = "<h2>Rapport de Débogage de la Correspondance</h2>"
    
    match_trouve = False
    
    for nom_eleve in eleves_attendus:
        nom_eleve_normalise = normaliser_chaine(nom_eleve)
        debug_html += f"<h4>Analyse pour l'élève : {nom_eleve} (Normalisé : <code>{nom_eleve_normalise}</code>)</h4><ul>"

        for nom_fichier in noms_fichiers:
            nom_fichier_normalise = normaliser_chaine(nom_fichier)
            
            # --- LA COMPARAISON ---
            # Au lieu de 'all(mot in ...)', on va joindre les mots et chercher la sous-chaîne.
            # "al naasan aman" -> "alnaasanamam"
            mots_eleve_joints = re.sub(r'\s+', '', nom_eleve_normalise)
            
            # On vérifie si la chaîne normalisée de l'élève est dans la chaîne normalisée du fichier
            if mots_eleve_joints in nom_fichier_normalise:
                match = "✅ TROUVÉ"
                match_trouve = True
            else:
                match = "❌ NON TROUVÉ"
                
            debug_html += (
                f"<li>"
                f"Comparaison avec le fichier : {nom_fichier} (Normalisé : <code>{nom_fichier_normalise}</code>)<br>"
                f"Chaîne de l'élève cherchée : <code>{mots_eleve_joints}</code><br>"
                f"Résultat : <strong>{match}</strong>"
                f"</li>"
            )
        debug_html += "</ul><hr>"

    if not match_trouve:
        debug_html = "<h3>Aucune correspondance trouvée. Voici le détail de toutes les tentatives :</h3>" + debug_html
    else:
        debug_html = "<h3>Au moins une correspondance a été trouvée ! Voici le détail :</h3>" + debug_html

    flash(debug_html, "info")
    return redirect(url_for('accueil'))

if __name__ == '__main__':
    app.run(debug=True)