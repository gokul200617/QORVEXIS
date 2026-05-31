import os
import re

files_to_update = [
    r'app/models/inference_session.py',
    r'app/models/request_log.py',
    r'app/models/request_lifecycle_event.py',
    r'app/token_intelligence/models/optimization_recommendation.py',
    r'app/telemetry/models/telemetry_snapshot.py',
    r'app/token_intelligence/models/token_tracking.py',
    r'app/token_intelligence/models/workload_signature.py',
    r'app/gateway/gateway_models.py',
    r'app/connectors/models/provider_usage_snapshot.py',
    r'app/connectors/models/connector_instance.py',
    r'app/connectors/models/connector_sync_event.py',
    r'app/connectors/models/connector_credentials.py',
    r'app/gateway/provider_credentials/provider_credentials.py',
]

for f in files_to_update:
    path = os.path.join(r'c:\Users\Gokul\OneDrive\Desktop\Qorvexis\backend', f)
    if not os.path.exists(path):
        print(f'File not found: {path}')
        continue
    
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    if 'organization_id: Mapped[str | None]' in content or 'organization_id: Mapped[Optional[str]]' in content:
        print(f'Already updated: {path}')
        continue
        
    # Insert organization_id after __tablename__
    content = re.sub(
        r'(__tablename__\s*=\s*".*?"\n)',
        r'\1    organization_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)\n',
        content
    )
    
    with open(path, 'w', encoding='utf-8') as file:
        file.write(content)
        
    print(f'Updated: {path}')
