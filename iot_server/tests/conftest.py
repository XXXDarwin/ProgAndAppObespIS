import os

# тестовый ключ: реальный ключ из .env тестам не нужен
os.environ.setdefault('IOT_MASTER_KEY', '11' * 32)