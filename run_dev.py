from improv.api.app import create_app
from improv.config import load_config
app = create_app(load_config())
