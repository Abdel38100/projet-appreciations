from app import create_app

# Cette ligne crée l'application en utilisant notre "factory".
# C'est ce que Gunicorn va chercher et lancer.
app = create_app()