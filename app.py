import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

# Initialisation de l'application Flask
app = Flask(__name__)

# --- Configuration de la base de données ---
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL is not set")
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Définition des modèles (nos tables) ---

class Eleve(db.Model):
    id = db.Column(db.Integer, primary_key=True) # Identifiant unique
    prenom = db.Column(db.String(100), nullable=False) # Prénom de l'élève
    nom = db.Column(db.String(100), nullable=False)   # Nom de famille

    def __repr__(self):
        return f'<Eleve {self.prenom} {self.nom}>'

# (Nous ajouterons la classe Matiere et Appréciation plus tard pour rester simple)


# --- Création des tables dans la base de données ---
# Cette commande doit être exécutée une seule fois pour créer la structure
with app.app_context():
    db.create_all()


# --- Définition des pages (routes) ---

@app.route('/')
def accueil():
    return redirect(url_for('liste_eleves')) # Redirige vers la page des élèves

@app.route('/eleves')
def liste_eleves():
    # Récupérer tous les élèves de la base de données
    tous_les_eleves = Eleve.query.order_by(Eleve.nom).all()
    return render_template('liste_eleves.html', eleves=tous_les_eleves)

@app.route('/eleve/ajouter', methods=['POST'])
def ajouter_eleve():
    # Récupérer les données du formulaire
    prenom = request.form.get('prenom')
    nom = request.form.get('nom')

    # Créer un nouvel objet Eleve
    if prenom and nom:
        nouvel_eleve = Eleve(prenom=prenom, nom=nom)
        # Ajouter à la session et sauvegarder en base
        db.session.add(nouvel_eleve)
        db.session.commit()

    # Rediriger vers la liste des élèves
    return redirect(url_for('liste_eleves'))

# (Le reste du fichier ne change pas)
if __name__ == '__main__':
    app.run(debug=True)