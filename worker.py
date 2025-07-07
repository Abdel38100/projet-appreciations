import os
import redis
from rq import Worker, Queue, Connection

# La liste des files d'attente que ce worker va écouter. 'default' est standard.
listen = ['default']

# On récupère l'URL de notre instance Redis depuis les variables d'environnement.
# Si la variable n'existe pas (par ex. en local), on se connecte à un Redis local par défaut.
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

# Établit la connexion à la base de données Redis.
conn = redis.from_url(redis_url)

if __name__ == '__main__':
    print("Lancement du worker...")
    # Le worker doit opérer dans le contexte d'une connexion Redis.
    with Connection(conn):
        # On crée l'objet Worker. Il va automatiquement chercher les tâches
        # dans les files d'attente de la liste 'listen'.
        worker = Worker(map(Queue, listen))
        
        # worker.work() est une boucle infinie. Le worker attendra des tâches
        # et les exécutera dès qu'elles arrivent.
        worker.work()