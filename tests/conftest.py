from pathlib import Path
import random
import string

test_data_path = (Path(__file__).parent / "test-data").resolve()


def random_string(prefix: str = "", n: int = 32) -> str:
    return prefix + "".join(random.choice(string.ascii_lowercase) for _ in range(n))
