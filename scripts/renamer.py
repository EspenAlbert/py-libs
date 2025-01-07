from pathlib import Path


ROOT_PATH = Path(__file__).parent.parent

if __name__ == '__main__':
    to_rename = list(ROOT_PATH.glob('**/test_*.py'))
    for file in to_rename:
        new_name = file.name.replace('test_', '').replace(".py", "_test.py")
        file.rename(file.parent / new_name)
