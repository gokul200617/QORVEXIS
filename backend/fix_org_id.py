import os
import re

directories = [
    r"c:\Users\Gokul\OneDrive\Desktop\Qorvexis\backend\app\token_intelligence\analytics",
    r"c:\Users\Gokul\OneDrive\Desktop\Qorvexis\backend\app\business",
    r"c:\Users\Gokul\OneDrive\Desktop\Qorvexis\backend\app\connectors\services"
]

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # We want to match: `def some_func(self, db: Session) -> ...:`
    # or `def some_func(db: Session) -> ...:`
    # and replace with `def some_func(self, db: Session, org_id: str | None = None) -> ...:`
    
    # regex pattern to match standard signatures
    # Matches `def func_name(db: Session) -> return_type:` or `def func_name(self, db: Session) -> return_type:`
    # Also handles cases with limit=10 etc, we can just replace `(db: Session` with `(db: Session, org_id: str | None = None`
    # and `(self, db: Session` with `(self, db: Session, org_id: str | None = None`
    # We should be careful not to replace it if org_id is already there.

    if "org_id" in content and "def " in content:
        # maybe it already has it, but let's check carefully.
        pass

    # Replace `(db: Session)`
    content = re.sub(r'\(db: Session\)', r'(db: Session, org_id: str | None = None)', content)
    # Replace `(self, db: Session)`
    content = re.sub(r'\(self, db: Session\)', r'(self, db: Session, org_id: str | None = None)', content)
    # Replace `(db: Session, limit: int = 10)`
    content = re.sub(r'\(db: Session, limit: int = 10\)', r'(db: Session, limit: int = 10, org_id: str | None = None)', content)

    # Some methods might have `(db: Session, connector_id: str)`
    # We will ignore those unless they are failing.

    with open(filepath, 'w') as f:
        f.write(content)

for d in directories:
    for root, dirs, files in os.walk(d):
        for file in files:
            if file.endswith('.py'):
                process_file(os.path.join(root, file))

print("Fixed org_id in function signatures.")
