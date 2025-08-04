import os
from flask import Flask
from config import Config
from models import db
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_misaka import Misaka

bcrypt = Bcrypt()
login_manager = LoginManager()
misaka = Misaka()
login_manager.login_view = 'main.login'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    misaka.init_app(app)

    from main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    from models import User, Prompt, AIProvider # On importe les modèles ici
    @login_manager.user_loader
    def load_user(user_id):
        if user_id is not None:
            return User(user_id)
        return None

    return app