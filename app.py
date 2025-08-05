import os
from flask import Flask
from config import Config
from models import db, User, Prompt, AIProvider
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_misaka import Misaka
from flask_mail import Mail # NOUVEL IMPORT

bcrypt = Bcrypt()
login_manager = LoginManager()
misaka = Misaka()
mail = Mail() # NOUVELLE INSTANCE
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info' # Pour de jolis messages flash

@login_manager.user_loader
def load_user(user_id):
    # MODIFICATION : On charge maintenant l'utilisateur depuis la BDD
    return User.query.get(int(user_id))

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    misaka.init_app(app)
    mail.init_app(app) # NOUVELLE INITIALISATION

    from main import main as main_blueprint
    app.register_blueprint(main_blueprint)

    @app.cli.command("init-db")
    def init_db_command():
        """Crée les tables et un utilisateur admin par défaut."""
        with app.app_context():
            db.create_all()
            # MODIFICATION : On crée un vrai utilisateur dans la BDD
            if not User.query.first():
                admin_username = os.getenv('APP_USERNAME', 'admin')
                admin_email = os.getenv('APP_EMAIL', 'admin@example.com')
                admin_password = os.getenv('APP_PASSWORD', 'password')
                
                admin_user = User(username=admin_username, email=admin_email)
                admin_user.set_password(admin_password)
                db.session.add(admin_user)
                print(f"Utilisateur admin créé : {admin_username}")
            
            # Le reste de l'initialisation ne change pas
            if not Prompt.query.first():
                default_prompt = Prompt(
                    name="Prompt par Défaut",
                    system_message="Tu es un professeur principal...",
                    user_message_template="Rédige une appréciation...",
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