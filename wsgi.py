from app import create_app, db
from models import Classe, Analyse

app = create_app()

# Cette commande est nécessaire pour pouvoir lancer 'flask init-db'
@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'Classe': Classe, 'Analyse': Analyse}