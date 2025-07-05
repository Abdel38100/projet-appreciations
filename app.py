import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# Initialisation de l'application Flask
app = Flask(__name__)

# --- Configuration de la base de données ---
# Récupère l'URL de la base de données depuis la variable d'environnement
db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL is not set")

# Configure l'application pour utiliser l'URL de la base de données
app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Recommandé pour désactiver des notifications inutiles

# Initialise l'extension SQLAlchemy avec notre application
db = SQLAlchemy(app)

# --- Définition des modèles (nos tables) ---
# Nous allons définir nos tables ici dans une prochaine étape.
# Pour l'instant, nous laissons cette partie vide.

# --- Définition des pages (routes) ---
@app.route('/')
def accueil():
    # Essayons de nous connecter pour vérifier que tout fonctionne
    try:
        db.session.execute(db.text('SELECT 1'))
        status_db = "Connectée avec succès !"
    except Exception as e:
        status_db = f"Erreur de connexion : {e}"

    return f"""
        <h1>Bonjour, Professeur !</h1>
        <p>L'application d'aide à la génération d'appréciations est en construction.</p>
        <p><strong>Statut de la base de données :</strong> {status_db}</p>
    """

# Permet de lancer l'application pour des tests locaux
# (Note: cela ne fonctionnera plus en local sans configurer la BDD, c'est normal)
if __name__ == '__main__':
    app.run(debug=True)