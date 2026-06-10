import os
import tempfile

tmpdir = tempfile.gettempdir()
test_db_path = os.path.join(tmpdir, "test_commerce.db")
os.environ["API_KEY"] = "test-key-123"
os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path}"
