from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin):
    def __init__(self, id): self.id = id

class Classe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    annee_scolaire = db.Column(db.String(10), nullable=False)
    nom_classe = db.Column(db.String(50), nullable=False)
    matieres = db.Column(db.Text, nullable=False)
    eleves = db.Column(db.Text, nullable=False)
    analyses = db.relationship('Analyse', backref='classe', lazy=True, cascade="all, delete-orphan")

class Analyse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_eleve = db.Column(db.String(200), nullable=False)
    appreciation_principale = db.Column(db.Text)
    justifications = db.Column(db.Text)
    donnees_brutes = db.Column(db.JSON)
    classe_id = db.Column(db.Integer, db.ForeignKey('classe.id'), nullable=False)