import os
from flask import Flask
from config import Config
from models import db, User, Prompt, AIProvider
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_misaka import Misaka

bcrypt = Bcrypt()
login_manager = LoginManager()
misaka = Misaka()
login_manager.login_view = 'main.login'

@login_manager.user_loader
def load_user(user_id):
    if user_id is not None:
        return User(user_id)
    return None

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    misaka.init_app(app)

    from main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    @app.cli.command("init-db")
    def init_db_command():
        """Crée toutes les tables de la base de données."""
        with app.app_context():
            db.create_all()
            if not Prompt.query.first():
                default_prompt = Prompt(
                    name="Prompt par Défaut",
                    system_message="Tu es un professeur principal qui rédige l'appréciation générale. Ton style est synthétique, analytique et tu justifies tes conclusions.",
                    user_message_template="""Rédige une appréciation pour l'élève {nom_eleve} pour le trimestre {trimestre}.
Contexte: {contexte_trimestre}

{appreciations_precedentes}
Voici les données BRUTES du trimestre actuel :
{liste_appreciations}

Ta réponse doit être en DEUX parties, séparées par "--- JUSTIFICATIONS ---".
**Partie 1 : Appréciation Globale**
Rédige un paragraphe de 2 à 3 phrases pour le bulletin en tenant compte de l'évolution de l'élève.
**Partie 2 : Justifications**
Sous le séparateur, justifie chaque idée clé avec des citations brutes des commentaires du trimestre actuel.""",
                    is_active=True)
                db.session.add(default_prompt)
            if not AIProvider.query.first():
                default_provider = AIProvider(
                    name="Mistral",
                    api_key=os.getenv("MISTRAL_API_KEY", "CHANGER_CETTE_CLE"),
                    model_name="mistral-large-latest",
                    is_active=True)
                db.session.add(default_provider)
            db.session.commit()
        print("Tables de la BDD créées et valeurs par défaut assurées.")
    return app