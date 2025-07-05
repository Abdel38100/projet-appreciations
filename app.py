from flask import Flask

# Initialisation de l'application Flask
app = Flask(__name__)

# Définition de la page d'accueil
@app.route('/')
def accueil():
    return "<h1>Bonjour, Professeur !</h1><p>L'application d'aide à la génération d'appréciations est en construction.</p>"

# Permet de lancer l'application pour des tests locaux
if __name__ == '__main__':
    app.run(debug=True)